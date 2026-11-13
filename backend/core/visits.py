"""Visitors on site: every way in records a Visit with a daily pass number; check-out ends it.

Walk-ins are registered at a kiosk (and get a printed slip) or by security at the guardhouse.
Invitation check-ins (QR or plate) and gates opened over the intercom record a visit too, so
security has one list of who is on site.
"""
import base64
import io
import logging
import math
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import qrcode
from django.db import transaction
from django.db.models import Count, F, Max
from django.utils import timezone

from .models import Condominium, Visit, VisitPurpose
from .realtime import broadcast

log = logging.getLogger(__name__)

FACE_SIZE = 128
# Euclidean distance between face templates (face-api.js recognition net). 0.6 is the library's usual
# cut-off; 0.45 is stricter, and the best match must also clearly beat the runner-up.
FACE_MATCH_DISTANCE = 0.45
FACE_MATCH_MARGIN = 0.06


def local_day(condo, at=None):
    """The condominium's local date at ``at``, and the moment that day ends."""
    tz = ZoneInfo(condo.timezone or "Asia/Singapore")
    day = (at or timezone.now()).astimezone(tz).date()
    return day, datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz) - timedelta(seconds=1)


DELIVERY_PURPOSES = (VisitPurpose.DELIVERY, VisitPurpose.FOOD, VisitPurpose.PICKUP)


def overstay_at(visit, condo=None):
    """When a visitor still on site starts overstaying, by the site's limit for their purpose; None when
    no limit applies. A contractor who arrives after the day's cut-off gets the guests' limit."""
    condo = condo or visit.condominium
    guest = condo.overstay_guest_minutes and visit.created_at + timedelta(minutes=condo.overstay_guest_minutes)
    if visit.purpose in DELIVERY_PURPOSES:
        return condo.overstay_delivery_minutes and visit.created_at + timedelta(minutes=condo.overstay_delivery_minutes) or None
    if visit.purpose == VisitPurpose.CONTRACTOR and condo.overstay_contractor_until:
        tz = ZoneInfo(condo.timezone or "Asia/Singapore")
        cutoff = datetime.combine(visit.created_at.astimezone(tz).date(), condo.overstay_contractor_until, tzinfo=tz)
        return cutoff if cutoff > visit.created_at else guest or None
    if visit.purpose == VisitPurpose.CONTRACTOR:
        return None
    return guest or None


def is_overstaying(visit, now=None):
    if visit.checked_out_at or visit.valid_until < (now or timezone.now()):
        return False
    at = overstay_at(visit)
    return bool(at and at <= (now or timezone.now()))


def notify_overstays():
    """Tell each site's guardhouse, once per visit, about visitors on site past their limit."""
    from .serializers import VisitSerializer

    now = timezone.now()
    told = 0
    waiting = Visit.objects.filter(checked_out_at__isnull=True, valid_until__gte=now, overstay_notified_at__isnull=True) \
        .select_related("condominium", "unit__block", "kiosk", "gate", "visitor", "created_by")
    for visit in waiting:
        if not is_overstaying(visit, now):
            continue
        visit.overstay_notified_at = now
        visit.save(update_fields=["overstay_notified_at", "updated_at"])
        try:
            broadcast(visit.condominium_id, None, "visit_overstay", VisitSerializer(visit).data)
        except Exception:  # Redis trouble: the dashboard still shows the visit as overstaying.
            log.exception("Failed to broadcast overstay of visit %s", visit.pk)
        told += 1
    return told


def notify_still_on_site():
    """Evening round: how many visitors each site still has inside, for the night shift."""
    now = timezone.now()
    rows = Visit.objects.filter(checked_out_at__isnull=True, valid_until__gte=now) \
        .values_list("condominium_id").annotate(n=Count("id"))
    for condo_id, count in rows:
        try:
            broadcast(condo_id, None, "visitors_on_site", {"condominium": condo_id, "count": count, "at": now.isoformat()})
        except Exception:
            log.exception("Failed to broadcast visitors on site for %s", condo_id)
    return len(rows)


