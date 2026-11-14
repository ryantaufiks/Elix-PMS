import secrets
from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.fields import EncryptedTextField

from .base import TimeStampedModel
from .tenancy import Condominium, Unit

WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]  # Monday = 0, as in Python


def default_open_days():
    return list(WEEKDAYS)


class Facility(TimeStampedModel):
    """A bookable facility (BBQ pit, function room, tennis court…), configured by the site admin.

    Bookings are made in slots of ``slot_minutes`` between ``opens_at`` and ``closes_at`` on
    ``open_days``. A price of 0 makes the facility free (confirmed at once); otherwise the resident
    pays online (HitPay) and the booking is confirmed when the payment completes.
    """

    class Kind(models.TextChoices):
        AMENITY = "amenity", "Amenity"
        SERVICE = "service", "Service (lift, loading bay)"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="facilities")
    name = models.CharField(max_length=100)
    kind = models.CharField(
        max_length=10, choices=Kind.choices, default=Kind.AMENITY,
        help_text="Service: booked for moving in or out and renovation deliveries (service lift, loading bay).")
    description = models.TextField(blank=True)
    location = models.CharField(max_length=150, blank=True, help_text="e.g. 'Level 1, next to the pool'.")
    icon = models.CharField(max_length=30, default="event", help_text="Icon shown in the resident app.")
    image = models.ImageField(upload_to="facilities/", blank=True)
    capacity = models.PositiveSmallIntegerField(default=10, help_text="People allowed per booking.")
    opens_at = models.TimeField(default=time(8, 0))
    closes_at = models.TimeField(default=time(22, 0))
    open_days = models.JSONField(default=default_open_days, help_text="Weekdays open, Monday = 0.")
    slot_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(15), MaxValueValidator(720)])
    max_slots_per_booking = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1)])
    concurrent_bookings = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)], help_text="Bookings allowed in the same slot (e.g. 2 for two BBQ pits).")
    price_per_slot = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"),
                                         validators=[MinValueValidator(Decimal("0"))], help_text="0 = free.")
    deposit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"),
                                  validators=[MinValueValidator(Decimal("0"))],
                                  help_text="Refundable deposit paid with the booking (refunded by the management).")
    advance_days = models.PositiveSmallIntegerField(default=14, help_text="How many days ahead residents can book.")
    max_upcoming_per_unit = models.PositiveSmallIntegerField(
        default=2, help_text="Upcoming bookings a unit may hold for this facility (0 = no limit).")
    cancel_hours = models.PositiveSmallIntegerField(
        default=24, help_text="Residents can cancel up to this many hours before the start.")
    rules = models.TextField(blank=True, help_text="Shown before booking, e.g. clean-up and noise rules.")
    no_show_minutes = models.PositiveSmallIntegerField(
        default=0, help_text="Mark a booking no-show when nobody checks in at the kiosk this long after the start. "
                             "0 = off (for sites that do not check in at the kiosk).")
    release_no_shows = models.BooleanField(
        default=False, help_text="Cancel a no-show booking so others can book the rest of the slot (no automatic refund).")
    gate = models.ForeignKey(
        "core.AccessGate", on_delete=models.SET_NULL, null=True, blank=True, related_name="facilities",
        help_text="Door opened when a resident checks in to their booking at the kiosk (optional).")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["condominium", "name"]
        verbose_name_plural = "facilities"
        constraints = [models.UniqueConstraint(fields=["condominium", "name"], name="uniq_facility_name")]

    def __str__(self):
        return self.name

    def clean(self):
        if self.closes_at <= self.opens_at:
            raise ValidationError({"closes_at": "Closing time must be after opening time."})
        days = self.open_days or []
        if not isinstance(days, list) or any(d not in WEEKDAYS for d in days):
            raise ValidationError({"open_days": "Weekdays are numbers 0 (Monday) to 6 (Sunday)."})
        self.open_days = sorted(set(days))

    @property
    def is_paid(self):
        return self.price_per_slot > 0 or self.deposit > 0


def generate_booking_token():
    return secrets.token_urlsafe(24)


class Booking(TimeStampedModel):
    """A unit's booking of a facility. Paid bookings hold their slots while the payment is pending.
    The resident checks in with the booking's QR at the kiosk (``ELIX-BOOKING:<token>``)."""

    QR_PREFIX = "ELIX-BOOKING:"

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Payment expired"

    class Payment(models.TextChoices):
        NONE = "none", "Free"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    ACTIVE_STATUSES = (Status.PENDING_PAYMENT, Status.CONFIRMED)

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="bookings")
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="bookings")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="bookings")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    slots = models.PositiveSmallIntegerField(default=1)
    guests = models.PositiveSmallIntegerField(default=1)
    notes = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
    amount = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"), help_text="Fee + deposit.")
    deposit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="SGD")
    payment_status = models.CharField(max_length=10, choices=Payment.choices, default=Payment.NONE)
    payment_provider = models.CharField(max_length=20, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True, db_index=True, help_text="Provider's payment request id.")
    payment_url = models.URLField(max_length=500, blank=True)
    payment_expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cancel_reason = models.CharField(max_length=255, blank=True)
    checkin_token = models.CharField(max_length=64, unique=True, default=generate_booking_token, editable=False)
    checked_in_at = models.DateTimeField(null=True, blank=True, help_text="First check-in at the kiosk.")
    no_show_at = models.DateTimeField(
        null=True, blank=True, help_text="When nobody had checked in by the facility's no-show time (cleared if they come later).")

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["facility", "starts_at"]), models.Index(fields=["condominium", "-starts_at"])]

    def __str__(self):
        return f"{self.facility} {self.starts_at:%Y-%m-%d %H:%M} ({self.unit})"

    @property
    def qr_payload(self):
        return f"{self.QR_PREFIX}{self.checkin_token}"


class PaymentSettings(TimeStampedModel):
    """The condominium's online payment account (HitPay), for facility bookings. Secrets are encrypted."""

    condominium = models.OneToOneField(Condominium, on_delete=models.CASCADE, related_name="payment_settings")
    enabled = models.BooleanField(default=False)
    sandbox = models.BooleanField(default=True, help_text="Use HitPay's sandbox (test payments) instead of live.")
    hitpay_api_key = EncryptedTextField("HitPay API key", blank=True, default="")
    hitpay_salt = EncryptedTextField("HitPay salt", blank=True, default="", help_text="Verifies HitPay webhooks.")
    currency = models.CharField(max_length=3, default="SGD")
    payment_minutes = models.PositiveSmallIntegerField(
        default=15, validators=[MinValueValidator(5), MaxValueValidator(120)],
        help_text="Slots are held this long while the resident pays.")

    class Meta:
        verbose_name_plural = "payment settings"

    def __str__(self):
        return f"Payments for {self.condominium}"

    @property
    def ready(self):
        return self.enabled and bool(self.hitpay_api_key)
