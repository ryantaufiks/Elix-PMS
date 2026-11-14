"""e-Permit to Work: a resident applies to renovate, pays the deposit if the site asks for one, and the
management office approves or rejects. Approval issues the contractor's vendor pass for the permit's dates on
the site's contractor days and hours (plus one pass per vehicle plate); cancelling, rejecting or completing the
permit ends them. Deposits are refunded through HitPay's dashboard and recorded here.
"""
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from . import entitlements, payments
from .models import Invitation, PaymentSettings, RenovationPermit
from .realtime import broadcast
from .validators import normalize_plate

log = logging.getLogger(__name__)

Status = RenovationPermit.Status
Payment = RenovationPermit.Payment


class PermitError(Exception):
    pass


def deposit_settings(condo):
    """(deposit, payment settings) when the site takes the deposit online, else (0, None)."""
    settings = PaymentSettings.objects.filter(condominium=condo).first()
    if condo.renovation_deposit > 0 and entitlements.has(condo, "facilities") and settings and settings.ready:
        return condo.renovation_deposit, settings
    return 0, None


@transaction.atomic
def apply(unit, user, **data):
    """A resident's application. With an online deposit it waits for payment (call ``start_payment``)."""
    condo = unit.condominium
    if not condo.renovation_permits_enabled:
        raise PermitError("Renovation permits are not taken in the app at this condominium. Please contact the management office.")
    if data["start_date"] < timezone.localdate():
        raise PermitError("The start date has passed.")
    plates = list(dict.fromkeys(p for p in (normalize_plate(x) for x in data.pop("plates", [])) if p))
    permit = RenovationPermit(condominium=condo, unit=unit, applicant=user, plates=plates, **data)
    deposit, settings = deposit_settings(condo)
    if deposit:
        permit.deposit, permit.currency = deposit, settings.currency
        permit.status, permit.payment_status = Status.PENDING_PAYMENT, Payment.PENDING
        permit.payment_expires_at = timezone.now() + timedelta(minutes=settings.payment_minutes)
    permit.full_clean()
    permit.save()
    notify(permit)
    return permit


def start_payment(permit, *, redirect_url, webhook_url):
    if permit.status != Status.PENDING_PAYMENT:
        raise PermitError("This permit is not awaiting its deposit.")
    if permit.payment_url and permit.payment_reference:
        return permit.payment_url
    settings = PaymentSettings.objects.get(condominium_id=permit.condominium_id)
    try:
        reference, url = payments.create_request(
            settings, amount=permit.deposit, currency=permit.currency, reference=f"permit-{permit.pk}",
            purpose=f"Renovation deposit {permit.unit} {permit.start_date:%d %b}–{permit.end_date:%d %b %Y}",
            user=permit.applicant, redirect_url=redirect_url, webhook_url=webhook_url)
    except payments.PaymentError as exc:
        RenovationPermit.objects.filter(pk=permit.pk).update(status=Status.CANCELLED, payment_status=Payment.NONE,
                                                             updated_at=timezone.now())
        raise PermitError(str(exc))
    permit.payment_reference, permit.payment_url = reference, url
    permit.save(update_fields=["payment_reference", "payment_url", "updated_at"])
    return url


@transaction.atomic
def refresh_payment(permit):
    """Ask HitPay about the deposit; once paid the application goes to the management office."""
    permit = RenovationPermit.objects.select_for_update().get(pk=permit.pk)
    if permit.status != Status.PENDING_PAYMENT or not permit.payment_reference:
        return expire_if_stale(permit)
    settings = PaymentSettings.objects.get(condominium_id=permit.condominium_id)
    state = payments.fetch_status(settings, permit.payment_reference)
    if state == "completed":
        permit.status, permit.payment_status, permit.paid_at = Status.SUBMITTED, Payment.PAID, timezone.now()
        permit.save()
        notify(permit)
    elif state in ("failed", "expired", "canceled", "cancelled"):
        permit.status, permit.payment_status = Status.CANCELLED, Payment.NONE
        permit.save()
        notify(permit)
    else:
        permit = expire_if_stale(permit)
    return permit


def expire_if_stale(permit):
    if permit.status == Status.PENDING_PAYMENT and permit.payment_expires_at and permit.payment_expires_at <= timezone.now():
        permit.status, permit.payment_status = Status.CANCELLED, Payment.NONE
        permit.save(update_fields=["status", "payment_status", "updated_at"])
        notify(permit)
    return permit


