"""Firebase Cloud Messaging (HTTP v1). Push is best-effort: failures are logged, never raised to callers."""
import json
import logging
from functools import lru_cache

import requests
from django.conf import settings
from django.utils import timezone

from .models import PushDevice

logger = logging.getLogger(__name__)
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


@lru_cache(maxsize=1)
def _credentials():
    from google.oauth2 import service_account

    with open(settings.FCM_SERVICE_ACCOUNT_FILE) as fh:
        info = json.load(fh)
    return service_account.Credentials.from_service_account_info(info, scopes=[SCOPE]), info["project_id"]


def _access_token():
    from google.auth.transport.requests import Request

    credentials, project_id = _credentials()
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials.token, project_id


def is_enabled():
    return bool(settings.FCM_SERVICE_ACCOUNT_FILE)


def send(devices, data, title, body, ttl_seconds):
    """Send a high-priority message to each device; drop tokens FCM reports as gone."""
    if not is_enabled():
        logger.info("Push disabled (FCM_SERVICE_ACCOUNT_FILE not set); skipped %s", data.get("type"))
        return 0
    token, project_id = _access_token()
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    sent = 0
    for device in devices:
        message = {
            "token": device.token,
            "data": {k: str(v) for k, v in data.items()},
            "android": {"priority": "high", "ttl": f"{ttl_seconds}s"},
            "apns": {
                "headers": {"apns-priority": "10", "apns-expiration": str(int(timezone.now().timestamp()) + ttl_seconds)},
                "payload": {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}},
            },
        }
        try:
            response = requests.post(url, json={"message": message}, timeout=5,
                                     headers={"Authorization": f"Bearer {token}"})
        except requests.RequestException:
            logger.exception("FCM request failed for device %s", device.pk)
            continue
        if response.ok:
            sent += 1
            PushDevice.objects.filter(pk=device.pk).update(last_used_at=timezone.now())
            continue
        details = response.text[:1000]
        if response.status_code == 404 or "UNREGISTERED" in details:
            device.delete()
        else:
            logger.warning("FCM rejected device %s: HTTP %s %s", device.pk, response.status_code, details[:300])
    return sent
