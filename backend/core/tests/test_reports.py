import io
from datetime import timedelta
from unittest import mock

from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APITestCase

from core import models as m
from core import reports, visits

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit, make_user, set_plan


@mock.patch("core.visits.broadcast")
class ReportTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.other = make_condo("beta")
        self.other_unit = make_unit(self.other, floor="09", number="01")
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main gate")
        self.guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        self.client.force_authenticate(self.guard)

    def visit(self, condo=None, unit=None, **kw):
        kw.setdefault("purpose", "guest")
        kw.setdefault("name", "Tan Ah Kow")
        return visits.create((condo or self.condo).pk, unit=unit or self.unit, source="staff", **kw)

    def get(self, key, **params):
        params.setdefault("condominium", self.condo.pk)
        return self.client.get(f"/v1/reports/{key}/", params)

    def test_parse_search(self, _):
        self.assertEqual(reports.parse_search('unit:05-12 "Ace Aircon" grab name:"Tan Ah"'),
                         ([("unit", "05-12"), ("name", "Tan Ah")], ["Ace Aircon", "grab"]))

    def test_catalog_lists_reports_and_own_sites(self, _):
        data = self.client.get("/v1/reports/").data
        self.assertEqual([r["key"] for r in data["reports"]], ["summary", "visits", "access", "vehicles", "intercom", "invitations"])
        self.assertEqual([s["name"] for s in data["sites"]], [self.condo.name])
        self.assertFalse(data["can_combine"])
        self.client.force_authenticate(make_user("nobody"))
        self.assertEqual(self.client.get("/v1/reports/").status_code, 403)

    def test_visits_summary_rows_and_smart_search(self, _):
        a = self.visit(company="Ace Aircon", purpose="contractor", vehicle_plate="SGX1234A")
        self.visit(name="Siti")
        visits.check_out(a)
        self.visit(condo=self.other, unit=self.other_unit, name="Elsewhere")

        data = self.get("visits").data
        self.assertEqual(data["count"], 2)
        kpis = {k["key"]: k["value"] for k in data["summary"]["kpis"]}
        self.assertEqual((kpis["total"], kpis["checked_out"], kpis["on_site"]), (2, 1, 1))
        self.assertEqual(len(data["summary"]["trend"]["points"]), 7)
        self.assertNotIn("site", [c["key"] for c in data["columns"]])  # One site: no site column.

        # Insights: arrivals by weekday and hour, stay and daily visits per purpose group.
        m.Visit.objects.filter(pk=a.pk).update(created_at=a.checked_out_at - timedelta(minutes=30))
        insights = self.get("visits").data["summary"]["insights"]
        self.assertEqual((len(insights["heatmap"]), sum(map(sum, insights["heatmap"]))), (7, 2))
        self.assertEqual([(r["key"], r["minutes"], r["visits"]) for r in insights["stay_by_purpose"]], [("contractors", 30, 1)])
        trend = insights["purpose_trend"]
        # Insights are part of Advanced reports.
        set_plan(self.condo, "basic")
        summary = self.get("visits").data["summary"]
        self.assertNotIn("insights", summary)
        self.assertTrue(summary["insights_locked"])
        set_plan(self.condo, "full")
        self.assertEqual([x["key"] for x in trend["series"]], ["guests", "deliveries", "contractors"])
        self.assertEqual(sum(p["guests"] + p["contractors"] for p in trend["points"]), 2)

        self.assertEqual(self.get("visits", q="unit:05-12 plate:sgx1234").data["count"], 1)
        self.assertEqual(self.get("visits", q='"Ace Air"').data["rows"][0]["visitor"], "Tan Ah Kow")
        self.assertEqual(self.get("visits", q="category:contr").data["count"], 1)
        self.assertEqual(self.get("visits", state="on_site").data["rows"][0]["visitor"], "Siti")
        self.assertEqual(self.get("visits", q="nobody-like-this").data["count"], 0)

    def test_period(self, _):
        old = self.visit()
        m.Visit.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
        self.visit()
        self.assertEqual(self.get("visits").data["count"], 1)
        start = (timezone.localdate() - timedelta(days=40)).isoformat()
        self.assertEqual(self.get("visits", date_from=start).data["count"], 2)
        self.assertEqual(self.get("visits", date_from="2026-02-01", date_to="2026-01-01").status_code, 400)
        self.assertEqual(self.get("visits", date_from="2020-01-01", date_to="2026-01-01").status_code, 400)

    def test_officers_only_see_their_site(self, _):
        self.assertEqual(self.get("visits", condominium=self.other.pk).status_code, 403)
        self.assertEqual(self.get("visits", condominium=f"{self.condo.pk},{self.other.pk}").status_code, 403)
        self.assertEqual(self.get("visits", condominium="all").status_code, 400)
        self.client.force_authenticate(make_resident("res", self.unit))
        self.assertEqual(self.get("visits").status_code, 403)

    def test_superuser_combines_sites(self, _):
        self.visit()
        self.visit(condo=self.other, unit=self.other_unit)
        self.client.force_authenticate(make_user("root", is_superuser=True, is_staff=True))
        data = self.get("visits", condominium="all").data
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["columns"][0]["key"], "site")
        summary = self.get("summary", condominium=f"{self.condo.pk},{self.other.pk}").data
        self.assertEqual(summary["count"], 2)  # One row per site and day.
        self.assertEqual({r["site"] for r in summary["rows"]}, {self.condo.name, "Beta"})
        self.assertIn("sites", [b["key"] for b in summary["summary"]["breakdowns"]])

    def test_every_report_runs(self, _):
        host = make_resident("alice", self.unit)
        make_invitation(self.unit, host, vehicle_plate="SGX1234A")
        m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, method="lpr", result="denied",
                                   plate_number="SKA9999Z", reason="Unknown plate")
        m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, method="manual", result="granted", actor=self.guard)
        m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, room_name="r", status="missed", visitor_name="Bob")
        self.visit()
        for key in reports.REPORTS:
            response = self.get(key)
            self.assertEqual(response.status_code, 200, (key, response.data))
            self.assertGreater(response.data["count"], 0, key)
        self.assertEqual(self.get("access", q="status:denied plate:ska").data["count"], 1)
        vehicles = self.get("vehicles").data
        self.assertEqual(vehicles["rows"][0]["kind"], "Unknown")
        self.assertEqual(self.get("access", q="by:guard").data["count"], 1)
        self.assertEqual(self.get("nope").status_code, 404)

    def test_exports(self, _):
        self.visit(company="Ace Aircon")
        csv = self.get("visits", export="csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("attachment;", csv["Content-Disposition"])
        text = csv.content.decode("utf-8-sig")
        self.assertTrue(text.startswith("Pass,Visitor,"))
        self.assertIn("Ace Aircon", text)

        xlsx = self.get("visits", export="xlsx")
        self.assertEqual(xlsx.status_code, 200)
        book = load_workbook(io.BytesIO(xlsx.content))
        self.assertEqual(book.sheetnames, ["Summary", "Details"])
        self.assertEqual(book["Summary"]["A1"].value, "Visitor report")
        self.assertEqual(book["Details"]["B2"].value, "Tan Ah Kow")
        for key in reports.REPORTS:
            self.assertEqual(self.get(key, export="xlsx").status_code, 200, key)

    def test_exports_never_contain_formulas(self, _):
        self.visit(name='=HYPERLINK("http://evil.example","Click")', company="@SUM(1+1)")
        text = self.get("visits", export="csv").content.decode("utf-8-sig")
        self.assertIn("\"'=HYPERLINK(", text)
        self.assertIn("'@SUM(1+1)", text)
        cell = load_workbook(io.BytesIO(self.get("visits", export="xlsx", q="HYPERLINK").content))["Details"]["B2"]
        self.assertEqual((cell.data_type, cell.value), ("s", '=HYPERLINK("http://evil.example","Click")'))

    def test_print_returns_every_row_up_to_the_limit(self, _):
        for i in range(3):
            self.visit(name=f"V{i}")
        data = self.get("visits", page_size="print").data
        self.assertEqual((len(data["rows"]), data["truncated"]), (3, False))
        self.assertEqual(len(self.get("visits", page_size=2).data["rows"]), 2)
