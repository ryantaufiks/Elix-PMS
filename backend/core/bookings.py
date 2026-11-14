"""Facility bookings: availability, booking rules, payment confirmation and cancellation."""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import payments
from .models import Booking, Facility, PaymentSettings
from .realtime import broadcast

log = logging.getLogger(__name__)


class BookingError(Exception):
    pass


def tz(facility):
    return ZoneInfo(facility.condominium.timezone or "Asia/Singapore")


def holding(qs, now=None):
    """Bookings that hold their slots: confirmed, or awaiting a payment that has not expired."""
    now = now or timezone.now()
    return qs.filter(Q(status=Booking.Status.CONFIRMED) |
                     Q(status=Booking.Status.PENDING_PAYMENT, payment_expires_at__gt=now))


def slots_of(facility, day):
    """[(start, end)] aware datetimes of the facility's slots on ``day`` (none when it is closed)."""
    if day.weekday() not in (facility.open_days or []):
        return []
    zone = tz(facility)
    start = datetime.combine(day, facility.opens_at, tzinfo=zone)
    close = datetime.combine(day, facility.closes_at, tzinfo=zone)
    step = timedelta(minutes=facility.slot_minutes)
    out = []
    while start + step <= close:
        out.append((start, start + step))
        start += step
    return out


def availability(facility, day, now=None):
    """Every slot of ``day`` with how many more bookings it takes (0 = full, or in the past)."""
    now = now or timezone.now()
    slots = slots_of(facility, day)
    if not slots:
        return []
    taken = list(holding(facility.bookings.filter(starts_at__lt=slots[-1][1], ends_at__gt=slots[0][0]), now)
                 .values_list("starts_at", "ends_at"))
    out = []
    for start, end in slots:
        used = sum(1 for s, e in taken if s < end and e > start)
        left = 0 if start <= now else max(0, facility.concurrent_bookings - used)
        out.append({"starts_at": start, "ends_at": end, "available": left > 0, "left": left})
    return out


# A resident may check in this long before their booking starts (and until it ends).
CHECKIN_EARLY = timedelta(minutes=15)


def today_schedule(facility, now=None):
    """The rest of today's slots at ``facility`` for the kiosk: booked or free, and whether it is the current
    one. No names or units: anyone in the lobby can read it."""
    now = now or timezone.now()
    slots = slots_of(facility, now.astimezone(tz(facility)).date())
    if not slots:
        return []
    taken = list(holding(facility.bookings.filter(starts_at__lt=slots[-1][1], ends_at__gt=slots[0][0]), now)
                 .values_list("starts_at", "ends_at"))
    out = []
    for start, end in slots:
        if end <= now:
            continue
        used = sum(1 for s, e in taken if s < end and e > start)
        out.append({"starts_at": start, "ends_at": end, "booked": used >= facility.concurrent_bookings,
                    "left": max(0, facility.concurrent_bookings - used), "now": start <= now < end})
    return out


def check_in(condominium_id, code, now=None):
    """Check a resident in with their booking QR. Returns (booking or None, problem): an empty problem means
    welcome. Opening the facility's door is left to the caller."""
    now = now or timezone.now()
    code = (code or "").strip()
    if not code.startswith(Booking.QR_PREFIX):
        return None, "This is not a facility booking QR code."
    booking = (Booking.objects.select_related("facility__gate", "unit__block")
               .filter(condominium_id=condominium_id, checkin_token=code[len(Booking.QR_PREFIX):]).first())
    if booking is None:
        return None, "This booking was not found at this condominium."
    if booking.status != Booking.Status.CONFIRMED:
        return booking, f"This booking is {booking.get_status_display().lower()}."
    if now < booking.starts_at - CHECKIN_EARLY:
        local = booking.starts_at.astimezone(tz(booking.facility))
        return booking, f"Too early: check in from {(local - CHECKIN_EARLY):%H:%M}" + ("" if local.date() == now.astimezone(tz(booking.facility)).date() else f" on {local:%a %d %b}") + "."
    if now >= booking.ends_at:
        return booking, "This booking has ended."
    if booking.checked_in_at is None:
        booking.checked_in_at, booking.no_show_at = now, None  # Late, but here: no longer a no-show.
        booking.save(update_fields=["checked_in_at", "no_show_at", "updated_at"])
        notify(booking)
    return booking, ""


