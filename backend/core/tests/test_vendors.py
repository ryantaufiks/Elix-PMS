from datetime import datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.test import APITestCase

from core import access, entitlements, visits
from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit

SG = ZoneInfo("Asia/Singapore")


def on(weekday, hour):
    """A moment this coming week on ``weekday`` (Monday = 0) at ``hour``:00, Singapore time."""
    today = timezone.localdate()
    day = today + timedelta(days=(weekday - today.weekday()) % 7)
    return datetime.combine(day, time(hour), tzinfo=SG)


@mock.patch("core.visits.broadcast")
@mock.patch("core.tasks.open_gate.delay")
class VendorTests(APITestCase):
    def setUp(self):
        self.condo = make_condo(contractor_hours_enforced=True, contractor_days=[0, 1, 2, 3, 4], contractor_from=time(9),
                                overstay_contractor_until=time(17), lpr_enabled=True)
        self.unit = make_unit(self.condo)
        self.admin = make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def test_contractor_working_hours(self, *_):
        self.assertEqual(m.contractor_hours_problem(self.condo, on(2, 10)), "")
        self.assertEqual(m.contractor_hours_problem(self.condo, on(2, 18)), "Contractors may work Mon–Fri, 09:00–17:00.")
        self.assertIn("Mon–Fri", m.contractor_hours_problem(self.condo, on(6, 10)))  # Sunday.
        self.condo.contractor_hours_enforced = False
        self.assertEqual(m.contractor_hours_problem(self.condo, on(6, 10)), "")

    def test_office_and_vendor_pass(self, *_):
        office = self.client.get("/v1/units/office/", {"condominium": self.condo.pk}).data
        self.assertEqual(office["id"], m.Unit.office_of(self.condo.pk).pk)
        self.assertNotIn(office["id"], [u["id"] for u in self.client.get("/v1/units/", {"condominium": self.condo.pk}).data["results"]])
        self.assertEqual(entitlements.usage(self.condo)["units"], 1)  # The office does not count.
        with self.assertRaises(Exception):
            m.Residency(user=make_resident("res", self.unit), unit=m.Unit.objects.get(pk=office["id"])).full_clean()

        start = on(0, 0)
        response = self.client.post("/v1/invitations/", {
            "unit": office["id"], "visitor_name": "Lift technician", "company": "Acme Lifts", "purpose": "contractor",
            "valid_from": start.isoformat(), "valid_until": (start + timedelta(days=13)).isoformat(),
            "weekdays": [0, 2, 4], "daily_from": "10:00", "daily_until": "16:00", "max_entries": 0, "vehicle_plate": "GBA1A",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["schedule"], response.data["unit_display"]), ("Mon, Wed, Fri, 10:00–16:00", "Management office"))
        invitation = m.Invitation.objects.get()
        self.assertEqual(invitation.check_usable(on(2, 11)), (True, ""))
        self.assertIn("Mon, Wed, Fri", invitation.check_usable(on(1, 11))[1])
        self.assertIn("10:00–16:00", invitation.check_usable(on(2, 9))[1])
        self.assertEqual(self.client.get("/v1/invitations/", {"condominium": self.condo.pk, "vendor": 1}).data["count"], 1)

        # At the barrier: the plate opens only within the pass's days and hours.
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        camera = m.LprCamera(gate=gate, name="Entry", device_id="CAM", webhook_username="cam")
        camera.set_webhook_password("pw")
        camera.save()
        with mock.patch("core.access.timezone.now", return_value=on(1, 11)), \
                mock.patch("core.models.visitors.timezone.now", return_value=on(1, 11)):
            log = access.handle_plate(camera, "GBA1A", {})
        self.assertEqual((log.result, log.invitation), ("denied", invitation))
        with mock.patch("core.access.timezone.now", return_value=on(2, 11)), \
                mock.patch("core.models.visitors.timezone.now", return_value=on(2, 11)):
            log = access.handle_plate(camera, "GBA1A", {})
        self.assertEqual(log.result, "granted", log.reason)
        visit = m.Visit.objects.get()
        self.assertEqual(visit.company, "Acme Lifts")
        m.Visit.objects.filter(pk=visit.pk).update(created_at=on(2, 11))
        visit.refresh_from_db()
        self.assertEqual(timezone.localtime(visits.overstay_at(visit)).strftime("%H:%M"), "16:00")

    def test_contractor_invitation_follows_working_hours(self, *_):
        resident = make_resident("res", self.unit)
        invitation = m.Invitation.objects.create(condominium=self.condo, unit=self.unit, host=resident, visitor_name="Ace Reno",
                                                 purpose="contractor", valid_from=on(0, 0) - timedelta(days=7),
                                                 valid_until=on(0, 0) + timedelta(days=14))
        self.assertTrue(invitation.check_usable(on(3, 10))[0])
        self.assertIn("Contractors may work", invitation.check_usable(on(5, 10))[1])  # Saturday is not a working day here.
