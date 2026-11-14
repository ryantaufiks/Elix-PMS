"""Season parking bought online: the offer, the purchase, its HitPay payment and the pass it turns on.

A purchase (ParkingPermit) waits for payment like a paid booking. Once HitPay says it is paid, the plate's
Season parking pass (a Vehicle) is created or extended, and the LPR cameras let it in until ``ends_on``.
"""
import calendar
import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from . import entitlements, payments
from .models import Condominium, ParkingPermit, PaymentSettings, Vehicle
from .realtime import broadcast
from .validators import normalize_plate

log = logging.getLogger(__name__)

MONTHS = (1, 3, 6, 12)


class ParkingError(Exception):
    pass


def add_months(day, months):
    """The day before the same date ``months`` later: 1 month from 14 Nov runs to 13 Dec."""
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1])) - timedelta(days=1)


def _active_passes(condo, today, exclude_plate=""):
    return (Vehicle.objects.filter(condominium=condo, kind=Vehicle.Kind.SEASON, is_active=True, valid_until__gte=today)
            .exclude(plate_number=exclude_plate))


def lots_left(condo, plate=""):
    """Season passes that can still be sold now (None: no limit). Renewing a plate never needs a new lot."""
    if not condo.season_parking_quota:
        return None
    today = timezone.localdate()
    pending = ParkingPermit.objects.filter(condominium=condo, status=ParkingPermit.Status.PENDING_PAYMENT,
                                           payment_expires_at__gt=timezone.now()).exclude(plate_number=plate)
    taken = _active_passes(condo, today, plate).count() + pending.values("plate_number").distinct().count()
    return max(0, condo.season_parking_quota - taken)


def offer(condo):
    settings = PaymentSettings.objects.filter(condominium=condo).first()
    return {
        "enabled": (entitlements.has(condo, "facilities") and condo.season_parking_enabled and condo.season_parking_fee > 0
                    and bool(settings and settings.ready)),
        "monthly_fee": condo.season_parking_fee,
        "currency": settings.currency if settings else "SGD",
        "months": list(MONTHS),
        "lots_left": lots_left(condo),
    }


def period(condo, plate, months):
    """(starts_on, ends_on): a renewal carries on from the day after the current pass ends."""
    today = timezone.localdate()
    current = Vehicle.objects.filter(condominium=condo, plate_number=plate, kind=Vehicle.Kind.SEASON,
                                     valid_until__gte=today).first()
    start = current.valid_until + timedelta(days=1) if current else today
    return start, add_months(start, months)


@transaction.atomic
def buy(unit, user, plate, months, holder_name=""):
    """Start a purchase for ``plate`` (call ``start_payment`` next)."""
    condo = Condominium.objects.select_for_update().get(pk=unit.condominium_id)  # Serialises the lot count.
    plate = normalize_plate(plate)
    if not entitlements.has(condo, "facilities") or not condo.season_parking_enabled or condo.season_parking_fee <= 0:
        raise ParkingError("Season parking is not sold online at this condominium. Please contact the management office.")
    settings = PaymentSettings.objects.filter(condominium=condo).first()
    if settings is None or not settings.ready:
        raise ParkingError("Online payment is not set up for this condominium yet. Please contact the management office.")
    if months not in MONTHS:
        raise ParkingError(f"Choose {', '.join(map(str, MONTHS))} months.")
    if not plate:
        raise ParkingError("Enter the plate number.")
    other = Vehicle.objects.filter(condominium=condo, plate_number=plate).exclude(unit=unit).first()
    if other is not None:
        raise ParkingError(f"{plate} is registered to another unit. Please contact the management office.")
    resident = Vehicle.objects.filter(condominium=condo, plate_number=plate, kind=Vehicle.Kind.RESIDENT).first()
    if resident is not None:
        raise ParkingError(f"{plate} already parks as a resident's car.")
    left = lots_left(condo, plate)
    if left is not None and left <= 0:
        raise ParkingError("All season parking lots are taken. Please contact the management office.")
    starts_on, ends_on = period(condo, plate, months)
    now = timezone.now()
    return ParkingPermit.objects.create(
        condominium=condo, unit=unit, user=user, plate_number=plate, holder_name=holder_name.strip()[:150],
        months=months, starts_on=starts_on, ends_on=ends_on, amount=condo.season_parking_fee * months,
        currency=settings.currency, payment_expires_at=now + timedelta(minutes=settings.payment_minutes))


