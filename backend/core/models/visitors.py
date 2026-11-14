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


class VisitPurpose(models.TextChoices):
    GUEST = "guest", "Guest"
    DELIVERY = "delivery", "Parcel delivery"
    FOOD = "food", "Food delivery"
    CONTRACTOR = "contractor", "Contractor"
    PICKUP = "pickup", "Pick-up / drop-off"
    OTHER = "other", "Other"


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
    last_visit_at = models.DateTimeField(null=True, blank=True, help_text="Used for the PDPA retention period.")
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

    @property
    def needs_face(self) -> bool:
        """Face verification applies only while the site has the Face check module."""
        return self.require_face and "face_kiosk" in (self.condominium.modules or [])

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


class Visit(TimeStampedModel):
    """One visitor on site: from check-in (created) to check-out.

    Recorded for every way in: a walk-in registered at a kiosk or by security, an invitation QR or
    plate, or a gate opened over the intercom. Every visit gets a pass number that restarts each
    day per condominium, one series per purpose (V001 visitor, C001 contractor, ...), a QR
    (``qr_payload``) and a 4-digit PIN that check the visitor out at a kiosk. The gate is never opened by a visit.
    """

    class Source(models.TextChoices):
        KIOSK = "kiosk", "Walk-in (kiosk)"
        STAFF = "staff", "Walk-in (security)"
        INVITATION = "invitation", "Invitation"
        INTERCOM = "intercom", "Intercom"

    QR_PREFIX = "ELIX-WALKIN:"
    PREFIXES = {
        VisitPurpose.GUEST: "V", VisitPurpose.DELIVERY: "D", VisitPurpose.FOOD: "F",
        VisitPurpose.CONTRACTOR: "C", VisitPurpose.PICKUP: "P", VisitPurpose.OTHER: "O",
    }

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="visits")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="visits")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.KIOSK)
    kiosk = models.ForeignKey("core.Kiosk", on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")
    gate = models.ForeignKey(AccessGate, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")
    invitation = models.ForeignKey(Invitation, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")
    intercom_call = models.ForeignKey(
        "core.IntercomCall", on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")
    entry_log = models.ForeignKey(
        "core.AccessLog", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="The access-log entry that let the visitor in (its photo is shown when the visit has none).")
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")
    visitor_name = models.CharField(max_length=150)
    purpose = models.CharField(max_length=20, choices=VisitPurpose.choices)
    company = models.CharField(max_length=100, blank=True)
    vehicle_plate = models.CharField(max_length=12, blank=True)
    visitor_snapshot = models.ImageField(upload_to="walkins/%Y/%m/", blank=True)
    notes = models.TextField(blank=True, help_text="Security's notes, e.g. items carried or vehicle parked.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Security staff who registered the walk-in.")
    issued_on = models.DateField(help_text="Local date at the condominium; the pass number series restarts daily.")
    sequence = models.PositiveIntegerField()
    pass_number = models.CharField(max_length=12)
    valid_until = models.DateTimeField(help_text="24 hours after arrival: on site until checked out, overnight too.")
    token = models.CharField(max_length=64, unique=True, default=generate_invitation_token, editable=False)
    pin = models.CharField(
        max_length=4, blank=True, editable=False,
        help_text="4 digits on the pass, unique among visitors on site; checks out at the kiosk (and later unit doors).")
    face_descriptor = models.JSONField(
        null=True, blank=True, editable=False,
        help_text="Face template (128 numbers computed in the kiosk browser) for face check-out; "
                  "cleared at check-out and when the pass ends.")
    checked_out_at = models.DateTimeField(null=True, blank=True)
    overstay_notified_at = models.DateTimeField(
        null=True, blank=True, editable=False, help_text="When the guardhouse was told the visitor overstayed (once).")
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Staff member who checked the visitor out; empty when they scanned out or drove out.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["condominium", "issued_on", "pass_number"], name="walkin_pass_number_per_day"),
        ]
        indexes = [
            models.Index(fields=["condominium", "issued_on"]),
            models.Index(fields=["condominium", "-created_at"]),  # The visitor list, newest first.
            models.Index(fields=["unit", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.pass_number} {self.visitor_name} ({self.issued_on})"

    @property
    def qr_payload(self):
        return f"{self.QR_PREFIX}{self.token}"

    @property
    def state(self):
        if self.checked_out_at:
            return "checked_out"
        return "expired" if timezone.now() > self.valid_until else "on_site"

    def photo(self):
        """The best photo of the visitor: the visit's own, else the call's or the check-in snapshot."""
        if self.visitor_snapshot:
            return self.visitor_snapshot
        if self.intercom_call_id and self.intercom_call.visitor_snapshot:
            return self.intercom_call.visitor_snapshot
        if self.entry_log_id and self.entry_log.snapshot:
            return self.entry_log.snapshot
        return None
