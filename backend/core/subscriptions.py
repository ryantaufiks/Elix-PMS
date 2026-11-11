"""Subscription lifecycle: trial -> (paid) active -> grace -> suspended, and the reminder emails.

A daily job moves sites along when their dates pass; the platform admin can change a status at any time,
which sends the same emails. Physical access never stops (see ``core.entitlements``).
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import config, mail
from .models import StaffAssignment, Subscription, SubscriptionEvent, User
from .scoping import ADMIN

logger = logging.getLogger(__name__)

GRACE_DAYS = 14
TRIAL_REMINDER_DAYS = (7, 1)
Status = Subscription.Status


def recipients(sub) -> list[str]:
    """The site's admins, its billing contact and the platform admins."""
    admins = StaffAssignment.objects.filter(condominium=sub.condominium_id, role=ADMIN, user__is_active=True) \
        .exclude(user__email="").values_list("user__email", flat=True)
    platform = User.objects.filter(is_superuser=True, is_active=True).exclude(email="").values_list("email", flat=True)
    return list(dict.fromkeys([*admins, *([sub.billing_email] if sub.billing_email else []), *platform]))


def notify(sub, kind, date, template=None, **context) -> bool:
    """Queue the ``subscription_<template or kind>`` email once per ``kind`` and date. False if already sent."""
    key = f"{kind}:{date.isoformat() if date else ''}"
    if key in sub.notices_sent:
        return False
    to = recipients(sub)
    if to:
        contact = config.get("EMAIL_REPLY_TO") or config.get("EMAIL_FROM_ADDRESS")
        mail.queue(to, f"subscription_{template or kind}", {"site": sub.condominium.name, "plan": sub.plan.name, "date": date,
                                                "contact": contact, **context}, condominium=sub.condominium)
    sub.notices_sent = [*sub.notices_sent[-49:], key]
    Subscription.objects.filter(pk=sub.pk).update(notices_sent=sub.notices_sent)
    return True


def on_status_change(sub, old_status, actor=None):
    """Emails for a status change, whoever made it."""
    if sub.status == old_status:
        return
    if sub.status == Status.GRACE:
        notify(sub, "grace", sub.grace_ends_on)
    elif sub.status == Status.SUSPENDED:
        notify(sub, "suspended", timezone.localdate())
    elif sub.status == Status.ACTIVE and old_status in (Status.GRACE, Status.SUSPENDED):
        notify(sub, "reactivated", sub.period_ends_on or timezone.localdate())


def move(sub, status, summary, **fields):
    """Change a subscription's status on schedule (no actor), record why, and send the emails."""
    old = sub.status
    sub.status = status
    for name, value in fields.items():
        setattr(sub, name, value)
    with transaction.atomic():
        sub.save(update_fields=["status", "updated_at", *fields])  # The signal refreshes the site's modules.
        SubscriptionEvent.objects.create(subscription=sub, summary=summary)
    on_status_change(sub, old)


def run_daily(today=None) -> dict:
    """Reminders and status changes due today. Safe to run more than once a day."""
    today = today or timezone.localdate()
    done = {"reminders": 0, "grace": 0, "active": 0, "suspended": 0}
    for sub in Subscription.objects.select_related("condominium", "plan"):
        try:
            if sub.status == Status.TRIAL and sub.trial_ends_on:
                left = (sub.trial_ends_on - today).days
                if left < 0:
                    if sub.period_ends_on and sub.period_ends_on >= today:  # Paid before the trial ended.
                        move(sub, Status.ACTIVE, f"Trial ended; paid until {sub.period_ends_on:%d %b %Y}.")
                        done["active"] += 1
                    else:
                        grace = sub.trial_ends_on + timedelta(days=GRACE_DAYS)
                        move(sub, Status.GRACE, f"Trial ended; grace period until {grace:%d %b %Y}.", grace_ends_on=grace)
                        done["grace"] += 1
                elif left in TRIAL_REMINDER_DAYS:
                    done["reminders"] += notify(sub, f"trial_ending-{left}", sub.trial_ends_on, template="trial_ending", days=left)
            elif sub.status == Status.ACTIVE and sub.period_ends_on and sub.period_ends_on < today:
                grace = sub.period_ends_on + timedelta(days=GRACE_DAYS)
                move(sub, Status.GRACE, f"Paid period ended; grace period until {grace:%d %b %Y}.", grace_ends_on=grace)
                done["grace"] += 1
            elif sub.status == Status.GRACE:
                if not sub.grace_ends_on:  # Set by hand without a date: start counting today.
                    sub.grace_ends_on = today + timedelta(days=GRACE_DAYS)
                    sub.save(update_fields=["grace_ends_on", "updated_at"])
                elif sub.grace_ends_on < today:
                    move(sub, Status.SUSPENDED, "Grace period ended without renewal; site suspended.")
                    done["suspended"] += 1
        except Exception:  # One site's problem must not stop the others.
            logger.exception("Subscription lifecycle failed for %s", sub.condominium)
    return done
