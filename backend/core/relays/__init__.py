"""Gate relay drivers. ``pulse`` opens a gate, ``status`` reads the relay state."""
from core.models import Provider, RelayController

from . import ewelink, shelly
from .base import RelayError, RelayResult

DRIVERS = {Provider.SHELLY: shelly, Provider.EWELINK: ewelink}
Mode = RelayController.ControlMode

__all__ = ["RelayError", "RelayResult", "pulse", "status"]


def _run(relay, action):
    driver = DRIVERS[relay.provider]
    local, cloud = getattr(driver, f"local_{action}"), getattr(driver, f"cloud_{action}")
    if relay.control_mode == Mode.LOCAL:
        return local(relay)
    if relay.control_mode == Mode.CLOUD:
        return cloud(relay)
    try:
        return local(relay)
    except RelayError as local_error:
        try:
            result = cloud(relay)
        except RelayError as cloud_error:
            raise RelayError(f"Local: {local_error}; cloud: {cloud_error}") from cloud_error
        result.detail = f"{result.detail} (local failed: {local_error})"
        return result


def pulse(relay) -> RelayResult:
    return _run(relay, "pulse")


def status(relay) -> RelayResult:
    return _run(relay, "status")
