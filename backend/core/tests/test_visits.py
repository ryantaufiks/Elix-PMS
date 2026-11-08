import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from core import models as m
from core import access, intercom, privacy, visits

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit
from .test_checkin import jpeg


@mock.patch("core.visits.broadcast")
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
        walk_in = m.Visit.objects.get(pass_number="C002")
        self.assertEqual(walk_in.company, "Ace Aircon")
        self.assertTrue(walk_in.visitor_snapshot)
        self.assertEqual(walk_in.visitor.full_name, "Tan Ah Kow")
        self.assertFalse(m.AccessLog.objects.exists())  # The gate is not opened.

        # Next day the series restarts.
        with mock.patch("core.visits.timezone.now", return_value=timezone.now() + timedelta(days=1)):
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
        self.assertFalse(m.Visit.objects.exists())
        self.assertEqual(m.AccessLog.objects.get().method, m.AccessLog.Method.WALK_IN)

    def test_directory_lists_every_unit_for_walk_ins(self, _):
        self.assertEqual(self.client.get("/v1/kiosk/directory/").data, [])
        self.assertEqual(len(self.client.get("/v1/kiosk/directory/?walk_in=1").data), 1)

    def test_check_out_with_slip_qr(self, _):
        self.register()
        walk_in = m.Visit.objects.get()
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
        listed = client.get("/v1/visits/?state=on_site").data["results"]
        self.assertEqual({w["pass_number"] for w in listed}, {"V001", "D001"})
        self.assertTrue(listed[0]["has_snapshot"])
        target = next(w for w in listed if w["pass_number"] == "D001")
        self.assertEqual(client.get(f"/v1/visits/{target['id']}/snapshot/").status_code, 200)
        response = client.post(f"/v1/visits/{target['id']}/check_out/")
        self.assertEqual(response.data["state"], "checked_out")
        self.assertEqual(m.Visit.objects.get(pk=target["id"]).checked_out_by, guard)
        self.assertEqual([w["pass_number"] for w in client.get("/v1/visits/?state=on_site").data["results"]], ["V001"])

        outsider = make_staff("outsider", make_condo("beta"), m.StaffAssignment.Role.SECURITY)
        client.force_authenticate(outsider)
        self.assertEqual(client.get("/v1/visits/").data["count"], 0)

    def test_pass_expires_at_end_of_local_day(self, _):
        self.register()
        walk_in = m.Visit.objects.get()
        day, end = visits.local_day(self.condo)
        self.assertEqual(walk_in.issued_on, day)
        self.assertEqual(walk_in.valid_until, end)
        self.assertEqual(walk_in.state, "on_site")
        with mock.patch("core.models.visitors.timezone.now", return_value=end + timedelta(seconds=2)):
            self.assertEqual(walk_in.state, "expired")

    def test_pdpa_purge_and_erasure(self, _):
        self.register()
        self.register("contractor", name="Lim")
        old = m.Visit.objects.get(pass_number="V001")
        m.Visit.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=200))
        counts = privacy.purge_condominium(self.condo)
        self.assertEqual((counts["visits"], counts["visit_photos"]), (1, 1))
        old.refresh_from_db()
        self.assertEqual((old.visitor_name, old.visitor_snapshot.name, old.pass_number), (privacy.REMOVED, "", "V001"))

        recent = m.Visit.objects.get(pass_number="C001")
        privacy.erase_visitor(recent.visitor)
        recent.refresh_from_db()
        self.assertEqual((recent.visitor_name, recent.visitor, recent.visitor_snapshot.name), (privacy.REMOVED, None, ""))


    def test_pins_unique_on_site_and_check_out_with_pin(self, _):
        cache.clear()
        self.addCleanup(cache.clear)
        slips = [self.register(name=f"Visitor {i}").data for i in range(5)]
        pins = [slip["pin"] for slip in slips]
        self.assertTrue(all(len(p) == 4 and p.isdigit() for p in pins))
        self.assertEqual(len(set(pins)), 5)

        url = "/v1/kiosk/checkout/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        response = self.client.post(url, {"pin": pins[0]}, format="json")
        self.assertEqual((response.data["result"], response.data["walk_in"]["pass_number"]), ("checked_out", "V001"))
        # A PIN only works while the visitor is on site; the QR still answers "already checked out".
        self.assertEqual(self.client.post(url, {"pin": pins[0]}, format="json").status_code, 404)
        qr = m.Visit.objects.get(pass_number="V001").qr_payload
        self.assertEqual(self.client.post(url, {"code": qr}, format="json").data["result"], "already_checked_out")

        self.condo.kiosk_checkout = False
        self.condo.save()
        self.assertEqual(self.client.post(url, {"pin": pins[1]}, format="json").status_code, 409)

    def test_wrong_pins_lock_the_kiosk_for_a_minute(self, _):
        cache.clear()
        self.addCleanup(cache.clear)
        pin = self.register().data["pin"]
        wrong = f"{(int(pin) + 1) % 10_000:04d}"
        url = "/v1/kiosk/checkout/"
        for _attempt in range(5):
            self.assertEqual(self.client.post(url, {"pin": wrong}, format="json").status_code, 404)
        self.assertEqual(self.client.post(url, {"pin": pin}, format="json").status_code, 429)
        self.assertIsNone(m.Visit.objects.get().checked_out_at)

    def test_pass_shown_after_the_resident_opens_the_gate(self, _):
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, kiosk=self.kiosk, gate=self.gate,
                                             room_name="r-pass", visitor_name="Siti", visitor_purpose="guest")
        url = f"/v1/kiosk/calls/{call.pk}/pass/"
        self.assertEqual(self.client.get(url).status_code, 404)
        intercom.unlock(call, make_resident("host", self.unit))
        slip = self.client.get(url).data
        self.assertEqual((slip["pass_number"], slip["visitor_name"], len(slip["pin"])), ("V001", "Siti", 4))
        other = m.Kiosk.objects.create(condominium=self.condo, name="Side kiosk")
        token = other.issue_token()
        other.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")
        self.assertEqual(self.client.get(url).status_code, 404)  # Only the kiosk that placed the call.

    def test_visitor_records_show_last_check_in_and_out(self, _):
        self.register(visitor_phone="9123 4567")
        visitor = m.Visitor.objects.get()
        staff = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        client = APIClient()
        client.force_authenticate(staff)
        row = client.get(f"/v1/visitors/?condominium={self.condo.pk}").data["results"][0]
        self.assertTrue(row["on_site"])
        self.assertIsNotNone(row["last_check_in"])
        self.assertIsNone(row["last_check_out"])
        self.assertEqual(row["visit_count"], 1)
        visits.check_out(m.Visit.objects.get())
        row = client.get(f"/v1/visitors/{visitor.pk}/").data
        self.assertFalse(row["on_site"])
        self.assertIsNotNone(row["last_check_out"])
        history = client.get(f"/v1/visits/?visitor={visitor.pk}").data
        self.assertEqual(history["count"], 1)


