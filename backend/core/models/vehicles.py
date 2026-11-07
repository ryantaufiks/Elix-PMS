from django.core.exceptions import ValidationError
from django.db import models

from core.validators import normalize_plate, validate_plate

from .base import TimeStampedModel
from .tenancy import Condominium, Unit


class Vehicle(TimeStampedModel):
    """A resident vehicle, recognised by LPR cameras for automatic entry."""

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="vehicles")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="vehicles")
    plate_number = models.CharField(max_length=12, validators=[validate_plate])
    make = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=50, blank=True)
    colour = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["plate_number"]
        constraints = [models.UniqueConstraint(fields=["condominium", "plate_number"], name="uniq_vehicle_plate")]

    def __str__(self):
        return self.plate_number

    def clean(self):
        self.plate_number = normalize_plate(self.plate_number)
        if self.unit_id and not self.condominium_id:
            self.condominium_id = self.unit.condominium_id
        if self.unit_id and self.condominium_id and self.unit.condominium_id != self.condominium_id:
            raise ValidationError({"unit": "Unit belongs to a different condominium."})

    def save(self, *args, **kwargs):
        self.plate_number = normalize_plate(self.plate_number)
        if self.unit_id and not self.condominium_id:
            self.condominium_id = self.unit.condominium_id
        super().save(*args, **kwargs)