def on_site(condominium_id):
    return Visit.objects.filter(condominium_id=condominium_id, checked_out_at__isnull=True, valid_until__gte=timezone.now())


def new_pin(condominium_id):
    """A random 4-digit PIN that no visitor on site at the condominium holds."""
    taken = set(on_site(condominium_id).values_list("pin", flat=True))
    for _ in range(50):
        pin = f"{secrets.randbelow(10_000):04d}"
        if pin not in taken:
            return pin
    free = sorted(set(f"{n:04d}" for n in range(10_000)) - taken)  # Practically never: thousands on site.
    return secrets.choice(free) if free else ""


@transaction.atomic
def create(condominium_id, *, unit, purpose, name, source, snapshot=None, **fields):
    """Record a visitor arriving, with the next pass number of the day for their purpose."""
    condo = Condominium.objects.select_for_update().get(pk=condominium_id)  # Serialises numbering.
    day, end = local_day(condo)
    purpose = purpose if purpose in Visit.PREFIXES else VisitPurpose.GUEST
    prefix = Visit.PREFIXES[purpose]
    last = (Visit.objects.filter(condominium=condo, issued_on=day, pass_number__startswith=prefix)
            .aggregate(n=Max("sequence"))["n"] or 0)
    visit = Visit(condominium=condo, unit=unit, purpose=purpose, visitor_name=name or "Visitor", source=source,
                  issued_on=day, sequence=last + 1, pass_number=f"{prefix}{last + 1:03d}", valid_until=end,
                  pin=new_pin(condo.pk), **fields)
    if snapshot is not None:
        visit.visitor_snapshot.save(f"visit-{condo.pk}.jpg", snapshot, save=False)
    visit.save()
    _notify(visit)
    return visit


def issue(kiosk, unit, purpose, name, company="", visitor=None, snapshot=None, face_descriptor=None):
    """A walk-in registered at a kiosk."""
    return create(kiosk.condominium_id, unit=unit, purpose=purpose, name=name, source=Visit.Source.KIOSK,
                  kiosk=kiosk, gate=kiosk.gate, company=company, visitor=visitor, snapshot=snapshot,
                  face_descriptor=face_descriptor)


def _open_for(invitation):
    return on_site(invitation.condominium_id).select_for_update().filter(invitation=invitation).first()


def _safely(record):
    """Recording the visit must never undo the gate opening it belongs to."""
    def wrapper(*args, **kwargs):
        try:
            with transaction.atomic():
                return record(*args, **kwargs)
        except Exception:
            log.exception("Could not record the visit (%s)", record.__name__)
            return None
    return wrapper


@_safely
def invitation_entry(invitation, entry_log, kiosk=None, face_descriptor=None):
    """An invited visitor came in (QR at a kiosk or plate). Re-entries the same day reuse the visit."""
    visit = _open_for(invitation)
    if visit is not None:
        if face_descriptor:
            visit.face_descriptor = face_descriptor
            visit.save(update_fields=["face_descriptor", "updated_at"])
        return visit
    return create(invitation.condominium_id, unit=invitation.unit, purpose=invitation.purpose,
                  name=invitation.visitor_name, source=Visit.Source.INVITATION, invitation=invitation,
                  visitor=invitation.visitor, vehicle_plate=invitation.vehicle_plate or entry_log.plate_number,
                  gate=entry_log.gate, kiosk=kiosk, entry_log=entry_log, face_descriptor=face_descriptor)


@_safely
def invitation_exit(invitation):
    """An invited vehicle drove out past an exit camera."""
    visit = _open_for(invitation)
    if visit is not None:
        check_out(visit)
    return visit


@_safely
def call_entry(call, entry_log):
    """A resident or guard opened the gate for a visitor over the intercom."""
    return create(call.condominium_id, unit=call.unit, purpose=call.visitor_purpose, name=call.visitor_name,
                  source=Visit.Source.INTERCOM, intercom_call=call, visitor=call.visitor,
                  company=call.visitor_company, gate=call.gate, kiosk=call.kiosk, entry_log=entry_log,
                  face_descriptor=call.face_descriptor)


