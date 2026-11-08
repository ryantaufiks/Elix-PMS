from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import TimeStampedModel
from .devices import AccessGate, Kiosk, LprCamera, RelayController
from .tenancy import Condominium, Unit
from .vehicles import Vehicle
from .visitors import Invitation, Visitor, VisitPurpose


class IntercomCall(TimeStampedModel):
    """A kiosk-to-resident video call (LiveKit room). Primary visitor approval flow."""

    class Status(models.TextChoices):
        RINGING = "ringing", "Ringing"
        ANSWERED = "answered", "Answered"
        APPROVED = "approved", "Approved (gate opened)"
        REJECTED = "rejected", "Rejected"
        MISSED = "missed", "Missed"
        CANCELLED = "cancelled", "Cancelled by kiosk"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="intercom_calls")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="intercom_calls")
    kiosk = models.ForeignKey(Kiosk, on_delete=models.SET_NULL, null=True, blank=True, related_name="calls")
    gate = models.ForeignKey(AccessGate, on_delete=models.SET_NULL, null=True, blank=True, related_name="calls")
    room_name = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RINGING)
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="calls")
    visitor_name = models.CharField(max_length=150, blank=True)
    visitor_purpose = models.CharField(max_length=20, choices=VisitPurpose.choices, blank=True)
    visitor_company = models.CharField(max_length=100, blank=True)
    visitor_snapshot = models.ImageField(upload_to="intercom/%Y/%m/", blank=True)
    face_descriptor = models.JSONField(null=True, blank=True, editable=False,
                                       help_text="Copied to the visit when the resident opens the gate.")
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    OPEN_STATUSES = (Status.RINGING, Status.ANSWERED)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES and self.ended_at is None

    def __str__(self):
        return f"Call {self.room_name} -> {self.unit} [{self.status}]"


class AccessLog(models.Model):
    """Immutable record of every access attempt, granted or not."""

    class Method(models.TextChoices):
        LPR = "lpr", "Licence plate"
        QR = "qr", "Invitation QR"
        INTERCOM = "intercom", "Intercom approval"
        APP = "app", "Resident app"
        MANUAL = "manual", "Manual (staff)"
        WALK_IN = "walk_in", "Walk-in registration"

    class Result(models.TextChoices):
        GRANTED = "granted", "Granted"
        DENIED = "denied", "Denied"
        ERROR = "error", "Error"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="access_logs")
    gate = models.ForeignKey(AccessGate, on_delete=models.SET_NULL, null=True, blank=True, related_name="access_logs")
    occurred_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=20, choices=Method.choices)
    result = models.CharField(max_length=20, choices=Result.choices)
    reason = models.CharField(max_length=255, blank=True)
    plate_number = models.CharField(max_length=12, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="access_logs")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    invitation = models.ForeignKey(Invitation, on_delete=models.SET_NULL, null=True, blank=True, related_name="access_logs")
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="access_logs")
    intercom_call = models.ForeignKey(IntercomCall, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    camera = models.ForeignKey(LprCamera, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    relay = models.ForeignKey(RelayController, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="User who approved or triggered the opening, if any.",
    )
    snapshot = models.ImageField(upload_to="access/%Y/%m/", blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["condominium", "-occurred_at"]),
            models.Index(fields=["plate_number"]),
        ]

    def __str__(self):
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.get_method_display()} {self.result}"
