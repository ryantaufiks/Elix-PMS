from django.core.exceptions import ValidationError
from django.db import models

from core.validators import normalize_plate, validate_plate

from .base import TimeStampedModel
from .tenancy import Condominium, Unit


class Vehicle(TimeStampedModel):
    """A vehicle the LPR cameras let in: a resident's car, a season parking holder's, or a temporary pass
    (a loan car, a contractor's van during renovation). Dates bound when the plate opens the gate."""

    class Kind(models.TextChoices):
        RESIDENT = "resident", "Resident"
        SEASON = "season", "Season parking"
        TEMPORARY = "temporary", "Temporary"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="vehicles")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="vehicles")
    plate_number = models.CharField(max_length=12, validators=[validate_plate])
    make = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=50, blank=True)
    colour = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.RESIDENT)
    holder_name = models.CharField(
        max_length=150, blank=True, help_text="Driver or pass holder when it is not the unit's resident (season parking).")
    valid_from = models.DateField(null=True, blank=True, help_text="First day the plate opens the gate (local date).")
    valid_until = models.DateField(null=True, blank=True, help_text="Last day the plate opens the gate; empty: no end.")

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
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({"valid_until": "Must be on or after the start date."})
        if self.kind in (self.Kind.SEASON, self.Kind.TEMPORARY) and not self.valid_until:
            raise ValidationError({"valid_until": "Season and temporary passes need an end date."})

    def valid_on(self, day):
        """Whether the plate may open the gate on ``day`` (dates only; ``is_active`` is checked separately)."""
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_until is None or day <= self.valid_until)

    def save(self, *args, **kwargs):
        self.plate_number = normalize_plate(self.plate_number)
        if self.unit_id and not self.condominium_id:
            self.condominium_id = self.unit.condominium_id
        super().save(*args, **kwargs)
