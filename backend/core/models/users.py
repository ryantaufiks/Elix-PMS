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
