import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import AccessLog, AssistantMap, Backup, ResidentDocument, User
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


@receiver(pre_save, sender=User)
def revoke_sessions_on_password_change(sender, instance, update_fields=None, **kwargs):
    """A new password or a disabled account signs the person out of every device."""
    if not instance.pk or (update_fields is not None and not {"password", "is_active"} & set(update_fields)):
        return
    old = User.objects.filter(pk=instance.pk).values("password", "is_active").first()
    if old and (old["password"] != instance.password or (old["is_active"] and not instance.is_active)):
        from .auth_views import revoke_sessions

        revoke_sessions(instance)


@receiver(post_delete, sender=ResidentDocument)
def delete_document_file(sender, instance, **kwargs):
    """The file goes with its record, also when the resident or their residency is removed."""
    if instance.file:
        transaction.on_commit(lambda: instance.file.storage.delete(instance.file.name))


@receiver(post_delete, sender=Backup)
def delete_backup_file(sender, instance, **kwargs):
    if instance.file:
        transaction.on_commit(lambda: instance.file.storage.delete(instance.file.name))


@receiver(post_delete, sender=AssistantMap)
def delete_assistant_map_image(sender, instance, **kwargs):
    if instance.image:
        transaction.on_commit(lambda: instance.image.storage.delete(instance.image.name))
