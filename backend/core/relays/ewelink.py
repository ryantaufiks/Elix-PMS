"""Sonoff relays via eWeLink: CoolKit Open API v2 (cloud) and DIY-mode LAN API.

Not yet verified against a real device. The relay must have Inching / Auto-Off
enabled in the eWeLink app: these APIs only switch the relay on.
"""
import base64
import hashlib
import hmac
import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import IntegrationAccount

from .base import RelayError, RelayResult, http, json_or_error

ACCESS_TOKEN_LIFETIME = timedelta(days=30)
TOKEN_ERRORS = {401, 402, 406}  # CoolKit: token invalid / expired / missing


def _api_base(account):
    return f"https://{account.ewelink_region or 'as'}-apia.coolkit.cc"


def _signed_post(account, path, payload):
    """Login/refresh calls are signed with HMAC-SHA256(app secret, body)."""
    body = json.dumps(payload, separators=(",", ":"))
    sign = base64.b64encode(hmac.new(account.ewelink_app_secret.encode(), body.encode(), hashlib.sha256).digest())
    response = http("POST", f"{_api_base(account)}{path}", data=body, headers={
        "Content-Type": "application/json",
        "X-CK-Appid": account.ewelink_app_id,
        "Authorization": f"Sign {sign.decode()}",
    })
    return json_or_error(response, "eWeLink")


def _store_tokens(account, data):
    account.ewelink_access_token = data["at"]
    account.ewelink_refresh_token = data["rt"]
    account.ewelink_token_expires_at = timezone.now() + ACCESS_TOKEN_LIFETIME
    account.save(update_fields=[
        "ewelink_access_token", "ewelink_refresh_token", "ewelink_token_expires_at", "updated_at",
    ])


def renew_tokens(account):
    """Refresh the access token, falling back to a password login if one is configured."""
    with transaction.atomic():
        account = IntegrationAccount.objects.select_for_update().get(pk=account.pk)
        if account.ewelink_refresh_token:
            body = _signed_post(account, "/v2/user/refresh", {"rt": account.ewelink_refresh_token})
            if body.get("error") == 0:
                _store_tokens(account, body["data"])
                return account
        if account.ewelink_account and account.ewelink_password:
            key = "email" if "@" in account.ewelink_account else "phoneNumber"
            body = _signed_post(account, "/v2/user/login", {
                key: account.ewelink_account, "password": account.ewelink_password, "countryCode": "+65",
            })
            if body.get("error") == 0:
                _store_tokens(account, body["data"])
                return account
            raise RelayError(f"eWeLink login failed: {body.get('msg') or body.get('error')}")
        raise RelayError("eWeLink token expired; enter a new access/refresh token in the integration account")


def _authed(relay, method, path, **kwargs):
    account = relay.account
    expiring = account.ewelink_token_expires_at and account.ewelink_token_expires_at < timezone.now() + timedelta(days=1)
    if not account.ewelink_access_token or expiring:
        account = relay.account = renew_tokens(account)
    for attempt in range(2):
        response = http(method, f"{_api_base(account)}{path}", headers={
            "X-CK-Appid": account.ewelink_app_id,
            "Authorization": f"Bearer {account.ewelink_access_token}",
        }, **kwargs)
        body = json_or_error(response, "eWeLink")
        if body.get("error") in TOKEN_ERRORS and attempt == 0:
            account = relay.account = renew_tokens(account)
            continue
        if body.get("error") != 0:
            raise RelayError(f"eWeLink error {body.get('error')}: {body.get('msg', '')}".strip())
        return body.get("data") or {}


def _switch_params(relay):
    if relay.channel:
        return {"switches": [{"switch": "on", "outlet": relay.channel}]}
    return {"switch": "on"}


def cloud_pulse(relay):
    _authed(relay, "POST", "/v2/device/thing/status",
            json={"type": 1, "id": relay.cloud_device_id, "params": _switch_params(relay)})
    return RelayResult("cloud", "Switched on (device inching turns it off)")


def cloud_status(relay):
    data = _authed(relay, "GET", "/v2/device/thing/status",
                   params={"type": 1, "id": relay.cloud_device_id, "params": "switch|switches|online"})
    params = data.get("params", {})
    state = params.get("switch") or next(
        (s["switch"] for s in params.get("switches", []) if s.get("outlet") == relay.channel), "unknown"
    )
    return RelayResult("cloud", state, data)


def _diy(relay, endpoint, data):
    if relay.local_device_key:
        raise RelayError("Encrypted eWeLink LAN mode is not supported yet; put the device in DIY mode or use cloud")
    response = http("POST", f"http://{relay.local_ip}:{relay.local_port or 8081}/zeroconf/{endpoint}",
                    json={"deviceid": relay.cloud_device_id, "data": data})
    body = json_or_error(response, "eWeLink LAN")
    if body.get("error") not in (0, None):
        raise RelayError(f"eWeLink LAN error {body.get('error')}")
    return body.get("data") or {}


def local_pulse(relay):
    if relay.channel:
        _diy(relay, "switches", {"switches": [{"switch": "on", "outlet": relay.channel}]})
    else:
        _diy(relay, "switch", {"switch": "on"})
    return RelayResult("local", "Switched on (device inching turns it off)")


def local_status(relay):
    data = _diy(relay, "info", {})
    if isinstance(data, str):
        data = json.loads(data)
    return RelayResult("local", data.get("switch", "unknown"), data)
