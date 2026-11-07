import hashlib
import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models

from core.fields import EncryptedTextField

from .base import TimeStampedModel
from .tenancy import Condominium


class Provider(models.TextChoices):
    EWELINK = "ewelink", "eWeLink (Sonoff)"
    SHELLY = "shelly", "Shelly"


class Direction(models.TextChoices):
    ENTRY = "entry", "Entry"
    EXIT = "exit", "Exit"
    BOTH = "both", "Entry & exit"


class IntegrationAccount(TimeStampedModel):
    """Cloud credentials for a relay provider at one condominium.

    Fill in only the section matching ``provider``. Secrets are encrypted at rest.
    """

    class EwelinkRegion(models.TextChoices):
        AS = "as", "Asia (as)"
        CN = "cn", "China (cn)"
        EU = "eu", "Europe (eu)"
        US = "us", "Americas (us)"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="integration_accounts")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    label = models.CharField(max_length=100, help_text="e.g. 'Main eWeLink account'.")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    # eWeLink (CoolKit Open API v2)
    ewelink_region = models.CharField(max_length=2, choices=EwelinkRegion.choices, default=EwelinkRegion.AS, blank=True)
    ewelink_app_id = models.CharField("eWeLink App ID", max_length=100, blank=True)
    ewelink_app_secret = EncryptedTextField("eWeLink App Secret", blank=True, default="")
    ewelink_account = models.CharField(
        "eWeLink login (email/phone)", max_length=150, blank=True,
        help_text="Optional: lets the server log in again if the refresh token expires.",
    )
    ewelink_password = EncryptedTextField("eWeLink password", blank=True, default="")
    ewelink_access_token = EncryptedTextField("eWeLink access token", blank=True, default="")
    ewelink_refresh_token = EncryptedTextField("eWeLink refresh token", blank=True, default="")
    ewelink_token_expires_at = models.DateTimeField("eWeLink token expires at", null=True, blank=True)

    # Shelly Cloud Control API
    shelly_server_uri = models.URLField(
        "Shelly server URI", blank=True,
        help_text="From Shelly app > User settings > Authorization cloud key, e.g. https://shelly-103-eu.shelly.cloud",
    )
    shelly_auth_key = EncryptedTextField("Shelly auth key", blank=True, default="")

    class Meta:
        ordering = ["condominium", "provider", "label"]

    def __str__(self):
        return f"{self.label} ({self.get_provider_display()})"

    def clean(self):
        errors = {}
        if self.provider == Provider.EWELINK:
            if not self.ewelink_app_id:
                errors["ewelink_app_id"] = "Required for eWeLink."
            if not self.ewelink_app_secret:
                errors["ewelink_app_secret"] = "Required for eWeLink."
        elif self.provider == Provider.SHELLY:
            if not self.shelly_server_uri:
                errors["shelly_server_uri"] = "Required for Shelly."
            if not self.shelly_auth_key:
                errors["shelly_auth_key"] = "Required for Shelly."
        if errors:
            raise ValidationError(errors)


class AccessGate(TimeStampedModel):
    """A physical entry point: vehicle barrier, pedestrian gate or door."""

    class GateType(models.TextChoices):
        VEHICLE = "vehicle", "Vehicle barrier"
        PEDESTRIAN = "pedestrian", "Pedestrian gate"
        DOOR = "door", "Door"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="gates")
    name = models.CharField(max_length=100)
    gate_type = models.CharField(max_length=20, choices=GateType.choices, default=GateType.VEHICLE)
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.ENTRY)
    is_active = models.BooleanField(default=True)
    lpr_auto_open_residents = models.BooleanField(
        default=True, help_text="Open automatically when an LPR camera reads a registered resident plate."
    )
    lpr_auto_open_invited = models.BooleanField(
        default=True, help_text="Open automatically for a plate on a valid invitation."
    )

    class Meta:
        ordering = ["condominium", "name"]
        constraints = [models.UniqueConstraint(fields=["condominium", "name"], name="uniq_gate_name")]

    def __str__(self):
        return f"{self.condominium.code} / {self.name}"


