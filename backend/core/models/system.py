import json
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
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

    # Kiosk AI assistant (OpenAI)
    class AssistantMode(models.TextChoices):
        PIPELINE = "pipeline", "Speech to text (lower cost)"
        REALTIME = "realtime", "Realtime voice (most natural)"

    openai_api_key = EncryptedTextField("OpenAI API key", blank=True, default="",
                                        help_text="Used by every site's kiosk assistant unless the site has its own key.")
    assistant_mode = models.CharField(
        "Assistant mode", max_length=10, choices=AssistantMode.choices, default=AssistantMode.PIPELINE,
        help_text="Speech to text: transcribe, answer, speak (a short pause per answer). Realtime: live two-way voice.",
    )
    assistant_chat_model = models.CharField("Chat model", max_length=60, default="gpt-4.1-mini")
    assistant_transcribe_model = models.CharField("Transcription model", max_length=60, default="gpt-4o-mini-transcribe")
    assistant_tts_model = models.CharField("Text-to-speech model", max_length=60, default="gpt-4o-mini-tts")
    assistant_realtime_model = models.CharField("Realtime model", max_length=60, default="gpt-realtime-mini")
    assistant_voice = models.CharField("Voice", max_length=30, default="coral")
    assistant_max_session_seconds = models.PositiveIntegerField(
        "Longest conversation (seconds)", default=180, help_text="A conversation ends after this long.",
    )
    assistant_daily_sessions = models.PositiveIntegerField(
        "Conversations per kiosk per day", default=100, help_text="Caps the OpenAI bill of each kiosk.",
    )

    # Outgoing email (SMTP): subscription notices, alerts, test messages
    class SmtpSecurity(models.TextChoices):
        STARTTLS = "starttls", "STARTTLS (usually port 587)"
        SSL = "ssl", "SSL/TLS (usually port 465)"
        NONE = "none", "None (port 25, trusted networks only)"

    smtp_host = models.CharField("SMTP host", max_length=255, blank=True, help_text="e.g. smtp.office365.com")
    smtp_port = models.PositiveIntegerField("SMTP port", null=True, blank=True, help_text="Default 587.")
    smtp_security = models.CharField("Security", max_length=10, choices=SmtpSecurity.choices, blank=True,
                                     help_text="Default STARTTLS.")
    smtp_username = models.CharField("SMTP username", max_length=255, blank=True)
    smtp_password = EncryptedTextField("SMTP password", blank=True, default="")
    email_from_address = models.EmailField("From address", blank=True, help_text="e.g. no-reply@yourcompany.com.sg")
    email_from_name = models.CharField("From name", max_length=100, blank=True, help_text="Default Elix.")
    email_reply_to = models.EmailField("Reply-to address", blank=True,
                                       help_text="Where replies go, e.g. your support mailbox.")

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


class BackupStorage(FileSystemStorage):
    """Files under BACKUP_ROOT: outside MEDIA_ROOT, so backups never end up inside the next backup or
    behind a media URL. The folder is read on every use (not fixed when the app starts), so tests and
    overridden settings write where they should."""

    @property
    def base_location(self):
        return settings.BACKUP_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)


def backup_storage():
    return BackupStorage()


class Backup(TimeStampedModel):
    """A platform backup (database + media, for disaster recovery) or one site's data export
    (records and their files, for handover, audit or a PDPA request). Platform admins only."""

    class Kind(models.TextChoices):
        PLATFORM = "platform", "Platform backup"
        SITE = "site", "Site export"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        RUNNING = "running", "Running"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    condominium = models.ForeignKey("core.Condominium", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    file = models.FileField(storage=backup_storage, blank=True)
    size = models.BigIntegerField(default=0)
    error = models.TextField(blank=True)
    automatic = models.BooleanField(default=False, help_text="Made by the daily schedule rather than by hand.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(help_text="Deleted with its file after this.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.created_at:%Y-%m-%d %H:%M}"


class BackupDownload(models.Model):
    """Who downloaded which backup, and when: the archives hold every resident's personal data."""

    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name="downloads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at"]


class EmailLog(models.Model):
    """One outgoing email to one recipient. Kept 30 days so the platform admin can see what went out and why
    something failed; the body is stored so a retry sends exactly the same message."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    condominium = models.ForeignKey("core.Condominium", on_delete=models.CASCADE, null=True, blank=True,
                                    related_name="+", help_text="The site the email is about, if any.")
    to = models.EmailField()
    subject = models.CharField(max_length=200)
    template = models.CharField(max_length=60)
    body_text = models.TextField()
    body_html = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.subject} -> {self.to} ({self.status})"
