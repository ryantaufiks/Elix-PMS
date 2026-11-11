import smtplib
from datetime import timedelta
from unittest import mock

from celery.exceptions import Retry
from django.core import mail as outbox
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core import mail
from core import models as m
from core.tasks import prune_email_log, send_email

from core.scoping import ADMIN

from .factories import make_condo, make_staff, make_user

SMTP = {"smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_username": "elix", "smtp_password": "pw",
        "email_from_address": "no-reply@example.com", "email_from_name": "Elix Test", "email_reply_to": "help@example.com"}


class EmailTests(APITestCase):
    def setUp(self):
        self.root = make_user("root", is_superuser=True, is_staff=True, email="root@example.com")
        self.client.force_authenticate(self.root)

    def configure(self, **extra):
        m.SystemSettings.objects.update_or_create(pk=1, defaults={**SMTP, **extra})

    def test_settings_keep_the_password_secret(self):
        response = self.client.patch("/v1/system-settings/", SMTP, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("smtp_password", response.data)
        self.assertTrue(response.data["has_smtp_password"])
        self.assertTrue(response.data["email_configured"])
        self.assertEqual(response.data["sources"]["smtp_host"], "admin")
        # Blank keeps the saved password, null removes it.
        self.client.patch("/v1/system-settings/", {"smtp_password": ""}, format="json")
        self.assertEqual(m.SystemSettings.load().smtp_password, "pw")
        self.client.patch("/v1/system-settings/", {"smtp_password": None}, format="json")
        self.assertEqual(m.SystemSettings.load().smtp_password, "")

    def test_test_email_needs_settings(self):
        response = self.client.post("/v1/system-settings/test-email/", {}, format="json")
        self.assertFalse(response.data["ok"])
        self.assertIn("SMTP host", response.data["detail"])
        self.assertEqual(len(outbox.outbox), 0)

    def test_test_email_goes_to_the_admin_by_default(self):
        self.configure()
        response = self.client.post("/v1/system-settings/test-email/", {}, format="json")
        self.assertTrue(response.data["ok"], response.data)
        sent = outbox.outbox[0]
        self.assertEqual(sent.to, ["root@example.com"])
        self.assertEqual(sent.from_email, "Elix Test <no-reply@example.com>")
        self.assertEqual(sent.reply_to, ["help@example.com"])
        self.assertEqual(sent.subject, "Elix Test test email")
        self.assertIn("Email is working", sent.alternatives[0][0])
        log = m.EmailLog.objects.get()
        self.assertEqual((log.status, log.attempts), (m.EmailLog.Status.SENT, 1))
        # Another address can be given.
        self.client.post("/v1/system-settings/test-email/", {"to": "ops@example.com"}, format="json")
        self.assertEqual(outbox.outbox[1].to, ["ops@example.com"])

    @override_settings(EMAIL_HOST="smtp.env.example", EMAIL_FROM_ADDRESS="env@example.com")
    def test_env_is_the_fallback(self):
        self.assertTrue(mail.is_configured())
        self.assertTrue(mail.send_test("a@example.com")[0])
        self.assertEqual(outbox.outbox[0].from_email, "Elix <env@example.com>")

    def test_queued_email_is_sent_by_the_worker(self):
        self.configure()
        condo = make_condo("alpha")
        with mock.patch("core.tasks.send_email.delay") as delay, self.captureOnCommitCallbacks(execute=True):
            logs = mail.queue(["a@example.com", "a@example.com", " ", "b@example.com"], "test",
                              {"sent_at": timezone.now()}, condominium=condo)
        self.assertEqual([log.to for log in logs], ["a@example.com", "b@example.com"])
        self.assertEqual(delay.call_count, 2)
        send_email(logs[0].pk)
        self.assertEqual(outbox.outbox[0].to, ["a@example.com"])
        self.assertEqual(m.EmailLog.objects.get(pk=logs[0].pk).status, m.EmailLog.Status.SENT)
        # Sending again does nothing: it already went out.
        send_email(logs[0].pk)
        self.assertEqual(len(outbox.outbox), 1)

    def test_failures_are_recorded_and_network_errors_retried(self):
        self.configure()
        with self.captureOnCommitCallbacks(execute=False):
            log = mail.queue(["a@example.com"], "test", {"sent_at": timezone.now()})[0]
        with mock.patch("django.core.mail.EmailMultiAlternatives.send",
                        side_effect=smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")})):
            send_email(log.pk)
        log.refresh_from_db()
        self.assertEqual(log.status, m.EmailLog.Status.FAILED)
        self.assertIn("SMTPRecipientsRefused", log.error)
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=smtplib.SMTPServerDisconnected("gone")), \
                self.assertRaises(Retry):
            send_email.apply(args=[log.pk], throw=True)

    def test_which_errors_are_retried(self):
        self.assertTrue(mail.is_transient(smtplib.SMTPServerDisconnected("gone")))
        self.assertTrue(mail.is_transient(TimeoutError("timed out")))
        self.assertTrue(mail.is_transient(smtplib.SMTPDataError(451, b"try later")))
        self.assertFalse(mail.is_transient(smtplib.SMTPDataError(554, b"rejected")))
        self.assertFalse(mail.is_transient(smtplib.SMTPAuthenticationError(535, b"bad login")))
        self.assertFalse(mail.is_transient(smtplib.SMTPRecipientsRefused({"a@x.com": (550, b"no")})))
        self.assertFalse(mail.is_transient(mail.EmailNotConfigured("no host")))

    def test_log_is_for_the_platform_admin_and_pruned(self):
        old = m.EmailLog.objects.create(to="a@example.com", subject="Old", template="test", body_text="x")
        m.EmailLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
        m.EmailLog.objects.create(to="b@example.com", subject="New", template="test", body_text="x")
        self.assertEqual(self.client.get("/v1/email-logs/").data["count"], 2)
        self.client.force_authenticate(make_staff("admin", make_condo("alpha"), ADMIN))
        self.assertEqual(self.client.get("/v1/email-logs/").status_code, 403)
        self.assertEqual(self.client.post("/v1/system-settings/test-email/", {}).status_code, 403)
        self.assertEqual(prune_email_log(), 1)
        self.assertEqual(list(m.EmailLog.objects.values_list("subject", flat=True)), ["New"])
