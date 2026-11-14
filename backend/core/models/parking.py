from decimal import Decimal

from django.conf import settings
from django.db import models

from .base import TimeStampedModel
from .tenancy import Condominium, Unit
from .vehicles import Vehicle


class ParkingPermit(TimeStampedModel):
    """A season parking purchase: a resident pays online for a plate (their visitor's, tenant's, a second car)
    for some months; once paid, the plate's Season parking pass starts or is extended to ``ends_on``."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        PAID = "paid", "Paid"
        EXPIRED = "expired", "Not paid in time"
        CANCELLED = "cancelled", "Cancelled"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="parking_permits")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="parking_permits")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="permits",
                                help_text="The pass this purchase started or extended (set once paid).")
    plate_number = models.CharField(max_length=12)
    holder_name = models.CharField(max_length=150, blank=True)
    months = models.PositiveSmallIntegerField()
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
    amount = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="SGD")
    payment_reference = models.CharField(max_length=100, blank=True, db_index=True, help_text="HitPay payment request id.")
    payment_url = models.URLField(max_length=500, blank=True)
    payment_expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["condominium", "-created_at"])]

    def __str__(self):
        return f"{self.plate_number} {self.starts_on}–{self.ends_on} ({self.get_status_display()})"
