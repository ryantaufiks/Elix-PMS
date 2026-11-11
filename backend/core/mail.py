"""Outgoing email over the platform's SMTP server (System settings > Email, ``.env`` as fallback).

Every message is one ``EmailLog`` row per recipient, rendered when it is queued and sent by the worker,
so a retry sends the same message and the platform admin can see what went out.
"""
import logging
import smtplib
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from . import config
from .models import EmailLog

logger = logging.getLogger(__name__)

def is_transient(exc) -> bool:
    """Worth trying again: the network or a temporary (4xx) server answer, not a rejected message or login.
    (smtplib's errors are OSErrors too, so they are sorted out first.)"""
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError)):
        return True
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return all(400 <= code < 500 for code, _ in exc.recipients.values())
    return isinstance(exc, OSError) and not isinstance(exc, smtplib.SMTPException)  # timeouts, DNS, refused


class EmailNotConfigured(Exception):
    pass


def is_configured() -> bool:
    return bool(config.get("EMAIL_HOST") and config.get("EMAIL_FROM_ADDRESS"))


def connection():
    if not is_configured():
        raise EmailNotConfigured("Set the SMTP host and the from address under System settings > Email.")
    security = config.get("EMAIL_SECURITY") or "starttls"
    return get_connection(
        host=config.get("EMAIL_HOST"), port=int(config.get("EMAIL_PORT") or 587),
        username=config.get("EMAIL_HOST_USER") or None, password=config.get("EMAIL_HOST_PASSWORD") or None,
        use_tls=security == "starttls", use_ssl=security == "ssl", timeout=settings.EMAIL_TIMEOUT,
        fail_silently=False,
    )


def render(template: str, context: dict) -> tuple[str, str, str]:
    """(subject, text, html) from ``email/<template>.{subject.txt,txt,html}``."""
    context = {"brand": config.get("EMAIL_FROM_NAME") or "Elix", **context}
    subject = " ".join(render_to_string(f"email/{template}.subject.txt", context).split())
    return (subject[:200], render_to_string(f"email/{template}.txt", context).strip() + "\n",
            render_to_string(f"email/{template}.html", context))


def queue(recipients, template: str, context: dict, condominium=None) -> list[EmailLog]:
    """Render once and queue one email per recipient; the worker sends them after the transaction commits."""
    from .tasks import send_email

    subject, text, html = render(template, context)
    logs = [EmailLog.objects.create(condominium=condominium, to=to, subject=subject, template=template,
                                    body_text=text, body_html=html)
            for to in dict.fromkeys(r.strip() for r in recipients if r and r.strip())]
    for log in logs:
        transaction.on_commit(lambda pk=log.pk: send_email.delay(pk))
    return logs


def deliver(log: EmailLog, conn=None) -> None:
    """Send one logged email now. Raises on failure (after recording it on the log)."""
    log.attempts += 1
    try:
        name = config.get("EMAIL_FROM_NAME") or "Elix"
        reply_to = config.get("EMAIL_REPLY_TO")
        message = EmailMultiAlternatives(
            subject=log.subject, body=log.body_text, to=[log.to], connection=conn or connection(),
            from_email=formataddr((name, config.get("EMAIL_FROM_ADDRESS"))), reply_to=[reply_to] if reply_to else None,
        )
        if log.body_html:
            message.attach_alternative(log.body_html, "text/html")
        message.send()
    except Exception as exc:
        log.status, log.error = EmailLog.Status.FAILED, f"{exc.__class__.__name__}: {exc}"[:2000]
        log.save(update_fields=["status", "error", "attempts"])
        raise
    log.status, log.error, log.sent_at = EmailLog.Status.SENT, "", timezone.now()
    log.save(update_fields=["status", "error", "attempts", "sent_at"])


def send_test(to: str) -> tuple[bool, str]:
    """Send the test message right away, for the System settings button."""
    subject, text, html = render("test", {"sent_at": timezone.localtime()})
    log = EmailLog.objects.create(to=to, subject=subject, template="test", body_text=text, body_html=html)
    try:
        deliver(log)
    except EmailNotConfigured as exc:
        return False, str(exc)
    except Exception as exc:
        logger.warning("Test email to %s failed: %s", to, exc)
        return False, f"Could not send: {log.error}"
    return True, f"Test email sent to {to}. Check the inbox (and the spam folder)."