def find(condominium_id, code, lock=False):
    """The visit for what was scanned: the pass QR, or an invitation QR (that visitor's visit on site)."""
    from .access import invitation_token

    code = (code or "").strip()
    qs = Visit.objects.select_related("unit__block")
    if lock:
        qs = qs.select_for_update(of=("self",))
    if code.startswith(Visit.QR_PREFIX):
        return qs.filter(condominium_id=condominium_id, token=code[len(Visit.QR_PREFIX):]).first()
    token = invitation_token(code)
    if not token:
        return None
    return (qs.filter(condominium_id=condominium_id, invitation__token=token)
            .order_by(F("checked_out_at").asc(nulls_first=True), "-created_at").first())  # Still on site first.


def find_by_pin(condominium_id, pin, lock=False):
    """The visitor on site holding ``pin``, or None."""
    pin = (pin or "").strip()
    if len(pin) != 4 or not pin.isdigit():
        return None
    qs = on_site(condominium_id).select_related("unit__block")
    if lock:
        qs = qs.select_for_update(of=("self",))
    return qs.filter(pin=pin).first()


def valid_face(value):
    """``value`` as a face template (list of 128 finite numbers), or None."""
    if not isinstance(value, (list, tuple)) or len(value) != FACE_SIZE:
        return None
    try:
        out = [float(x) for x in value]
    except (TypeError, ValueError):
        return None
    return out if all(math.isfinite(x) for x in out) else None


def match_face(condominium_id, descriptor, lock=False):
    """(visit, "") for the visitor on site whose face matches, else (None, "no_match" | "ambiguous" | "none_enrolled")."""
    scored = []
    for visit_id, template in on_site(condominium_id).exclude(face_descriptor=None).values_list("pk", "face_descriptor"):
        template = valid_face(template)
        if template is not None:
            scored.append((math.dist(descriptor, template), visit_id))
    if not scored:
        return None, "none_enrolled"
    scored.sort()
    best, visit_id = scored[0]
    # Distances only (no personal data), to tune the thresholds against real kiosk cameras.
    log.info("Face check-out at condo %s: best %.3f, runner-up %s, %d on site",
             condominium_id, best, f"{scored[1][0]:.3f}" if len(scored) > 1 else "-", len(scored))
    if best > FACE_MATCH_DISTANCE:
        return None, "no_match"
    if len(scored) > 1 and scored[1][0] - best < FACE_MATCH_MARGIN:
        return None, "ambiguous"
    qs = Visit.objects.select_related("unit__block")
    if lock:
        qs = qs.select_for_update(of=("self",))
    return qs.get(pk=visit_id), ""


def check_out(visit, user=None):
    """Record the visitor leaving (and forget their face template). Returns False if they had already left."""
    if visit.checked_out_at:
        return False
    visit.checked_out_at = timezone.now()
    visit.checked_out_by = user
    visit.face_descriptor = None
    visit.save(update_fields=["checked_out_at", "checked_out_by", "face_descriptor", "updated_at"])
    _notify(visit)
    return True


@transaction.atomic
def check_out_many(queryset, user):
    """Check out every visit in ``queryset`` still on site. Returns how many were checked out."""
    ids = list(queryset.filter(checked_out_at__isnull=True).values_list("pk", flat=True))  # May be DISTINCT.
    return sum(check_out(visit, user) for visit in Visit.objects.select_for_update().filter(pk__in=ids))


def qr_data_uri(visit):
    buffer = io.BytesIO()
    qrcode.make(visit.qr_payload, box_size=8, border=2).save(buffer)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _notify(visit):
    def send():
        from .serializers import VisitSerializer

        try:
            broadcast(visit.condominium_id, None, "visit", VisitSerializer(visit).data)
        except Exception:  # Redis trouble must not break registration.
            log.exception("Failed to broadcast visit %s", visit.pk)

    transaction.on_commit(send)