@mock.patch("core.visits.broadcast")
@mock.patch("core.tasks.open_gate.delay")
class VisitSourcesTests(APITestCase):
    """Invitation and intercom check-ins also put the visitor on the list."""

    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby")
        self.kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby kiosk", gate=self.gate)
        self.host = make_resident("alice", self.unit)

    def test_invitation_qr_creates_one_visit_per_day(self, *_):
        invitation = make_invitation(self.unit, self.host, purpose="contractor", max_entries=0)
        log = access.handle_qr(self.kiosk, invitation.token)
        self.assertEqual(log.result, "granted")
        visit = m.Visit.objects.get()
        self.assertEqual((visit.source, visit.pass_number, visit.invitation, visit.entry_log), ("invitation", "C001", invitation, log))
        access.handle_qr(self.kiosk, invitation.token)  # Re-entry the same day: same visit.
        self.assertEqual(m.Visit.objects.count(), 1)

    def test_invited_plate_in_and_out(self, *_):
        invitation = make_invitation(self.unit, self.host, vehicle_plate="SGX1234A", max_entries=0)
        entry = m.LprCamera.objects.create(gate=self.gate, name="In", device_id="IN-1", webhook_username="in")
        exit_ = m.LprCamera.objects.create(gate=self.gate, name="Out", device_id="OUT-1", webhook_username="out", direction=m.Direction.EXIT)
        access.handle_plate(entry, "SGX1234A", {})
        visit = m.Visit.objects.get()
        self.assertEqual((visit.vehicle_plate, visit.state), ("SGX1234A", "on_site"))
        access.handle_plate(exit_, "SGX1234A", {})
        visit.refresh_from_db()
        self.assertEqual(visit.state, "checked_out")
        self.assertIsNone(visit.checked_out_by)
        self.assertEqual(invitation.visits.count(), 1)

    def test_intercom_unlock_creates_visit(self, *_):
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, kiosk=self.kiosk, gate=self.gate,
                                             room_name="r1", visitor_name="Grab rider", visitor_purpose="food",
                                             visitor_company="GrabFood")
        intercom.unlock(call, self.host)
        visit = m.Visit.objects.get()
        self.assertEqual((visit.source, visit.pass_number, visit.company, visit.intercom_call), ("intercom", "F001", "GrabFood", call))

    def test_recording_a_visit_never_blocks_the_gate(self, *_):
        invitation = make_invitation(self.unit, self.host)
        with mock.patch("core.visits.create", side_effect=RuntimeError("boom")):
            log = access.handle_qr(self.kiosk, invitation.token)
        self.assertEqual(log.result, "granted")
        self.assertFalse(m.Visit.objects.exists())