def mark_no_shows(now=None):
    """Flag confirmed bookings nobody checked in to within their facility's no-show time; facilities set to
    release no-shows cancel them so the rest of the slot can be booked. Returns how many were flagged."""
    now = now or timezone.now()
    due = (Booking.objects.select_related("facility")
           .filter(status=Booking.Status.CONFIRMED, checked_in_at__isnull=True, no_show_at__isnull=True,
                   facility__no_show_minutes__gt=0, starts_at__lte=now, ends_at__gt=now - timedelta(days=1)))
    count = 0
    for booking in due:
        if booking.starts_at + timedelta(minutes=booking.facility.no_show_minutes) > now:
            continue
        booking.no_show_at = now
        if booking.facility.release_no_shows and booking.ends_at > now:
            booking.status, booking.cancelled_at = Booking.Status.CANCELLED, now
            booking.cancel_reason = f"No-show: nobody checked in within {booking.facility.no_show_minutes} minutes."
        booking.save()
        notify(booking)
        count += 1
    return count


def bookable_days(facility, today=None):
    today = today or timezone.localdate(timezone=tz(facility))
    return today, today + timedelta(days=facility.advance_days)


def price(facility, slots):
    return facility.price_per_slot * slots + facility.deposit


@transaction.atomic
def book(facility, unit, user, starts_at, slots, *, guests=1, notes=""):
    """Book ``slots`` consecutive slots from ``starts_at``. Free facilities are confirmed at once;
    paid ones wait for payment (call ``start_payment`` next)."""
    facility = Facility.objects.select_for_update().select_related("condominium").get(pk=facility.pk)
    now = timezone.now()
    if not facility.is_active:
        raise BookingError("This facility is not available for booking.")
    if unit.condominium_id != facility.condominium_id:
        raise BookingError("This facility belongs to another condominium.")
    if not 1 <= slots <= facility.max_slots_per_booking:
        raise BookingError(f"Book between 1 and {facility.max_slots_per_booking} slot(s).")
    if guests < 1 or guests > facility.capacity:
        raise BookingError(f"At most {facility.capacity} people per booking.")
    local = starts_at.astimezone(tz(facility))
    first, last = bookable_days(facility)
    if local.date() < first or local.date() > last:
        raise BookingError(f"Bookings open {facility.advance_days} days ahead.")
    day_slots = slots_of(facility, local.date())
    starts = [s for s, _ in day_slots]
    if local not in starts:
        raise BookingError("Pick one of the facility's time slots.")
    index = starts.index(local)
    if index + slots > len(day_slots):
        raise BookingError("The booking would run past closing time.")
    if local <= now:
        raise BookingError("That slot has already started.")
    ends_at = day_slots[index + slots - 1][1]
    if not all(s["available"] for s in availability(facility, local.date(), now)[index:index + slots]):
        raise BookingError("Sorry, that time has just been booked. Please pick another slot.")
    if facility.max_upcoming_per_unit:
        upcoming = holding(facility.bookings.filter(unit=unit, ends_at__gt=now), now).count()
        if upcoming >= facility.max_upcoming_per_unit:
            raise BookingError(f"Your unit already has {upcoming} upcoming booking(s) for {facility.name}.")

    amount = price(facility, slots)
    booking = Booking(condominium_id=facility.condominium_id, facility=facility, unit=unit, user=user,
                      starts_at=local, ends_at=ends_at, slots=slots, guests=guests, notes=notes[:255],
                      amount=amount, deposit=facility.deposit)
    if amount > 0:
        settings = PaymentSettings.objects.filter(condominium_id=facility.condominium_id).first()
        if settings is None or not settings.ready:
            raise BookingError("Online payment is not set up for this condominium yet. Please contact the management office.")
        booking.currency = settings.currency
        booking.status = Booking.Status.PENDING_PAYMENT
        booking.payment_status = Booking.Payment.PENDING
        booking.payment_provider = "hitpay"
        booking.payment_expires_at = now + timedelta(minutes=settings.payment_minutes)
    else:
        booking.status = Booking.Status.CONFIRMED
        booking.payment_status = Booking.Payment.NONE
    booking.save()
    notify(booking)
    return booking


def start_payment(booking, *, redirect_url, webhook_url):
    """Create the HitPay request for a pending booking (or reuse its link). Releases the slots if HitPay fails."""
    if booking.status != Booking.Status.PENDING_PAYMENT:
        raise BookingError("This booking is not awaiting payment.")
    if booking.payment_url and booking.payment_reference:
        return booking.payment_url
    settings = PaymentSettings.objects.get(condominium_id=booking.condominium_id)
    try:
        reference, url = payments.create_request(
            settings, amount=booking.amount, currency=booking.currency, reference=f"booking-{booking.pk}",
            purpose=f"{booking.facility.name} {booking.starts_at:%d %b %Y %H:%M} ({booking.unit})", user=booking.user,
            redirect_url=redirect_url, webhook_url=webhook_url)
    except payments.PaymentError as exc:
        Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.EXPIRED, payment_status=Booking.Payment.FAILED,
                                                     updated_at=timezone.now())
        raise BookingError(str(exc))
    booking.payment_reference, booking.payment_url = reference, url
    booking.save(update_fields=["payment_reference", "payment_url", "updated_at"])
    return url


