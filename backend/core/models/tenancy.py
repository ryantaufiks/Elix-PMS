from datetime import time

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from core.validators import validate_sg_postal_code

from .base import TimeStampedModel


def default_contractor_days():
    return [0, 1, 2, 3, 4, 5]  # Monday to Saturday


class Condominium(TimeStampedModel):
    """A site (tenant). Every other record belongs to exactly one condominium."""

    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=50, unique=True, help_text="Short unique code, e.g. 'parc-esta'.")
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=6, blank=True, validators=[validate_sg_postal_code])
    timezone = models.CharField(max_length=64, default="Asia/Singapore")
    contact_phone = PhoneNumberField(blank=True)
    is_active = models.BooleanField(default=True)

    modules = ArrayField(
        models.CharField(max_length=30), default=list, blank=True, editable=False,
        help_text="Effective modules from the subscription (kept up to date by core.entitlements).",
    )
    lpr_enabled = models.BooleanField(
        "LPR enabled", default=False,
        help_text="Act on licence-plate events. When off, camera posts are only recorded for inspection.",
    )

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

    # Visitor kiosk
    kiosk_visitor_form = models.BooleanField(
        "Ask visitors for their details", default=True,
        help_text="Name and purpose (and optionally mobile / last 4 of NRIC) before a kiosk rings a unit.",
    )
    kiosk_photo_required = models.BooleanField(
        "Take the visitor's photo", default=True,
        help_text="The kiosk takes a photo, shown to the resident before they answer.",
    )
    kiosk_walk_in = models.BooleanField(
        "Walk-in registration", default=True,
        help_text="Kiosks offer Walk in: visitors register, get a printed slip with a pass number, and show it to security.",
    )
    kiosk_walk_in_photo = models.BooleanField(
        "Photo for walk-ins", default=True, help_text="Take the visitor's photo when they register as a walk-in.",
    )
    kiosk_checkout = models.BooleanField(
        "Self check-out at the kiosk", default=True,
        help_text="Kiosks offer Check out: visitors scan the QR or enter the PIN from their pass when leaving.",
    )
    kiosk_call_guardhouse = models.BooleanField(
        "Call the guardhouse from the kiosk", default=True,
        help_text="Kiosks show Call the guardhouse: a video call that rings the dashboard's Intercom page, "
                  "for visitors who need help or have no unit to visit.",
    )
    kiosk_face_checkout = models.BooleanField(
        "Face check-out at the kiosk", default=False,
        help_text="Visitors whose photo the kiosk took can check out by looking at the camera. The face template "
                  "is matched only against visitors on site and deleted at check-out or when the pass ends.",
    )
    # Season parking bought online (HitPay, the same account as facility bookings).
    season_parking_enabled = models.BooleanField(
        "Sell season parking in the app", default=False,
        help_text="Residents buy season parking for a plate (a visitor's, tenant's or second car) by the month.",
    )
    season_parking_fee = models.DecimalField(
        "Season parking per month", max_digits=8, decimal_places=2, default=0,
        help_text="In the payment account's currency.",
    )
    season_parking_quota = models.PositiveIntegerField(
        "Season parking lots", default=0, help_text="Most season passes valid at once. 0: no limit.",
    )

    # Overstay: when a visitor still on site is flagged and the guardhouse is told.
    overstay_delivery_minutes = models.PositiveIntegerField(
        "Deliveries overstay after (minutes)", default=30,
        help_text="Parcel and food deliveries and pick-ups. 0 turns the alert off.",
    )
    overstay_guest_minutes = models.PositiveIntegerField(
        "Guests overstay after (minutes)", default=240,
        help_text="Guests and other visitors. 0 turns the alert off.",
    )
    overstay_contractor_until = models.TimeField(
        "Contractors overstay after", default=time(18, 0), null=True, blank=True,
        help_text="Local time contractors should have left by. Empty turns the alert off.",
    )
    # Contractor working hours (renovation rules): when on, contractors are let in only then.
    contractor_hours_enforced = models.BooleanField(
        "Keep contractors to working hours", default=False,
        help_text="Kiosk walk-ins, invitations and vendor passes for contractors work only on the days and hours below.",
    )
    contractor_days = models.JSONField(default=default_contractor_days, blank=True,
                                       help_text="Weekdays contractors may work, Monday = 0. Empty: Monday to Saturday.")
    contractor_from = models.TimeField("Contractors may start at", default=time(9, 0))
    visitor_privacy_notice = models.TextField(
        blank=True, help_text="Shown at the kiosk and on visitor passes. Leave blank for the standard notice.",
    )

    class Meta:
        ordering = ["name"]

    @property
    def privacy_notice(self):
        """PDPA notification of purpose: the site's own text, or the standard notice."""
        if self.visitor_privacy_notice.strip():
            return self.visitor_privacy_notice.strip()
        contact = f" on {self.contact_phone}" if self.contact_phone else ""
        return (
            f"{self.name} collects your name, mobile number, the last 4 characters of your NRIC/FIN (if you give "
            "them) and a photo of you, so that the resident you are visiting can see who is at the gate and to keep "
            "the estate secure. They are shared only with that resident and the estate's management and security "
            f"staff, and are deleted after {self.visitor_data_retention_days} days. To access or correct your data, "
            f"or to withdraw consent, contact the management office{contact}."
        )

    def __str__(self):
        return self.name

    def clean(self):
        days = self.contractor_days
        if not isinstance(days, list) or any(d not in range(7) for d in days):
            raise ValidationError({"contractor_days": "Weekdays are numbers 0 (Monday) to 6 (Sunday)."})
        self.contractor_days = sorted(set(days))

    @property
    def resident_app_enabled(self) -> bool:
        return "resident_app" in (self.modules or [])


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
    """A residential unit, labelled Singapore-style as #<floor>-<unit> (e.g. #05-12).

    Each site also has one ``is_office`` unit, the management office: vendors and visitors of the MCST
    are recorded against it. It has no residents and does not count towards the plan's units."""

    OFFICE_NUMBER = "_OFFICE_"  # Never a real unit number.

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="units")
    block = models.ForeignKey(Block, on_delete=models.PROTECT, null=True, blank=True, related_name="units")
    floor = models.CharField(max_length=4, blank=True, help_text="e.g. '05'. Leave blank for landed units.")
    unit_number = models.CharField(max_length=10, help_text="e.g. '12' for #05-12, or the house number.")
    is_active = models.BooleanField(default=True)
    is_office = models.BooleanField(default=False, editable=False, help_text="The site's management office.")

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
        if self.is_office:
            return "Management office"
        return f"#{self.floor}-{self.unit_number}" if self.floor else self.unit_number

    def __str__(self):
        return f"{self.block.name} {self.label}" if self.block_id and not self.is_office else self.label

    @classmethod
    def office_of(cls, condominium_id):
        """The site's management office (created the first time it is needed)."""
        return cls.objects.get_or_create(condominium_id=condominium_id, is_office=True,
                                         defaults={"unit_number": cls.OFFICE_NUMBER})[0]

    def clean(self):
        if self.block_id and self.condominium_id and self.block.condominium_id != self.condominium_id:
            raise ValidationError({"block": "Block belongs to a different condominium."})
