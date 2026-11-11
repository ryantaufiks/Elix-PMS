from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.utils import timezone
from rest_framework.test import APITestCase

from core import intercom, usage
from core import models as m
from core.scoping import ADMIN

from .factories import make_condo, make_staff, make_unit, make_user, set_plan


@mock.patch("core.tasks.end_call_room.delay")
@mock.patch("core.tasks.send_email.delay")
class UsageTests(APITestCase):
    def setUp(self):
        self.condo = make_condo("alpha", plan="standard")
        plan = m.Plan.objects.get(code="standard")
        plan.limits = {"intercom_minutes": 10, "ai_conversations": 2}
        plan.overage_rates = {"intercom_minutes": 0.05, "ai_conversations": 0.5}
        plan.save()
        self.condo.refresh_from_db()
        self.unit = make_unit(self.condo)
        self.admin = make_staff("admin", self.condo, ADMIN)
        self.admin.email = "admin@alpha.example"
        self.admin.save()
        self.root = make_user("root", is_superuser=True, is_staff=True)

    def call(self, seconds, answered=True):
        now = timezone.now()
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, room_name=f"room-{m.IntercomCall.objects.count()}",
                                             answered_at=now - timedelta(seconds=seconds) if answered else None,
                                             status=m.IntercomCall.Status.ANSWERED if answered else m.IntercomCall.Status.RINGING)
        with self.captureOnCommitCallbacks(execute=True):
            intercom.hang_up(call, m.IntercomCall.Status.MISSED)

    def subjects(self):
        return list(m.EmailLog.objects.order_by("pk").values_list("subject", flat=True))

    def test_answered_time_is_counted_in_minutes(self, *mocks):
        self.call(125)
        self.call(30, answered=False)
        self.assertEqual(usage.counters(self.condo, usage.month_of())[usage.INTERCOM_SECONDS], 125)
        self.assertEqual(usage.this_month(self.condo)["intercom_minutes"], 3)

    def test_warnings_at_80_and_100_percent_once(self, *mocks):
        self.call(8 * 60)
        self.assertEqual(self.subjects(), ["Alpha: 80% of this month's video intercom allowance used"])
        self.call(30)
        self.assertEqual(len(self.subjects()), 1)  # Not again.
        self.call(2 * 60)
        self.assertEqual(self.subjects()[-1], "Alpha: 100% of this month's video intercom allowance used")
        self.assertIn("keeps working", m.EmailLog.objects.last().body_text)

    def test_conversations_and_tokens(self, *mocks):
        usage.conversation_started(self.condo, own_key=False)
        usage.conversation_started(self.condo, own_key=True)
        usage.tokens(self.condo, {"usage": {"prompt_tokens": 1200, "completion_tokens": 80}})
        usage.tokens(self.condo, {"usage": {"input_tokens": 50, "output_tokens": 10}})
        usage.tokens(self.condo, {})
        raw = usage.counters(self.condo, usage.month_of())
        self.assertEqual((raw[usage.AI_CONVERSATIONS], raw[usage.AI_OWN_KEY_CONVERSATIONS]), (1, 1))
        self.assertEqual((raw[usage.AI_TOKENS_IN], raw[usage.AI_TOKENS_OUT]), (1250, 90))

    def test_monthly_report_with_overage_and_cost(self, *mocks):
        m.SystemSettings.objects.update_or_create(pk=1, defaults={"ai_usd_per_million_input": Decimal("0.4"),
                                                                 "ai_usd_per_million_output": Decimal("1.6")})
        self.call(12 * 60)
        for _ in range(3):
            usage.conversation_started(self.condo, own_key=False)
        usage.tokens(self.condo, {"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}})
        self.client.force_authenticate(self.root)
        row = self.client.get("/v1/usage/").data["rows"][0]
        self.assertEqual((row["intercom_minutes"], row["intercom_minutes_overage"], row["intercom_minutes_amount"]), (12, 2, 0.1))
        self.assertEqual((row["ai_conversations"], row["ai_conversations_overage"], row["ai_conversations_amount"]), (3, 1, 0.5))
        self.assertEqual(row["overage_amount"], 0.6)
        self.assertEqual(row["ai_cost_usd"], 1.2)
        self.assertEqual(row["currency"], "SGD")
        csv = self.client.get("/v1/usage/?export=csv")
        self.assertIn("elix-usage-", csv["Content-Disposition"])
        self.assertIn("Alpha,alpha,Standard", csv.content.decode())
        # Another month is empty; a bad month is refused; site admins cannot see the report.
        last_year = (timezone.localdate() - timedelta(days=400)).strftime("%Y-%m")
        self.assertEqual(self.client.get(f"/v1/usage/?month={last_year}").data["rows"][0]["intercom_minutes"], 0)
        self.assertEqual(self.client.get("/v1/usage/?month=2026-13").status_code, 400)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/v1/usage/").status_code, 403)
        # ...but they see this month's use against their allowance.
        sub = self.client.get(f"/v1/subscriptions/{self.condo.pk}/").data
        self.assertEqual((sub["usage"]["intercom_minutes"], sub["limits"]["intercom_minutes"]), (12, 10))

    def test_rates_only_for_metered_limits(self, *mocks):
        self.client.force_authenticate(self.root)
        response = self.client.post("/v1/plans/", {"code": "x", "name": "X", "overage_rates": {"kiosks": 5}}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/v1/plans/", {"code": "x", "name": "X", "overage_rates": {"ai_conversations": 0.3}}, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_no_allowance_no_warning(self, *mocks):
        set_plan(self.condo, "full")
        self.call(60 * 60)
        self.assertEqual(self.subjects(), [])
