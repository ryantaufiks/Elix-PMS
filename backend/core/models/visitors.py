import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

from core.validators import normalize_plate, validate_plate

from .base import TimeStampedModel
from .devices import AccessGate
from .tenancy import Condominium, Unit


class Visitor(TimeStampedModel):
    """A person who has visited (or is expected at) a condominium.

    PDPA: store only the partial NRIC/FIN (last 3 digits + letter), and a face
    photo only with recorded consent.
    """

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="visitors")
    full_name = models.CharField(max_length=150)
    phone = PhoneNumberField(blank=True)
    id_partial = models.CharField(
        "Partial NRIC/FIN", max_length=4, blank=True, help_text="Last 3 digits and letter only, e.g. 567D."
    )
    company = models.CharField(max_length=100, blank=True)
    face_photo = models.ImageField(upload_to="visitors/faces/%Y/%m/", blank=True)
    face_consent_at = models.DateTimeField(null=True, blank=True)
    is_blacklisted = models.BooleanField(default=False)
    blacklist_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name

    def clean(self):
        if self.face_photo and not self.face_consent_at:
            raise ValidationError({"face_consent_at": "Record the visitor's consent before storing a face photo."})


def generate_invitation_token():
    return secrets.token_urlsafe(24)


class Invitation(TimeStampedModel):
    """A resident's pre-registration of a visitor; shared to the visitor as a QR code."""

    class Purpose(models.TextChoices):
        GUEST = "guest", "Guest"
        DELIVERY = "delivery", "Delivery"
        CONTRACTOR = "contractor", "Contractor"
        PICKUP = "pickup", "Pick-up / drop-off"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="invitations")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="invitations")
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invitations")
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="invitations")
    visitor_name = models.CharField(max_length=150)
    visitor_phone = PhoneNumberField(blank=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.GUEST)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    max_entries = models.PositiveSmallIntegerField(default=1, help_text="0 = unlimited within the validity window.")
    entry_count = models.PositiveSmallIntegerField(default=0, editable=False)
    vehicle_plate = models.CharField(
        max_length=12, blank=True, validators=[validate_plate], help_text="Optional: lets the LPR camera open the gate."
    )
    require_face = models.BooleanField(default=False, help_text="Visitor must pass face verification at the kiosk.")
    gates = models.ManyToManyField(
        AccessGate, blank=True, related_name="invitations", help_text="Leave empty to allow every gate."
    )
    token = models.CharField(max_length=64, unique=True, default=generate_invitation_token, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.CharField(max_length=255, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-valid_from"]
        indexes = [
            models.Index(fields=["condominium", "status", "valid_until"]),
            models.Index(fields=["condominium", "vehicle_plate"]),
        ]

    def __str__(self):
        return f"{self.visitor_name} -> {self.unit} ({self.valid_from:%d %b %Y})"

    @property
    def share_url(self):
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/i/{self.token}"

    def _sync_derived_fields(self):
        self.vehicle_plate = normalize_plate(self.vehicle_plate)
        if self.unit_id and not self.condominium_id:
            self.condominium_id = self.unit.condominium_id

    def clean(self):
        self._sync_derived_fields()
        errors = {}
        if self.unit_id and self.condominium_id and self.unit.condominium_id != self.condominium_id:
            errors["unit"] = "Unit belongs to a different condominium."
        if self.valid_from and self.valid_until:
            if self.valid_until <= self.valid_from:
                errors["valid_until"] = "Must be after the start time."
            elif self.condominium_id:
                max_days = self.condominium.invitation_max_days
                if self.valid_until - self.valid_from > timedelta(days=max_days):
                    errors["valid_until"] = f"Invitations may last at most {max_days} days at this condominium."
        if self.require_face and self.condominium_id and not self.condominium.face_verification_enabled:
            errors["require_face"] = "Face verification is not enabled at this condominium."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self._sync_derived_fields()
        super().save(*args, **kwargs)

    def check_usable(self, at=None):
        """Return (ok, reason) for whether the invitation admits a visitor now."""
        at = at or timezone.now()
        if self.status != self.Status.ACTIVE:
            return False, f"Invitation is {self.get_status_display().lower()}."
        if at < self.valid_from:
            return False, "Invitation is not valid yet."
        if at > self.valid_until:
            return False, "Invitation has expired."
        if self.max_entries and self.entry_count >= self.max_entries:
            return False, "Entry limit reached."
        return True, ""

    def record_entry(self):
        Invitation.objects.filter(pk=self.pk).update(entry_count=F("entry_count") + 1)
        self.refresh_from_db(fields=["entry_count"])
        if self.max_entries and self.entry_count >= self.max_entries:
            self.status = self.Status.COMPLETED
            self.save(update_fields=["status", "updated_at"])

    def cancel(self):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancelled_at", "updated_at"])
