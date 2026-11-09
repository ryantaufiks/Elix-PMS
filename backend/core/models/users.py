import uuid
from pathlib import Path

from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from .base import TimeStampedModel
from .tenancy import Condominium, Unit


class User(AbstractUser):
    phone = PhoneNumberField(blank=True)


class StaffAssignment(TimeStampedModel):
    """Gives a user a staff role at one condominium."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Site admin"
        STAFF = "staff", "Staff"
        SECURITY = "security", "Officer"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_assignments")
    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="staff_assignments")
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "condominium"], name="uniq_staff_assignment")]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} @ {self.condominium.code}"


class Residency(TimeStampedModel):
    """Links a resident user to a unit."""

    class ResidentType(models.TextChoices):
        OWNER = "owner", "Owner"
        TENANT = "tenant", "Tenant"
        FAMILY = "family", "Family member"
        HELPER = "helper", "Domestic helper"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="residencies")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="residencies")
    resident_type = models.CharField(max_length=20, choices=ResidentType.choices, default=ResidentType.OWNER)
    is_primary_contact = models.BooleanField(default=False)
    receives_intercom_calls = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "residencies"
        constraints = [models.UniqueConstraint(fields=["user", "unit"], name="uniq_residency")]

    def __str__(self):
        return f"{self.user} @ {self.unit}"

    @property
    def condominium(self):
        return self.unit.condominium


def _document_path(document, filename):
    # A random name: the stored path says nothing about the person or what the file is.
    return f"documents/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class ResidentDocument(TimeStampedModel):
    """A file the management keeps for a resident at a unit (proof of ownership, tenancy agreement…).

    Uploaded by the management, usually before the resident's account exists; the resident sees their
    own documents in the app. Files are only served through the API, never as public media."""

    class Kind(models.TextChoices):
        OWNERSHIP = "ownership", "Proof of ownership"
        TENANCY = "tenancy", "Tenancy agreement"
        IDENTITY = "identity", "Identity document"
        OTHER = "other", "Other"

    residency = models.ForeignKey(Residency, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to=_document_path)
    file_name = models.CharField(max_length=255, help_text="Name of the uploaded file, offered when downloading.")
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class PushDevice(TimeStampedModel):
    """A resident/staff phone registered for push notifications (Firebase Cloud Messaging)."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_devices")
    platform = models.CharField(max_length=10, choices=Platform.choices)
    token = models.CharField(max_length=4096, unique=True)
    app_version = models.CharField(max_length=30, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} ({self.platform})"
