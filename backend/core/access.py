"""Access decisions: every gate opening goes through ``grant`` so it is logged and queued the same way."""
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from . import config, visits
from .models import AccessLog, Direction, Invitation, Vehicle
from .validators import normalize_plate

Result = AccessLog.Result


def grant(gate, method, **fields):
    """Log a granted access and open the gate's relays once the transaction commits."""
    from .tasks import open_gate

    log = AccessLog.objects.create(condominium_id=gate.condominium_id, gate=gate, method=method,
                                   result=Result.GRANTED, **fields)
    transaction.on_commit(lambda: open_gate.delay(log.pk))
    return log


def deny(gate, method, reason, **fields):
    return AccessLog.objects.create(condominium_id=gate.condominium_id, gate=gate, method=method,
                                    result=Result.DENIED, reason=reason, **fields)


def _admits_gate(invitation, gate):
    gate_ids = [g.pk for g in invitation.gates.all()]
    return not gate_ids or gate.pk in gate_ids


@transaction.atomic
def handle_plate(camera, plate, payload):
    """Decide what to do with a plate read by an LPR camera. Returns the AccessLog, or None if debounced."""
    gate = camera.gate
    fields = {"method": AccessLog.Method.LPR, "plate_number": plate, "camera": camera, "raw_payload": payload}

    # Cameras report the same car several times while it waits at the barrier.
    recent = timezone.now() - timedelta(seconds=config.get("LPR_DEBOUNCE_SECONDS"))
    if AccessLog.objects.filter(camera=camera, plate_number=plate, occurred_at__gte=recent).exists():
        return None

    if not gate.is_active:
        return deny(gate, reason="Gate is disabled", **fields)

    vehicle = (Vehicle.objects.select_related("unit")
               .filter(condominium_id=gate.condominium_id, plate_number=plate, is_active=True, unit__is_active=True)
               .first())
    lapsed = None
    today = visits.local_day(gate.condominium)[0]
    if vehicle and not vehicle.valid_on(today):
        # Outside its dates: an invitation may still let it in, otherwise say why it was refused.
        lapsed = (f"Vehicle pass ended on {vehicle.valid_until:%d %b %Y}" if vehicle.valid_until and vehicle.valid_until < today
                  else f"Vehicle pass starts on {vehicle.valid_from:%d %b %Y}")
        fields.update(vehicle=vehicle, unit=vehicle.unit)
        vehicle = None
    if vehicle:
        fields.update(vehicle=vehicle, unit=vehicle.unit)
        if not gate.lpr_auto_open_residents:
            return deny(gate, reason="Auto-open for residents is off at this gate", **fields)
        return grant(gate, **fields)

    now = timezone.now()
    invitations = (Invitation.objects.select_for_update(of=("self",))
                   .select_related("unit", "visitor").prefetch_related("gates")
                   .filter(condominium_id=gate.condominium_id, vehicle_plate=plate, status=Invitation.Status.ACTIVE,
                           valid_from__lte=now, valid_until__gte=now)
                   .filter(Q(max_entries=0) | Q(entry_count__lt=F("max_entries")))
                   .order_by("valid_until"))
    invitation = next((i for i in invitations if _admits_gate(i, gate)), None)
    if invitation is None:
        return deny(gate, reason=lapsed or "Unregistered plate", **fields)
    usable, reason = invitation.check_usable()  # Days and hours of a vendor pass, contractors' working hours.
    if not usable:
        return deny(gate, reason=reason, invitation=invitation, unit=invitation.unit, **fields)

    fields.update(invitation=invitation, unit=invitation.unit, visitor=invitation.visitor)
    if invitation.needs_face:
        return deny(gate, reason="Invitation requires face verification at the kiosk", **fields)
    if not gate.lpr_auto_open_invited:
        return deny(gate, reason="Auto-open for invited vehicles is off at this gate", **fields)
    if camera.direction == Direction.EXIT:
        log = grant(gate, **fields)
        visits.invitation_exit(invitation)
        return log
    invitation.record_entry()
    log = grant(gate, **fields)
    visits.invitation_entry(invitation, log)
    return log


def invitation_token(code):
    """The invitation token from what a kiosk scanned: the share link (…/i/<token>) or the bare token."""
    code = (code or "").strip()
    if "/i/" in code:
        code = code.split("/i/", 1)[1]
    return code.split("?", 1)[0].split("#", 1)[0].strip("/")


def find_invitation(condominium_id, code, lock=False):
    token = invitation_token(code)
    if not token:
        return None
    qs = Invitation.objects.select_related("unit__block", "host", "visitor").prefetch_related("gates")
    if lock:
        qs = qs.select_for_update(of=("self",))
    return qs.filter(condominium_id=condominium_id, token=token).first()


def qr_problem(invitation, gate):
    """Why this invitation cannot open ``gate`` now, or "" when it can."""
    if invitation is None:
        return "Unknown QR code."
    ok, reason = invitation.check_usable()
    if not ok:
        return reason
    if not _admits_gate(invitation, gate):
        return "This invitation is not valid at this gate."
    return ""


class FaceRequired(Exception):
    """The invitation needs a face photo; the kiosk should capture one and try again."""


@transaction.atomic
def handle_qr(kiosk, code, plate="", face_photo=None, face_descriptor=None):
    """Check a visitor in at a kiosk with their invitation QR (plus optional plate / face photo).

    The face photo is stored with the access log for staff to review; it is not matched
    automatically at entry (``face_descriptor``, when sent, lets the visitor check out by face).
    Raises FaceRequired (nothing logged) when the invitation needs a photo.
    """
    gate = kiosk.gate
    invitation = find_invitation(kiosk.condominium_id, code, lock=True)
    plate = normalize_plate(plate)
    fields = {"method": AccessLog.Method.QR, "plate_number": plate}
    if invitation is not None:
        fields.update(invitation=invitation, unit=invitation.unit, visitor=invitation.visitor)

    if not gate.is_active:
        return deny(gate, reason="Gate is disabled", **fields)
    problem = qr_problem(invitation, gate)
    if problem:
        return deny(gate, reason=problem, **fields)
    if plate and invitation.vehicle_plate and plate != invitation.vehicle_plate:
        return deny(gate, reason=f"Vehicle {plate} does not match the invitation", **fields)
    if invitation.needs_face and face_photo is None:
        raise FaceRequired()

    invitation.record_entry()
    reason = "Face photo captured at kiosk (review in the access log)" if face_photo is not None else ""
    log = grant(gate, reason=reason, **fields)
    if face_photo is not None:
        log.snapshot.save(f"qr-{log.pk}.jpg", face_photo, save=True)
    visits.invitation_entry(invitation, log, kiosk=kiosk, face_descriptor=face_descriptor)
    return log
