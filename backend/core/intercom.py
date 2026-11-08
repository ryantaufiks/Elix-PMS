"""Intercom call lifecycle: kiosk rings a unit, a resident answers and swipes to unlock.

    ringing --answer--> answered --unlock--> approved
       |                   |
       +--unlock-----------+--> approved   (residents may unlock from the preview)
       +--reject / cancel / timeout--> rejected / cancelled / missed
"""
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import access, config, visits
from .models import AccessLog, IntercomCall, Residency, StaffAssignment
from .realtime import broadcast_call


class CallError(Exception):
    """The requested transition is not allowed in the call's current state."""


def recipients(unit):
    """Active residents of the unit who take intercom calls."""
    return Residency.objects.filter(unit=unit, is_active=True, receives_intercom_calls=True).select_related("user")


def can_handle(user, call):
    """Residents of the called unit, and staff of the condominium, may answer or decide."""
    if user.is_superuser:
        return True
    if recipients(call.unit).filter(user=user).exists():
        return True
    return StaffAssignment.objects.filter(user=user, condominium_id=call.condominium_id).exists()


def _locked(call):
    return IntercomCall.objects.select_for_update(of=("self",)).select_related("gate", "unit", "kiosk").get(pk=call.pk)


def _notify(call):
    """Tell sockets about the new state; once a call stops ringing, also stop other phones ringing."""
    from .tasks import push_call_ended

    transaction.on_commit(lambda: broadcast_call(call))
    if call.status != IntercomCall.Status.RINGING:
        transaction.on_commit(lambda: push_call_ended.delay(call.pk))


@transaction.atomic
def start(kiosk, unit, visitor_name="", snapshot=None, visitor=None, purpose="", company=""):
    from .tasks import end_call_room, expire_call, finish_call, push_incoming_call

    if not recipients(unit).exists():
        raise CallError("Nobody at this unit accepts intercom calls.")
    # A kiosk handles one visitor at a time: starting a new call cancels any still open.
    open_calls = IntercomCall.objects.select_for_update().filter(
        kiosk=kiosk, status__in=IntercomCall.OPEN_STATUSES, ended_at__isnull=True)
    for stale in open_calls:
        stale.status, stale.ended_at = IntercomCall.Status.CANCELLED, timezone.now()
        stale.save(update_fields=["status", "ended_at", "updated_at"])
        _notify(stale)
        transaction.on_commit(lambda room=stale.room_name: end_call_room.delay(room))

    call = IntercomCall(condominium_id=kiosk.condominium_id, unit=unit, kiosk=kiosk, gate=kiosk.gate,
                        visitor=visitor, visitor_name=visitor_name, visitor_purpose=purpose, visitor_company=company,
                        room_name=f"call-{kiosk.condominium_id}-{secrets.token_hex(8)}")
    if snapshot:
        call.visitor_snapshot = snapshot
    call.save()
    timeout = kiosk.condominium.intercom_ring_timeout_seconds
    _notify(call)
    transaction.on_commit(lambda: push_incoming_call.delay(call.pk))
    transaction.on_commit(lambda: expire_call.apply_async((call.pk,), countdown=timeout))
    # Safety net: close the room even if neither side hangs up.
    transaction.on_commit(lambda: finish_call.apply_async((call.pk,), countdown=config.get("INTERCOM_UNLOCK_WINDOW_SECONDS")))
    return call


@transaction.atomic
def answer(call, user):
    call = _locked(call)
    if call.status == IntercomCall.Status.ANSWERED and call.answered_by_id == user.pk:
        return call  # The same phone retrying.
    if call.status != IntercomCall.Status.RINGING or call.ended_at:
        raise CallError("This call has already been answered or has ended.")
    call.status, call.answered_by, call.answered_at = IntercomCall.Status.ANSWERED, user, timezone.now()
    call.save(update_fields=["status", "answered_by", "answered_at", "updated_at"])
    _notify(call)
    return call


@transaction.atomic
def unlock(call, user):
    """Swipe to unlock: approve the visitor and open the kiosk's gate."""
    call = _locked(call)
    if not call.is_open:
        raise CallError("This call has ended.")
    if timezone.now() - call.created_at > timedelta(seconds=config.get("INTERCOM_UNLOCK_WINDOW_SECONDS")):
        raise CallError("This call is too old to unlock the gate.")
    if call.gate is None or not call.gate.is_active:
        raise CallError("The kiosk is not linked to an active gate.")
    now = timezone.now()
    call.status, call.decided_by, call.decided_at = IntercomCall.Status.APPROVED, user, now
    if call.answered_by_id is None:
        call.answered_by, call.answered_at = user, now
    call.save(update_fields=["status", "decided_by", "decided_at", "answered_by", "answered_at", "updated_at"])
    log = access.grant(call.gate, AccessLog.Method.INTERCOM, actor=user, unit=call.unit, intercom_call=call,
                       visitor=call.visitor,
                       reason=f"Approved by {user.get_full_name() or user.get_username()}")
    visits.call_entry(call, log)
    _notify(call)
    return call, log


@transaction.atomic
def reject(call, user):
    from .tasks import end_call_room

    call = _locked(call)
    if not call.is_open:
        raise CallError("This call has ended.")
    now = timezone.now()
    call.status, call.decided_by, call.decided_at, call.ended_at = IntercomCall.Status.REJECTED, user, now, now
    call.save(update_fields=["status", "decided_by", "decided_at", "ended_at", "updated_at"])
    AccessLog.objects.create(condominium_id=call.condominium_id, gate=call.gate, method=AccessLog.Method.INTERCOM,
                             result=AccessLog.Result.DENIED, actor=user, unit=call.unit, intercom_call=call,
                             visitor=call.visitor, reason="Rejected by resident")
    _notify(call)
    transaction.on_commit(lambda: end_call_room.delay(call.room_name))
    return call


@transaction.atomic
def hang_up(call, status=None):
    """End the media session. Open calls get ``status`` (cancelled/missed); decided calls keep theirs."""
    from .tasks import end_call_room

    call = _locked(call)
    if call.ended_at:
        return call
    fields = ["ended_at", "updated_at"]
    was_open = call.is_open
    call.ended_at = timezone.now()
    if was_open and status:
        call.status = status
        fields.append("status")
    call.save(update_fields=fields)
    _notify(call)
    transaction.on_commit(lambda: end_call_room.delay(call.room_name))
    return call


def mark_missed(call_id):
    call = IntercomCall.objects.filter(pk=call_id, status=IntercomCall.Status.RINGING, ended_at__isnull=True).first()
    if call:
        hang_up(call, IntercomCall.Status.MISSED)


def finish(call_id):
    call = IntercomCall.objects.filter(pk=call_id, ended_at__isnull=True).first()
    if call:
        hang_up(call, IntercomCall.Status.MISSED)
