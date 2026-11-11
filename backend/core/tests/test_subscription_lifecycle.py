from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework.test import APITestCase

from core import models as m
from core import subscriptions
from core.scoping import ADMIN

from .factories import make_condo, make_staff, make_user, set_plan

Status = m.Subscription.Status


@mock.patch("core.tasks.send_email.delay")
class LifecycleTests(APITestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.condo = make_condo("alpha", plan="premium")
        self.admin = make_staff("admin", self.condo, ADMIN)
        self.admin.email = "admin@alpha.example"
        self.admin.save()
        self.root = make_user("root", is_superuser=True, is_staff=True, email="root@elix.example")

    def subscription(self, **fields):
        set_plan(self.condo, "premium", billing_email="billing@alpha.example", notices_sent=[], **fields)
        return m.Subscription.objects.get(condominium=self.condo)

    def run_on(self, day):
        with self.captureOnCommitCallbacks(execute=True):
            return subscriptions.run_daily(day)

    def subjects(self):
        return list(m.EmailLog.objects.order_by("pk").values_list("to", "subject"))

    def test_trial_reminders_go_once_to_admins_billing_and_platform(self, delay):
        self.subscription(status=Status.TRIAL, trial_ends_on=self.today + timedelta(days=7))
        self.assertEqual(self.run_on(self.today)["reminders"], 1)
        self.assertEqual(self.run_on(self.today)["reminders"], 0)  # Not twice.
        self.assertEqual({to for to, _ in self.subjects()}, {"admin@alpha.example", "billing@alpha.example", "root@elix.example"})
        self.assertIn("Alpha: your Elix trial ends in 7 days", self.subjects()[0][1])
        self.assertEqual(delay.call_count, 3)
        self.run_on(self.today + timedelta(days=6))
        self.assertIn("ends tomorrow", self.subjects()[-1][1])
        self.run_on(self.today + timedelta(days=3))  # No reminder on other days.
        self.assertEqual(len(self.subjects()), 6)

    def test_trial_end_to_grace_to_suspended_and_back(self, delay):
        end = self.today - timedelta(days=1)
        sub = self.subscription(status=Status.TRIAL, trial_ends_on=end)
        self.assertEqual(self.run_on(self.today)["grace"], 1)
        sub.refresh_from_db()
        self.assertEqual((sub.status, sub.grace_ends_on), (Status.GRACE, end + timedelta(days=14)))
        self.assertIn("grace period until", self.subjects()[-1][1])
        self.condo.refresh_from_db()
        self.assertIn("intercom", self.condo.modules)  # Grace: everything still works.

        self.assertEqual(self.run_on(end + timedelta(days=15))["suspended"], 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.SUSPENDED)
        self.condo.refresh_from_db()
        self.assertEqual(self.condo.modules, ["core", "lpr", "advanced_reports"])
        self.assertIn("subscription suspended", self.subjects()[-1][1])
        self.assertIn("Grace period ended", sub.events.first().summary)

        # Setup is locked for the site admin, not the platform admin; reports still export.
        self.client.force_authenticate(self.admin)
        locked = self.client.post("/v1/gates/", {"condominium": self.condo.pk, "name": "B"})
        self.assertEqual((locked.status_code, locked.data["code"]), (403, "site_suspended"))
        self.assertEqual(self.client.get(f"/v1/reports/visits/?condominium={self.condo.pk}&export=csv").status_code, 200)
        self.client.force_authenticate(self.root)
        self.assertEqual(self.client.post("/v1/gates/", {"condominium": self.condo.pk, "name": "B"}).status_code, 201)

        # Renewed by the platform admin: everything back, with an email.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f"/v1/subscriptions/{self.condo.pk}/",
                                         {"status": "active", "period_ends_on": str(self.today + timedelta(days=365))}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["grace_ends_on"])
        self.assertIn("intercom", response.data["modules"])
        self.assertIn("active again", self.subjects()[-1][1])

    def test_paid_before_the_trial_ended(self, delay):
        self.subscription(status=Status.TRIAL, trial_ends_on=self.today - timedelta(days=1),
                          period_ends_on=self.today + timedelta(days=300))
        self.assertEqual(self.run_on(self.today)["active"], 1)
        self.assertEqual(m.Subscription.objects.get(condominium=self.condo).status, Status.ACTIVE)
        self.assertEqual(self.subjects(), [])

    def test_paid_period_ends(self, delay):
        self.subscription(status=Status.ACTIVE, period_ends_on=self.today - timedelta(days=1))
        self.run_on(self.today)
        self.assertEqual(m.Subscription.objects.get(condominium=self.condo).status, Status.GRACE)
        self.subscription(status=Status.ACTIVE, period_ends_on=self.today)  # Last paid day: nothing yet.
        self.assertEqual(self.run_on(self.today)["grace"], 0)

    def test_grace_set_by_hand_counts_from_today(self, delay):
        self.subscription(status=Status.ACTIVE)
        self.client.force_authenticate(self.root)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f"/v1/subscriptions/{self.condo.pk}/", {"status": "grace"}, format="json")
        self.assertEqual(response.data["grace_ends_on"], str(self.today + timedelta(days=14)))
        self.assertIn("grace until", response.data["events"][0]["summary"])
        self.assertIn("grace period until", self.subjects()[-1][1])

    def test_cancelled_site_is_closed_to_its_staff(self, delay):
        self.subscription(status=Status.CANCELLED)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/v1/condominiums/").data["count"], 0)
        self.assertEqual(self.client.get(f"/v1/subscriptions/{self.condo.pk}/").status_code, 403)
        self.condo.refresh_from_db()
        self.assertEqual(self.condo.modules, ["core", "lpr"])
        self.client.force_authenticate(self.root)
        self.assertEqual(self.client.get("/v1/condominiums/").data["count"], 1)

    def test_no_email_without_recipients(self, delay):
        m.User.objects.update(email="")
        self.subscription(status=Status.TRIAL, trial_ends_on=self.today + timedelta(days=1))
        m.Subscription.objects.filter(condominium=self.condo).update(billing_email="")
        self.run_on(self.today)
        self.assertEqual(self.subjects(), [])
