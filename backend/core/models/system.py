import json

from django.core.exceptions import ValidationError
from django.db import models

from core.fields import EncryptedTextField

from .base import TimeStampedModel

FCM_KEYS = ("project_id", "client_email", "private_key")


class SystemSettings(TimeStampedModel):
    """Server-wide integration settings, edited in the admin. Exactly one row (pk=1).

    Every field is optional: a blank value falls back to the matching ``.env`` variable
    (see ``core.config``), so existing deployments keep working unchanged.
    """

    # LiveKit Cloud video intercom
    livekit_url = models.CharField(
        "LiveKit URL", max_length=255, blank=True,
        help_text="WebSocket URL from LiveKit Cloud > Settings, e.g. wss://your-project.livekit.cloud",
    )
    livekit_api_key = models.CharField("LiveKit API key", max_length=255, blank=True)
    livekit_api_secret = EncryptedTextField("LiveKit API secret", blank=True, default="")
    livekit_token_ttl_seconds = models.PositiveIntegerField(
        "LiveKit token lifetime (seconds)", null=True, blank=True, help_text="Default 600.",
    )
    intercom_unlock_window_seconds = models.PositiveIntegerField(
        "Intercom unlock window (seconds)", null=True, blank=True,
        help_text="How long after a call starts the resident may still swipe to unlock. Default 600.",
    )

    # Firebase Cloud Messaging
    fcm_service_account_json = EncryptedTextField(
        "FCM service account JSON", blank=True, default="",
        help_text="Paste the whole JSON key from Firebase console > Project settings > Service accounts.",
    )

    # Gate relays and LPR
    relay_http_timeout = models.FloatField(
        "Relay HTTP timeout (seconds)", null=True, blank=True, help_text="Default 5.",
    )
    lpr_debounce_seconds = models.PositiveIntegerField(
        "LPR debounce (seconds)", null=True, blank=True,
        help_text="Repeated reads of the same plate at the same gate within this window are ignored. Default 20.",
    )

    class Meta:
        verbose_name = verbose_name_plural = "System settings"

    def __str__(self):
        return "System settings"

    def clean(self):
        errors = {}
        self.livekit_url = self.livekit_url.strip()
        self.livekit_api_key = self.livekit_api_key.strip()
        self.livekit_api_secret = self.livekit_api_secret.strip()
        if self.livekit_url and not self.livekit_url.startswith(("wss://", "ws://", "https://", "http://")):
            errors["livekit_url"] = "Must start with wss:// (or https://)."
        if self.fcm_service_account_json.strip():
            try:
                info = json.loads(self.fcm_service_account_json)
            except ValueError:
                info = None
            if not isinstance(info, dict):
                errors["fcm_service_account_json"] = "Not a valid JSON object."
            elif missing := [k for k in FCM_KEYS if not info.get(k)]:
                errors["fcm_service_account_json"] = f"Missing {', '.join(missing)}."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.filter(pk=1).first() or cls(pk=1)
