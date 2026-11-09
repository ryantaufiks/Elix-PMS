"""Runtime integration settings: the admin's System settings row wins, ``.env`` is the fallback.

Read on every use (one primary-key lookup), so admin changes apply immediately in the web,
worker and beat processes without a restart.
"""
from django.conf import settings

# setting name -> SystemSettings field
FIELDS = {
    "LIVEKIT_URL": "livekit_url",
    "LIVEKIT_API_KEY": "livekit_api_key",
    "LIVEKIT_API_SECRET": "livekit_api_secret",
    "LIVEKIT_TOKEN_TTL_SECONDS": "livekit_token_ttl_seconds",
    "INTERCOM_UNLOCK_WINDOW_SECONDS": "intercom_unlock_window_seconds",
    "FCM_SERVICE_ACCOUNT_JSON": "fcm_service_account_json",
    "RELAY_HTTP_TIMEOUT": "relay_http_timeout",
    "LPR_DEBOUNCE_SECONDS": "lpr_debounce_seconds",
    "OPENAI_API_KEY": "openai_api_key",
}


def _row():
    from .models import SystemSettings

    return SystemSettings.objects.filter(pk=1).first()


def get(name):
    value = getattr(_row(), FIELDS[name], None)
    if value in (None, ""):
        return getattr(settings, name, "")
    return value


def source(name):
    """'admin', '.env' or '' (unset) - shown in the admin so staff know which value is live."""
    if getattr(_row(), FIELDS[name], None) not in (None, ""):
        return "admin"
    return ".env" if getattr(settings, name, "") not in (None, "") else ""
