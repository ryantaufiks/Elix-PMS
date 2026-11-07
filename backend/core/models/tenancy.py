from django.core.exceptions import ValidationError
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from core.validators import validate_sg_postal_code

from .base import TimeStampedModel


class Condominium(TimeStampedModel):
    """A site (tenant). Every other record belongs to exactly one condominium."""

    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=50, unique=True, help_text="Short unique code, e.g. 'parc-esta'.")
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=6, blank=True, validators=[validate_sg_postal_code])
    timezone = models.CharField(max_length=64, default="Asia/Singapore")
    contact_phone = PhoneNumberField(blank=True)
    is_active = models.BooleanField(default=True)

    # Visitor policy
    invitation_max_days = models.PositiveSmallIntegerField(
        default=30, help_text="Longest validity window a resident may give an invitation."
    )
    intercom_ring_timeout_seconds = models.PositiveSmallIntegerField(default=45)
    face_verification_enabled = models.BooleanField(
        default=False, help_text="Allow invitations to require face verification at the kiosk."
    )
    visitor_data_retention_days = models.PositiveSmallIntegerField(
        default=90, help_text="PDPA: visitor personal data (incl. face photos) is purged after this many days."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Block(TimeStampedModel):
    """A tower/block within a condominium, e.g. 'Block 12' or 'Tower A'."""

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="blocks")
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ["condominium", "name"]
        constraints = [models.UniqueConstraint(fields=["condominium", "name"], name="uniq_block_name")]

    def __str__(self):
        return f"{self.condominium.code} / {self.name}"


class Unit(TimeStampedModel):
    """A residential unit, labelled Singapore-style as #<floor>-<unit> (e.g. #05-12)."""

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="units")
    block = models.ForeignKey(Block, on_delete=models.PROTECT, null=True, blank=True, related_name="units")
    floor = models.CharField(max_length=4, blank=True, help_text="e.g. '05'. Leave blank for landed units.")
    unit_number = models.CharField(max_length=10, help_text="e.g. '12' for #05-12, or the house number.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["condominium", "block__name", "floor", "unit_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["condominium", "block", "floor", "unit_number"],
                name="uniq_unit",
                nulls_distinct=False,
            )
        ]

    @property
    def label(self):
        return f"#{self.floor}-{self.unit_number}" if self.floor else self.unit_number

    def __str__(self):
        return f"{self.block.name} {self.label}" if self.block_id else self.label

    def clean(self):
        if self.block_id and self.condominium_id and self.block.condominium_id != self.condominium_id:
            raise ValidationError({"block": "Block belongs to a different condominium."})