def start_payment(permit, *, redirect_url, webhook_url):
    """The HitPay link for a purchase awaiting payment (created once)."""
    if permit.status != ParkingPermit.Status.PENDING_PAYMENT:
        raise ParkingError("This purchase is not awaiting payment.")
    if permit.payment_url and permit.payment_reference:
        return permit.payment_url
    settings = PaymentSettings.objects.get(condominium_id=permit.condominium_id)
    try:
        reference, url = payments.create_request(
            settings, amount=permit.amount, currency=permit.currency, reference=f"parking-{permit.pk}",
            purpose=f"Season parking {permit.plate_number} {permit.starts_on:%d %b %Y}–{permit.ends_on:%d %b %Y} ({permit.unit})",
            user=permit.user, redirect_url=redirect_url, webhook_url=webhook_url)
    except payments.PaymentError as exc:
        ParkingPermit.objects.filter(pk=permit.pk).update(status=ParkingPermit.Status.EXPIRED, updated_at=timezone.now())
        raise ParkingError(str(exc))
    permit.payment_reference, permit.payment_url = reference, url
    permit.save(update_fields=["payment_reference", "payment_url", "updated_at"])
    return url


def _activate(permit):
    """Start or extend the plate's Season parking pass to cover the purchase."""
    vehicle = Vehicle.objects.filter(condominium_id=permit.condominium_id, plate_number=permit.plate_number).first() \
        or Vehicle(condominium_id=permit.condominium_id, unit=permit.unit, plate_number=permit.plate_number)
    carries_on = bool(vehicle.pk and vehicle.kind == Vehicle.Kind.SEASON and vehicle.is_active and vehicle.valid_until
                      and vehicle.valid_until >= permit.starts_on - timedelta(days=1))
    if carries_on:
        vehicle.valid_until = max(vehicle.valid_until, permit.ends_on)
    else:  # New, lapsed or another kind of pass: the paid period starts afresh.
        vehicle.valid_from, vehicle.valid_until = permit.starts_on, permit.ends_on
    vehicle.kind, vehicle.is_active = Vehicle.Kind.SEASON, True
    if permit.holder_name:
        vehicle.holder_name = permit.holder_name
    vehicle.save()
    permit.vehicle = vehicle


@transaction.atomic
def refresh_payment(permit):
    """Ask HitPay how the payment went; a paid purchase turns the pass on. Returns the re-read purchase."""
    permit = ParkingPermit.objects.select_for_update().select_related("unit").get(pk=permit.pk)
    if permit.status != ParkingPermit.Status.PENDING_PAYMENT or not permit.payment_reference:
        return expire_if_stale(permit)
    settings = PaymentSettings.objects.get(condominium_id=permit.condominium_id)
    state = payments.fetch_status(settings, permit.payment_reference)
    if state == "completed":
        permit.status, permit.paid_at = ParkingPermit.Status.PAID, timezone.now()
        _activate(permit)
        permit.save()
        notify(permit)
    elif state in ("failed", "expired", "canceled", "cancelled"):
        permit.status = ParkingPermit.Status.EXPIRED
        permit.save(update_fields=["status", "updated_at"])
        notify(permit)
    else:
        permit = expire_if_stale(permit)
    return permit


def expire_if_stale(permit):
    if permit.status == ParkingPermit.Status.PENDING_PAYMENT and permit.payment_expires_at \
            and permit.payment_expires_at <= timezone.now():
        permit.status = ParkingPermit.Status.EXPIRED
        permit.save(update_fields=["status", "updated_at"])
        notify(permit)
    return permit


def expire_stale():
    """Close purchases not paid in time, after one last look at HitPay. Returns how many expired."""
    stale = ParkingPermit.objects.filter(status=ParkingPermit.Status.PENDING_PAYMENT, payment_expires_at__lte=timezone.now())
    return sum(refresh_payment(p).status == ParkingPermit.Status.EXPIRED for p in stale)


def from_reference(data):
    """The purchase a HitPay callback is about (by its payment request id or our reference), or None."""
    reference = data.get("payment_request_id") or data.get("id") or ""
    permit = ParkingPermit.objects.filter(payment_reference=reference).first() if reference else None
    number = str(data.get("reference_number") or "")
    if permit is None and number.startswith("parking-") and number[8:].isdigit():
        permit = ParkingPermit.objects.filter(pk=int(number[8:])).first()
    return permit


def notify(permit):
    def send():
        from .serializers import ParkingPermitSerializer

        try:
            broadcast(permit.condominium_id, permit.unit_id, "parking_permit", ParkingPermitSerializer(permit).data)
        except Exception:  # Redis trouble must not break payments.
            log.exception("Failed to broadcast parking permit %s", permit.pk)

    transaction.on_commit(send)
