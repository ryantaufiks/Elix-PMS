import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AccessLog
from .realtime import broadcast

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AccessLog)
def access_log_created(sender, instance, created, **kwargs):
    if not created:
        return

    def send():
        from .serializers import AccessLogSerializer

        try:
            broadcast(instance.condominium_id, instance.unit_id, "access_log", AccessLogSerializer(instance).data)
        except Exception:  # A Redis hiccup must never break gate access.
            logger.exception("Failed to broadcast access log %s", instance.pk)

    transaction.on_commit(send)
