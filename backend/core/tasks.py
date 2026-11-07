import logging

from celery import shared_task
from django.utils import timezone

from . import intercom, livekit, push, relays
from .models import AccessLog, IntercomCall, Invitation

logger = logging.getLogger(__name__)


@shared_task
def expire_invitations() -> int:
    """Mark active invitations whose validity window has passed as expired."""
    return Invitation.objects.filter(
        status=Invitation.Status.ACTIVE, valid_until__lt=timezone.now()
    ).update(status=Invitation.Status.EXPIRED, updated_at=timezone.now())


@shared_task
def open_gate(access_log_id: int) -> str:
    """Pulse every active relay on the log's gate; mark the log as an error if none responds.

    Not retried: a barrier that opens a minute late is worse than a guard
    seeing the failure straight away.
    """
    log = AccessLog.objects.select_related("gate").get(pk=access_log_id)
    relays_qs = log.gate.relays.filter(is_active=True).select_related("account")
    errors, opened = [], None
    for relay in relays_qs:
        try:
            result = relays.pulse(relay)
        except relays.RelayError as exc:
            errors.append(f"{relay.name}: {exc}")
            relay.last_error = str(exc)
            relay.save(update_fields=["last_error", "updated_at"])
            logger.warning("Relay %s failed: %s", relay.pk, exc)
            continue
        relay.last_triggered_at, relay.last_error = timezone.now(), ""
        relay.save(update_fields=["last_triggered_at", "last_error", "updated_at"])
        opened = opened or relay
        logger.info("Relay %s opened via %s: %s", relay.pk, result.via, result.detail)

    if opened is None:
        reason = "; ".join(errors) or "No active relay on this gate"
        AccessLog.objects.filter(pk=log.pk).update(result=AccessLog.Result.ERROR, reason=reason[:255])
        return f"error: {reason}"
    AccessLog.objects.filter(pk=log.pk).update(relay=opened, reason=("; ".join(errors))[:255])
    return f"opened via {opened.name}"


@shared_task
def expire_call(call_id: int):
    """Ring timeout: a call nobody answered becomes missed."""
    intercom.mark_missed(call_id)


@shared_task
def finish_call(call_id: int):
    """Unlock window over: close whatever is still open."""
    intercom.finish(call_id)


@shared_task(autoretry_for=(Exception,), retry_backoff=2, max_retries=3)
def end_call_room(room: str):
    try:
        livekit.delete_room(room)
    except livekit.LiveKitNotConfigured:
        pass


@shared_task
def push_incoming_call(call_id: int) -> int:
    call = IntercomCall.objects.select_related("unit__block", "kiosk", "condominium").get(pk=call_id)
    if not call.is_open:
        return 0
    from .models import PushDevice

    users = intercom.recipients(call.unit).values_list("user_id", flat=True)
    devices = PushDevice.objects.filter(user_id__in=list(users))
    where = call.kiosk.name if call.kiosk else call.condominium.name
    return push.send(
        devices,
        data={"type": "intercom_call", "call_id": call.pk, "unit": str(call.unit), "kiosk": where,
              "visitor": call.visitor_name, "timeout": call.condominium.intercom_ring_timeout_seconds},
        title=f"Visitor at {where}",
        body=call.visitor_name or "Someone is calling your unit",
        ttl_seconds=call.condominium.intercom_ring_timeout_seconds,
    )


@shared_task
def push_call_ended(call_id: int) -> int:
    """Silent push so phones still showing the incoming-call screen dismiss it."""
    call = IntercomCall.objects.select_related("unit", "condominium").get(pk=call_id)
    from .models import PushDevice

    users = intercom.recipients(call.unit).values_list("user_id", flat=True)
    devices = PushDevice.objects.filter(user_id__in=list(users))
    return push.send(devices, data={"type": "intercom_call_ended", "call_id": call.pk, "status": call.status},
                     title="", body="", ttl_seconds=60)