@mock.patch("core.visits.broadcast")
class OfficerVisitTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        self.client.force_authenticate(self.guard)

    def register(self, **extra):
        data = {"unit": self.unit.pk, "visitor_name": "Ahmad", "purpose": "contractor", "company": "Ace",
                "visitor_phone": "9123 4567", "vehicle_plate": "gbc 123 x", "notes": "Aircon servicing", "consent": True, **extra}
        return self.client.post("/v1/visits/", data, format="json")

    def test_register_edit_slip_and_check_out(self, _):
        response = self.register()
        self.assertEqual(response.status_code, 201, response.data)
        visit = m.Visit.objects.get()
        self.assertEqual((visit.source, visit.pass_number, visit.vehicle_plate, visit.created_by), ("staff", "C001", "GBC123X", self.guard))
        self.assertEqual(response.data["created_by_name"], "guard")
        self.assertEqual(str(visit.visitor.phone), "+6591234567")

        patched = self.client.patch(f"/v1/visits/{visit.pk}/", {"notes": "Left ladder at lobby", "pass_number": "X999"}, format="json")
        self.assertEqual(patched.status_code, 200)
        visit.refresh_from_db()
        self.assertEqual((visit.notes, visit.pass_number), ("Left ladder at lobby", "C001"))

        slip = self.client.get(f"/v1/visits/{visit.pk}/slip/").data
        self.assertEqual((slip["pass_number"], slip["vehicle_plate"]), ("C001", "GBC123X"))
        self.assertTrue(slip["qr"].startswith("data:image/png"))
        self.assertEqual(self.client.delete(f"/v1/visits/{visit.pk}/").status_code, 405)

    def test_consent_and_blocked_visitor(self, _):
        self.assertIn("consent", self.register(consent=False).data)
        m.Visitor.objects.create(condominium=self.condo, full_name="Ahmad", phone="+6591234567", is_blacklisted=True,
                                 blacklist_reason="Theft")
        response = self.register()
        self.assertEqual(response.status_code, 403)
        self.assertIn("Theft", response.data["detail"])

    def test_bulk_check_out(self, _):
        for name in ("A", "B", "C"):
            self.register(visitor_name=name, visitor_phone="")
        ids = list(m.Visit.objects.values_list("pk", flat=True))
        other = make_condo("beta")
        stranger = visits.create(other.pk, unit=make_unit(other), purpose="guest", name="X", source="staff")
        response = self.client.post("/v1/visits/bulk_check_out/", {"ids": ids[:2] + [stranger.pk]}, format="json")
        self.assertEqual(response.data["checked_out"], 2)
        self.assertEqual(self.client.post("/v1/visits/bulk_check_out/", {"ids": ids}, format="json").data["checked_out"], 1)
        stranger.refresh_from_db()
        self.assertIsNone(stranger.checked_out_at)
        self.assertEqual(m.Visit.objects.filter(checked_out_by=self.guard).count(), 3)

    def test_residents_cannot_register_or_check_out(self, _):
        self.register()
        resident = make_resident("res", self.unit)
        self.client.force_authenticate(resident)
        self.assertEqual(self.register().status_code, 403)
        visit = m.Visit.objects.get()
        self.assertEqual(self.client.post(f"/v1/visits/{visit.pk}/check_out/").status_code, 403)
        self.assertEqual(self.client.patch(f"/v1/visits/{visit.pk}/", {"notes": "x"}, format="json").status_code, 403)
