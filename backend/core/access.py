"""Access decisions: every gate opening goes through ``grant`` so it is logged and queued the same way."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import AccessLog, Direction, Invitation, Vehicle

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
    recent = timezone.now() - timedelta(seconds=settings.LPR_DEBOUNCE_SECONDS)
    if AccessLog.objects.filter(camera=camera, plate_number=plate, occurred_at__gte=recent).exists():
        return None

    if not gate.is_active:
        return deny(gate, reason="Gate is disabled", **fields)

    vehicle = (Vehicle.objects.select_related("unit")
               .filter(condominium_id=gate.condominium_id, plate_number=plate, is_active=True, unit__is_active=True)
               .first())
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
        return deny(gate, reason="Unregistered plate", **fields)

    fields.update(invitation=invitation, unit=invitation.unit, visitor=invitation.visitor)
    if invitation.require_face:
        return deny(gate, reason="Invitation requires face verification at the kiosk", **fields)
    if not gate.lpr_auto_open_invited:
        return deny(gate, reason="Auto-open for invited vehicles is off at this gate", **fields)
    if camera.direction != Direction.EXIT:
        invitation.record_entry()
    return grant(gate, **fields)
