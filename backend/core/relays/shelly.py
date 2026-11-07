"""Shelly relays: local RPC (Gen2/Gen3, Gen1 fallback) and Shelly Cloud Control API v2."""
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .base import RelayError, RelayResult, http, json_or_error


def _local_base(relay):
    port = f":{relay.local_port}" if relay.local_port and relay.local_port != 80 else ""
    return f"http://{relay.local_ip}{port}"


def _rpc(relay, method, params):
    # Gen2+ devices authenticate with Digest SHA-256 and the fixed user "admin".
    auth = HTTPDigestAuth(relay.local_username or "admin", relay.local_password) if relay.local_password else None
    response = http("POST", f"{_local_base(relay)}/rpc", auth=auth,
                    json={"id": 1, "method": method, "params": params})
    if response.status_code == 404:
        return None  # Not a Gen2+ device
    if response.status_code == 401:
        raise RelayError("Shelly rejected the local password (HTTP 401)")
    body = json_or_error(response, "Shelly RPC")
    if "error" in body:
        raise RelayError(f"Shelly RPC error {body['error'].get('code')}: {body['error'].get('message')}")
    if response.status_code >= 400:
        raise RelayError(f"Shelly RPC HTTP {response.status_code}")
    return body.get("result", {})


def _gen1(relay, query):
    auth = HTTPBasicAuth(relay.local_username or "admin", relay.local_password) if relay.local_password else None
    response = http("GET", f"{_local_base(relay)}/relay/{relay.channel}", params=query, auth=auth)
    if response.status_code >= 400:
        raise RelayError(f"Shelly Gen1 HTTP {response.status_code}")
    return json_or_error(response, "Shelly Gen1")


def local_pulse(relay):
    params = {"id": relay.channel, "on": True, "toggle_after": relay.pulse_seconds}
    result = _rpc(relay, "Switch.Set", params)
    if result is None:
        _gen1(relay, {"turn": "on", "timer": relay.pulse_seconds})
        return RelayResult("local", f"Gen1 relay on for {relay.pulse_seconds}s")
    return RelayResult("local", f"On for {relay.pulse_seconds}s", result)


def local_status(relay):
    result = _rpc(relay, "Switch.GetStatus", {"id": relay.channel})
    if result is None:
        result = _gen1(relay, {})
    return RelayResult("local", "on" if result.get("output", result.get("ison")) else "off", result)


def _cloud(relay, path, payload):
    account = relay.account
    response = http("POST", f"{account.shelly_server_uri.rstrip('/')}{path}",
                    params={"auth_key": account.shelly_auth_key}, json=payload)
    body = json_or_error(response, "Shelly Cloud")
    if response.status_code == 429:
        raise RelayError("Shelly Cloud rate limit (1 request/second) - try again")
    if response.status_code >= 400:
        messages = ", ".join((body.get("data") or {}).get("messages") or []) if isinstance(body, dict) else ""
        error = body.get("error") if isinstance(body, dict) else ""
        raise RelayError(f"Shelly Cloud HTTP {response.status_code}: {error or ''} {messages}".strip())
    return body


def cloud_pulse(relay):
    _cloud(relay, "/v2/devices/api/set/switch", {
        "id": relay.cloud_device_id, "channel": relay.channel, "on": True, "toggle_after": relay.pulse_seconds,
    })
    return RelayResult("cloud", f"On for {relay.pulse_seconds}s")


def cloud_status(relay):
    devices = _cloud(relay, "/v2/devices/api/get", {"ids": [relay.cloud_device_id], "select": ["status"]})
    if not devices:
        raise RelayError("Shelly Cloud does not know this device ID")
    device = devices[0]
    if not device.get("online"):
        raise RelayError("Device is offline in Shelly Cloud")
    switch = (device.get("status") or {}).get(f"switch:{relay.channel}") or {}
    return RelayResult("cloud", "on" if switch.get("output") else "off", device)