def expire_stale():
    stale = RenovationPermit.objects.filter(status=Status.PENDING_PAYMENT, payment_expires_at__lte=timezone.now())
    return sum(refresh_payment(p).status == Status.CANCELLED for p in stale)


def _issue_passes(permit, user):
    """The contractor's vendor pass: the permit's dates, the site's contractor days and hours."""
    condo = permit.condominium
    tz = ZoneInfo(condo.timezone or "Asia/Singapore")
    common = {
        "condominium": condo, "unit": permit.unit, "host": permit.applicant or user, "purpose": Invitation.Purpose.CONTRACTOR,
        "company": permit.contractor_company, "permit": permit, "max_entries": 0,
        "valid_from": datetime.combine(permit.start_date, time.min, tzinfo=tz),
        "valid_until": datetime.combine(permit.end_date, time(23, 59), tzinfo=tz),
        "weekdays": condo.contractor_days or [0, 1, 2, 3, 4, 5],
        "daily_from": condo.contractor_from, "daily_until": condo.overstay_contractor_until,
        "notes": f"Renovation permit: {permit.get_category_display()}",
    }
    Invitation.objects.create(visitor_name=permit.contractor_contact or permit.contractor_company,
                              visitor_phone=permit.contractor_phone or "", **common)
    for plate in permit.plates:
        Invitation.objects.create(visitor_name=f"{permit.contractor_company} vehicle", vehicle_plate=plate, **common)


def _end_passes(permit):
    for invitation in permit.invitations.filter(status=Invitation.Status.ACTIVE):
        invitation.cancel()


@transaction.atomic
def decide(permit, user, approve, note=""):
    permit = RenovationPermit.objects.select_for_update().select_related("condominium", "unit").get(pk=permit.pk)
    if permit.status != Status.SUBMITTED:
        raise PermitError(f"This permit is {permit.get_status_display().lower()}.")
    permit.status = Status.APPROVED if approve else Status.REJECTED
    permit.decision_note, permit.decided_by, permit.decided_at = note.strip()[:255], user, timezone.now()
    permit.save()
    if approve:
        _issue_passes(permit, user)
    notify(permit)
    return permit


@transaction.atomic
def close(permit, user, status, staff):
    """Cancel (the resident, before approval; the office, any time) or complete (the office) a permit."""
    permit = RenovationPermit.objects.select_for_update().get(pk=permit.pk)
    if permit.status not in RenovationPermit.OPEN_STATUSES:
        raise PermitError(f"This permit is already {permit.get_status_display().lower()}.")
    if status == Status.COMPLETED and (not staff or permit.status != Status.APPROVED):
        raise PermitError("The management office completes an approved permit.")
    if status == Status.CANCELLED and not staff and permit.status == Status.APPROVED:
        raise PermitError("This permit is approved: please ask the management office to cancel it.")
    permit.status = status
    if status == Status.COMPLETED:
        permit.completed_at = timezone.now()
    if permit.payment_status == Payment.PENDING:
        permit.payment_status = Payment.NONE
    permit.save()
    _end_passes(permit)
    notify(permit)
    return permit


def mark_refunded(permit):
    if permit.payment_status != Payment.PAID or permit.status in (Status.PENDING_PAYMENT, Status.SUBMITTED, Status.APPROVED):
        raise PermitError("Refund the deposit of a permit that is completed, rejected or cancelled.")
    permit.payment_status, permit.refunded_at = Payment.REFUNDED, timezone.now()
    permit.save(update_fields=["payment_status", "refunded_at", "updated_at"])
    notify(permit)
    return permit


def from_reference(data):
    reference = data.get("payment_request_id") or data.get("id") or ""
    permit = RenovationPermit.objects.filter(payment_reference=reference).first() if reference else None
    number = str(data.get("reference_number") or "")
    if permit is None and number.startswith("permit-") and number[7:].isdigit():
        permit = RenovationPermit.objects.filter(pk=int(number[7:])).first()
    return permit


def notify(permit):
    def send():
        from .serializers import RenovationPermitSerializer

        try:
            broadcast(permit.condominium_id, permit.unit_id, "permit", RenovationPermitSerializer(permit).data)
        except Exception:  # Redis trouble must not break permits.
            log.exception("Failed to broadcast permit %s", permit.pk)

    transaction.on_commit(send)
