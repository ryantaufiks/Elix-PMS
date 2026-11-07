import logging

from celery import shared_task
from django.utils import timezone

from . import relays
from .models import AccessLog, Invitation

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
