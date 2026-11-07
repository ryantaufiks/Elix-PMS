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
        ADMIN = "admin", "Condo admin"
        SECURITY = "security", "Security guard"

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
