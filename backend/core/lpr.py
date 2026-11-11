"""Dahua LPR webhook: Basic Auth per camera, tolerant plate extraction."""
import base64
import binascii
import json
import logging
import secrets
from functools import lru_cache

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from . import entitlements
from .access import handle_plate
from .auth_views import client_ip, over_limit
from .models import LprCamera
from .validators import PLATE_RE, normalize_plate

logger = logging.getLogger(__name__)

# Keys under which Dahua firmwares report the plate, in order of preference.
PLATE_KEYS = ("PlateNumber", "plateNumber", "plate_number", "PlateNo", "plateNo", "Plate", "plate")
MAX_STORED_BODY = 20_000


def _unauthorized():
    response = JsonResponse({"detail": "Authentication required"}, status=401)
    response["WWW-Authenticate"] = 'Basic realm="lpr"'
    return response


@lru_cache(maxsize=1)
def _dummy_hash():
    return make_password(secrets.token_hex(16))


def _camera_from_basic_auth(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return None
    try:
        username, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return None
    camera = LprCamera.objects.select_related("gate__condominium").filter(webhook_username=username).first()
    if camera is None:
        check_password(password, _dummy_hash())  # Same cost as a real check, so timing reveals no usernames.
        return None
    return camera if camera.check_webhook_password(password) else None


def _at_path(payload, path):
    value = payload
    for part in path.split("."):
        if isinstance(value, list):
            value = value[int(part)] if part.isdigit() and int(part) < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value if isinstance(value, str) else None


def _find_plate(value):
    """Depth-first search for the first plate-like value under a known key."""
    if isinstance(value, dict):
        for key in PLATE_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
            if isinstance(candidate, dict):
                found = _find_plate(candidate)
                if found:
                    return found
        for child in value.values():
            found = _find_plate(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_plate(child)
            if found:
                return found
    return None


def extract_plate(camera, payload):
    raw = _at_path(payload, camera.plate_field) if camera.plate_field else _find_plate(payload)
    plate = normalize_plate(raw or "")
    return plate if PLATE_RE.match(plate) else ""


@csrf_exempt
@require_POST
def lpr_webhook(request):
    # Checking a webhook password is deliberately slow, so guessing is capped per address.
    ip = client_ip(request)
    if over_limit("lpr-ip", ip, 600, 60):
        return JsonResponse({"detail": "Too many requests"}, status=429)
    if cache.get(f"lpr-auth-failures:{ip}", 0) >= 20:
        return JsonResponse({"detail": "Too many failed sign-ins; try again in 5 minutes"}, status=429)
    camera = _camera_from_basic_auth(request)
    if camera is None:
        cache.set(f"lpr-auth-failures:{ip}", cache.get(f"lpr-auth-failures:{ip}", 0) + 1, 300)
        return _unauthorized()

    body = request.body[:MAX_STORED_BODY]
    try:
        payload = json.loads(body) if body else {}
    except (ValueError, UnicodeDecodeError):
        payload = {"_raw": body.decode(errors="replace"), "_content_type": request.content_type}
    if not isinstance(payload, dict):
        payload = {"_data": payload}

    camera.last_seen_at = timezone.now()
    camera.last_payload = payload
    camera.save(update_fields=["last_seen_at", "last_payload"])

    condo = camera.gate.condominium
    if not camera.is_active or not condo.lpr_enabled or not entitlements.has(condo, "lpr"):
        return JsonResponse({"status": "recorded", "detail": "LPR is disabled; payload stored for inspection"})

    plate = extract_plate(camera, payload)
    if not plate:
        logger.warning("LPR camera %s: no plate found in payload", camera.device_id)
        return JsonResponse({"status": "ignored", "detail": "No plate number found"})

    log = handle_plate(camera, plate, payload)
    if log is None:
        return JsonResponse({"status": "duplicate", "plate": plate})
    return JsonResponse({"status": log.result, "plate": plate, "reason": log.reason})