class RelayController(TimeStampedModel):
    """A Sonoff or Shelly relay that opens a gate.

    The relay must have Inching / Auto-Off (2-3 s) enabled in the eWeLink or
    Shelly app: the server only ever sends "on".
    """

    class ControlMode(models.TextChoices):
        CLOUD = "cloud", "Cloud API"
        LOCAL = "local", "Local LAN"
        LOCAL_THEN_CLOUD = "local_then_cloud", "Local LAN, fall back to cloud"

    gate = models.ForeignKey(AccessGate, on_delete=models.CASCADE, related_name="relays")
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    control_mode = models.CharField(max_length=20, choices=ControlMode.choices, default=ControlMode.CLOUD)
    is_active = models.BooleanField(default=True)

    # Cloud
    account = models.ForeignKey(
        IntegrationAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="relays",
        help_text="Cloud account that owns this device.",
    )
    cloud_device_id = models.CharField(
        "Cloud device ID", max_length=64, blank=True,
        help_text="eWeLink device ID (e.g. 1000abc123) or Shelly device ID.",
    )
    channel = models.PositiveSmallIntegerField(
        default=0, help_text="Output channel: Shelly switch id / eWeLink outlet (0 for single-channel)."
    )

    # Local LAN (optional)
    local_ip = models.GenericIPAddressField("Local IP", null=True, blank=True, protocol="IPv4")
    local_port = models.PositiveIntegerField("Local port", null=True, blank=True, help_text="eWeLink LAN: 8081, Shelly: 80.")
    local_username = models.CharField("Local username", max_length=64, blank=True, help_text="Shelly: usually 'admin'.")
    local_password = EncryptedTextField("Local password", blank=True, default="")
    local_device_key = EncryptedTextField("eWeLink LAN device key", blank=True, default="")

    pulse_seconds = models.PositiveSmallIntegerField(
        default=3, help_text="Must match the Inching / Auto-Off duration configured on the device."
    )
    last_triggered_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ["gate", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_provider_display()})"

    @property
    def condominium(self):
        return self.gate.condominium

    def clean(self):
        errors = {}
        uses_cloud = self.control_mode in (self.ControlMode.CLOUD, self.ControlMode.LOCAL_THEN_CLOUD)
        uses_local = self.control_mode in (self.ControlMode.LOCAL, self.ControlMode.LOCAL_THEN_CLOUD)
        if uses_cloud:
            if not self.account_id:
                errors["account"] = "Required for cloud control."
            if not self.cloud_device_id:
                errors["cloud_device_id"] = "Required for cloud control."
        if uses_local and not self.local_ip:
            errors["local_ip"] = "Required for local control."
        if self.account_id:
            if self.account.provider != self.provider:
                errors["account"] = "Account provider does not match the relay provider."
            elif self.gate_id and self.account.condominium_id != self.gate.condominium_id:
                errors["account"] = "Account belongs to a different condominium."
        if errors:
            raise ValidationError(errors)


class LprCamera(TimeStampedModel):
    """A Dahua LPR camera posting PlateResult events to the webhook.

    Each camera authenticates with its own Basic Auth credentials instead of a
    real user account, so a leaked camera password cannot log in anywhere else.
    """

    gate = models.ForeignKey(AccessGate, on_delete=models.CASCADE, related_name="cameras")
    name = models.CharField(max_length=100)
    device_id = models.CharField(
        "Dahua device ID", max_length=64, unique=True, help_text="The deviceID sent in the camera's PlateResult payload."
    )
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.ENTRY)
    ip_address = models.GenericIPAddressField("IP address", null=True, blank=True, protocol="IPv4")
    is_active = models.BooleanField(default=True)

    webhook_username = models.CharField(
        max_length=64, unique=True, help_text="Basic Auth username to enter in the camera's HTTP Post settings."
    )
    webhook_password_hash = models.CharField(max_length=128, blank=True, editable=False)

    plate_field = models.CharField(
        max_length=100, blank=True,
        help_text="Dotted path to the plate in the camera's JSON, e.g. 'Picture.Plate.PlateNumber'. "
                  "Leave blank to detect common Dahua formats.",
    )

    # Optional: camera HTTP API login, for pulling snapshots.
    api_username = models.CharField("Camera API username", max_length=64, blank=True)
    api_password = EncryptedTextField("Camera API password", blank=True, default="")

    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_payload = models.JSONField(
        null=True, blank=True, editable=False, help_text="Most recent request body, kept for configuring the parser."
    )

    class Meta:
        ordering = ["gate", "name"]
        verbose_name = "LPR camera"

    def __str__(self):
        return f"{self.name} [{self.device_id}]"

    @property
    def condominium(self):
        return self.gate.condominium

    def set_webhook_password(self, raw_password: str):
        self.webhook_password_hash = make_password(raw_password)

    def check_webhook_password(self, raw_password: str) -> bool:
        return bool(self.webhook_password_hash) and check_password(raw_password, self.webhook_password_hash)


class Kiosk(TimeStampedModel):
    """A visitor tablet at a gate. Authenticates to the API with a device token."""

    TOKEN_PREFIX = "kio_"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="kiosks")
    gate = models.ForeignKey(AccessGate, on_delete=models.SET_NULL, null=True, blank=True, related_name="kiosks")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    token_hint = models.CharField(max_length=16, blank=True, editable=False)
    token_hash = models.CharField(max_length=64, blank=True, editable=False, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)
    app_version = models.CharField(max_length=30, blank=True, editable=False)

    class Meta:
        ordering = ["condominium", "name"]

    def __str__(self):
        return self.name

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def issue_token(self) -> str:
        """Generate a new token; only its hash is stored, so show the return value once."""
        raw = self.TOKEN_PREFIX + secrets.token_urlsafe(32)
        self.token_hint = raw[:10] + "..."
        self.token_hash = self.hash_token(raw)
        return raw

    def clean(self):
        if self.gate_id and self.condominium_id and self.gate.condominium_id != self.condominium_id:
            raise ValidationError({"gate": "Gate belongs to a different condominium."})