@transaction.atomic
def refresh_payment(booking):
    """Ask HitPay how the payment went and update the booking. Returns the (re-read) booking."""
    booking = Booking.objects.select_for_update().select_related("facility", "unit").get(pk=booking.pk)
    if booking.payment_status != Booking.Payment.PENDING or not booking.payment_reference:
        return expire_if_stale(booking)
    settings = PaymentSettings.objects.get(condominium_id=booking.condominium_id)
    status = payments.fetch_status(settings, booking.payment_reference)
    now = timezone.now()
    if status == "completed":
        booking.payment_status, booking.paid_at = Booking.Payment.PAID, now
        if booking.status == Booking.Status.PENDING_PAYMENT:
            booking.status = Booking.Status.CONFIRMED
        elif booking.status == Booking.Status.EXPIRED:
            # Paid after the hold ran out: keep it if the slots are still free, otherwise flag a refund.
            clash = holding(booking.facility.bookings.exclude(pk=booking.pk).filter(
                starts_at__lt=booking.ends_at, ends_at__gt=booking.starts_at), now).count()
            if clash < booking.facility.concurrent_bookings and booking.starts_at > now:
                booking.status = Booking.Status.CONFIRMED
            else:
                booking.status, booking.cancelled_at = Booking.Status.CANCELLED, now
                booking.cancel_reason = "Paid after the slot was released: refund due."
        booking.save()
        notify(booking)
    elif status in ("failed", "expired", "canceled", "cancelled"):
        booking.payment_status = Booking.Payment.FAILED
        if booking.status == Booking.Status.PENDING_PAYMENT:
            booking.status = Booking.Status.EXPIRED
        booking.save()
        notify(booking)
    else:
        booking = expire_if_stale(booking)
    return booking


def expire_if_stale(booking):
    if booking.status == Booking.Status.PENDING_PAYMENT and booking.payment_expires_at and booking.payment_expires_at <= timezone.now():
        booking.status = Booking.Status.EXPIRED
        booking.save(update_fields=["status", "updated_at"])
        notify(booking)
    return booking


def expire_stale():
    """Release slots whose payment window ran out (after one last look at HitPay). Returns how many expired."""
    stale = Booking.objects.filter(status=Booking.Status.PENDING_PAYMENT, payment_expires_at__lte=timezone.now())
    count = 0
    for booking in stale:
        if refresh_payment(booking).status == Booking.Status.EXPIRED:
            count += 1
    return count


@transaction.atomic
def cancel(booking, user, *, staff, reason=""):
    booking = Booking.objects.select_for_update().select_related("facility").get(pk=booking.pk)
    if booking.status not in Booking.ACTIVE_STATUSES:
        raise BookingError("This booking is already closed.")
    now = timezone.now()
    if not staff:
        if booking.starts_at - now < timedelta(hours=booking.facility.cancel_hours):
            raise BookingError(f"Bookings can be cancelled up to {booking.facility.cancel_hours} hours before the start. "
                               "Please contact the management office.")
    booking.status, booking.cancelled_at, booking.cancelled_by = Booking.Status.CANCELLED, now, user
    booking.cancel_reason = reason[:255] or ("Cancelled by the management" if staff else "Cancelled by the resident")
    if booking.payment_status == Booking.Payment.PENDING:
        booking.payment_status = Booking.Payment.FAILED
    booking.save()
    notify(booking)
    return booking


def mark_refunded(booking):
    if booking.payment_status != Booking.Payment.PAID:
        raise BookingError("Only paid bookings can be marked refunded.")
    booking.payment_status = Booking.Payment.REFUNDED
    booking.save(update_fields=["payment_status", "updated_at"])
    notify(booking)
    return booking


def notify(booking):
    def send():
        from .serializers import BookingSerializer

        try:
            broadcast(booking.condominium_id, booking.unit_id, "booking", BookingSerializer(booking).data)
        except Exception:  # Redis trouble must not break bookings.
            log.exception("Failed to broadcast booking %s", booking.pk)

    transaction.on_commit(send)


def to_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise BookingError("Dates are YYYY-MM-DD.")

