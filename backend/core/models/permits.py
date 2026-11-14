import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .base import TimeStampedModel
from .tenancy import Condominium, Unit


def _permit_document_path(permit, filename):
    # A random name: the stored path says nothing about the unit or what the file is.
    return f"permits/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class RenovationPermit(TimeStampedModel):
    """A resident's application to renovate (e-Permit to Work): who works, what, when. The management office
    approves it; approval issues the contractor's vendor pass for the working days and hours of the site."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting deposit"
        SUBMITTED = "submitted", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    class Payment(models.TextChoices):
        NONE = "none", "No deposit"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"

    class Category(models.TextChoices):
        HACKING = "hacking", "Hacking and tiling"
        CARPENTRY = "carpentry", "Carpentry"
        PAINTING = "painting", "Painting"
        ELECTRICAL = "electrical", "Electrical"
        PLUMBING = "plumbing", "Plumbing"
        AIRCON = "aircon", "Air-conditioning"
        OTHER = "other", "Other"

    OPEN_STATUSES = (Status.PENDING_PAYMENT, Status.SUBMITTED, Status.APPROVED)

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="permits")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="permits")
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True, help_text="What will be done, e.g. 'Replace kitchen cabinets'.")
    contractor_company = models.CharField(max_length=100)
    contractor_contact = models.CharField(max_length=100, blank=True)
    contractor_phone = models.CharField(max_length=30, blank=True)
    workers = models.PositiveSmallIntegerField(default=1, help_text="Most workers on site at once.")
    start_date = models.DateField()
    end_date = models.DateField()
    plates = models.JSONField(default=list, blank=True, help_text="Contractor vehicle plates (at most 3).")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    deposit = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="SGD")
    payment_status = models.CharField(max_length=10, choices=Payment.choices, default=Payment.NONE)
    payment_reference = models.CharField(max_length=100, blank=True, db_index=True)
    payment_url = models.URLField(max_length=500, blank=True)
    payment_expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, help_text="Conditions on approval, or why it was rejected.")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    document = models.FileField(upload_to=_permit_document_path, blank=True,
                                help_text="Insurance or drawings, attached by the management office (PDF, JPG, PNG).")
    document_name = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["condominium", "status"])]

    def __str__(self):
        return f"{self.unit} {self.get_category_display()} {self.start_date}–{self.end_date}"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Must be on or after the start date."})
        if not isinstance(self.plates, list) or len(self.plates) > 3:
            raise ValidationError({"plates": "At most 3 vehicle plates."})
        if self.unit_id and self.unit.is_office:
            raise ValidationError({"unit": "Renovation permits are for residents' units."})
