import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from core import models as m
from core import privacy, walk_ins

from .factories import make_condo, make_staff, make_unit
from .test_checkin import jpeg


@mock.patch("core.walk_ins.broadcast")
class WalkInTests(APITestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.condo = make_condo()
        self.unit = make_unit(self.condo)  # Nobody lives here: walk-ins do not need a resident.
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby")
        self.kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby kiosk", gate=self.gate)
        token = self.kiosk.issue_token()
        self.kiosk.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")

    def register(self, purpose="guest", name="Tan Ah Kow", photo=True, **extra):
        data = {"unit": self.unit.pk, "visitor_name": name, "purpose": purpose, "consent": "true", **extra}
        if photo:
            data["snapshot"] = jpeg()
        return self.client.post("/v1/kiosk/walk-ins/", data, format="multipart")

    def test_daily_numbers_per_purpose(self, _):
        numbers = [self.register(p).data["pass_number"] for p in ("guest", "guest", "contractor", "food", "guest")]
        self.assertEqual(numbers, ["V001", "V002", "C001", "F001", "V003"])
        response = self.register("contractor", company="Ace Aircon")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["unit_display"], str(self.unit))
        self.assertTrue(response.data["qr"].startswith("data:image/png;base64,"))
        walk_in = m.WalkInPass.objects.get(pass_number="C002")
        self.assertEqual(walk_in.company, "Ace Aircon")
        self.assertTrue(walk_in.visitor_snapshot)
        self.assertEqual(walk_in.visitor.full_name, "Tan Ah Kow")
        self.assertFalse(m.AccessLog.objects.exists())  # The gate is not opened.

        # Next day the series restarts.
        with mock.patch("core.walk_ins.timezone.now", return_value=timezone.now() + timedelta(days=1)):
            self.assertEqual(self.register().data["pass_number"], "V001")

    def test_validation_and_site_settings(self, _):
        self.assertEqual(self.register(name="").status_code, 400)
        self.assertIn("purpose", self.register(purpose="").data)
        self.assertIn("snapshot", self.register(photo=False).data)
        self.assertIn("consent", self.register(consent="false").data)
        self.condo.kiosk_walk_in_photo = False
        self.condo.save()
        self.assertEqual(self.register(photo=False).status_code, 201)
        self.condo.kiosk_walk_in = False
        self.condo.save()
        self.assertEqual(self.register().status_code, 409)

    def test_blocked_visitor(self, _):
        m.Visitor.objects.create(condominium=self.condo, full_name="Bad Guy", phone="+6591234567", is_blacklisted=True)
        response = self.register(name="Bad Guy", visitor_phone="9123 4567")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(m.WalkInPass.objects.exists())
        self.assertEqual(m.AccessLog.objects.get().method, m.AccessLog.Method.WALK_IN)

    def test_directory_lists_every_unit_for_walk_ins(self, _):
        self.assertEqual(self.client.get("/v1/kiosk/directory/").data, [])
        self.assertEqual(len(self.client.get("/v1/kiosk/directory/?walk_in=1").data), 1)

    def test_check_out_with_slip_qr(self, _):
        self.register()
        walk_in = m.WalkInPass.objects.get()
        url = "/v1/kiosk/walk-ins/checkout/"
        self.assertEqual(self.client.post(url, {"code": "nonsense"}).status_code, 404)
        self.assertEqual(self.client.post(url, {"code": walk_in.token}).status_code, 404)  # Needs the prefix.
        response = self.client.post(url, {"code": walk_in.qr_payload})
        self.assertEqual(response.data["result"], "checked_out")
        self.assertEqual(response.data["walk_in"]["state"], "checked_out")
        self.assertEqual(self.client.post(url, {"code": walk_in.qr_payload}).data["result"], "already_checked_out")

        other = make_condo("beta")
        other_kiosk = m.Kiosk.objects.create(condominium=other, name="Other")
        token = other_kiosk.issue_token()
        other_kiosk.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")
        self.assertEqual(client.post(url, {"code": walk_in.qr_payload}).status_code, 404)

    def test_dashboard_list_and_guard_check_out(self, _):
        self.register()
        self.register("delivery", photo=True)
        guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        client = APIClient()
        client.force_authenticate(guard)
        listed = client.get("/v1/walk-ins/?state=on_site").data["results"]
        self.assertEqual({w["pass_number"] for w in listed}, {"V001", "D001"})
        self.assertTrue(listed[0]["has_snapshot"])
        target = next(w for w in listed if w["pass_number"] == "D001")
        self.assertEqual(client.get(f"/v1/walk-ins/{target['id']}/snapshot/").status_code, 200)
        response = client.post(f"/v1/walk-ins/{target['id']}/check_out/")
        self.assertEqual(response.data["state"], "checked_out")
        self.assertEqual(m.WalkInPass.objects.get(pk=target["id"]).checked_out_by, guard)
        self.assertEqual([w["pass_number"] for w in client.get("/v1/walk-ins/?state=on_site").data["results"]], ["V001"])

        outsider = make_staff("outsider", make_condo("beta"), m.StaffAssignment.Role.SECURITY)
        client.force_authenticate(outsider)
        self.assertEqual(client.get("/v1/walk-ins/").data["count"], 0)

    def test_pass_expires_at_end_of_local_day(self, _):
        self.register()
        walk_in = m.WalkInPass.objects.get()
        day, end = walk_ins.local_day(self.condo)
        self.assertEqual(walk_in.issued_on, day)
        self.assertEqual(walk_in.valid_until, end)
        self.assertEqual(walk_in.state, "on_site")
        with mock.patch("core.models.visitors.timezone.now", return_value=end + timedelta(seconds=2)):
            self.assertEqual(walk_in.state, "expired")

    def test_pdpa_purge_and_erasure(self, _):
        self.register()
        self.register("contractor", name="Lim")
        old = m.WalkInPass.objects.get(pass_number="V001")
        m.WalkInPass.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=200))
        counts = privacy.purge_condominium(self.condo)
        self.assertEqual((counts["walk_ins"], counts["walk_in_photos"]), (1, 1))
        old.refresh_from_db()
        self.assertEqual((old.visitor_name, old.visitor_snapshot.name, old.pass_number), (privacy.REMOVED, "", "V001"))

        recent = m.WalkInPass.objects.get(pass_number="C001")
        privacy.erase_visitor(recent.visitor)
        recent.refresh_from_db()
        self.assertEqual((recent.visitor_name, recent.visitor, recent.visitor_snapshot.name), (privacy.REMOVED, None, ""))
