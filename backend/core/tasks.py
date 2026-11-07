from celery import shared_task
from django.utils import timezone

from .models import Invitation


@shared_task
def expire_invitations() -> int:
    """Mark active invitations whose validity window has passed as expired."""
    return Invitation.objects.filter(
        status=Invitation.Status.ACTIVE, valid_until__lt=timezone.now()
    ).update(status=Invitation.Status.EXPIRED, updated_at=timezone.now())
