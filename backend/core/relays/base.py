from dataclasses import dataclass, field

import requests

from core import config


class RelayError(Exception):
    """A relay command failed; the message is safe to show to staff."""


@dataclass
class RelayResult:
    via: str  # "local" or "cloud"
    detail: str = ""
    data: dict = field(default_factory=dict)


def http(method, url, **kwargs):
    """requests wrapper: one timeout policy, and network failures become RelayError."""
    kwargs.setdefault("timeout", config.get("RELAY_HTTP_TIMEOUT"))
    try:
        return requests.request(method, url, **kwargs)
    except requests.Timeout as exc:
        raise RelayError(f"Timed out contacting {url.split('?')[0]}") from exc
    except requests.RequestException as exc:
        raise RelayError(f"Cannot reach {url.split('?')[0]}: {exc.__class__.__name__}") from exc


def json_or_error(response, what):
    try:
        return response.json() if response.content else {}
    except ValueError as exc:
        raise RelayError(f"{what}: invalid JSON response (HTTP {response.status_code})") from exc
