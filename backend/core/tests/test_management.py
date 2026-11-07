from unittest import mock

from rest_framework.test import APITestCase

from core import models as m
from core.relays import RelayError, RelayResult

from .factories import make_condo, make_resident, make_staff, make_unit

ADMIN, SECURITY = m.StaffAssignment.Role.ADMIN, m.StaffAssignment.Role.SECURITY


class PeopleTests(APITestCase):
    def setUp(self):
        self.condo, self.other = make_condo("alpha"), make_condo("beta")
        self.unit, self.other_unit = make_unit(self.condo), make_unit(self.other)
        self.admin = make_staff("boss", self.condo, ADMIN)
        self.client.force_authenticate(self.admin)

    def test_admin_creates_resident_with_unit_and_password(self):
        response = self.client.post("/v1/users/", {
            "username": "tan", "first_name": "Tan", "password": "Str0ng-pass-99",
            "residency": {"unit": self.unit.pk, "resident_type": "tenant"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = m.User.objects.get(username="tan")
        self.assertTrue(user.check_password("Str0ng-pass-99"))
        self.assertEqual(user.residencies.get().resident_type, "tenant")
        self.assertNotIn("password", response.data)

    def test_new_person_must_be_attached_and_only_to_own_condo(self):
        self.assertEqual(self.client.post("/v1/users/", {"username": "loose"}, format="json").status_code, 400)
        response = self.client.post("/v1/users/", {"username": "x", "residency": {"unit": self.other_unit.pk}}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/v1/users/", {"username": "y", "staff": {"condominium": self.other.pk, "role": "admin"}}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(m.User.objects.filter(username__in=["x", "y"]).exists())

    def test_admin_sees_and_edits_only_own_people(self):
        mine = make_resident("mine", self.unit)
        shared = make_resident("shared", self.unit)
        m.Residency.objects.create(user=shared, unit=self.other_unit)
        stranger = make_resident("stranger", self.other_unit)
        names = {u["username"] for u in self.client.get("/v1/users/").data["results"]}
        self.assertEqual(names, {"boss", "mine", "shared"})
        self.assertEqual(self.client.get(f"/v1/users/{stranger.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/v1/users/{mine.pk}/", {"first_name": "Mei"}).status_code, 200)
        self.assertEqual(self.client.patch(f"/v1/users/{shared.pk}/", {"first_name": "No"}).status_code, 403)
        self.assertEqual(self.client.post(f"/v1/users/{mine.pk}/set-password/", {"password": "An0ther-pass-77"}).status_code, 204)
        mine.refresh_from_db()
        self.assertTrue(mine.check_password("An0ther-pass-77"))

    def test_security_cannot_manage_people(self):
        self.client.force_authenticate(make_staff("guard", self.condo, SECURITY))
        self.assertEqual(self.client.get("/v1/users/").data["count"], 0)
        response = self.client.post("/v1/users/", {"username": "z", "residency": {"unit": self.unit.pk}}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_condo_admin_cannot_deactivate_or_delete_own_condo(self):
        url = f"/v1/condominiums/{self.condo.pk}/"
        self.assertEqual(self.client.patch(url, {"lpr_enabled": True}).status_code, 200)
        self.assertTrue(m.Condominium.objects.get(pk=self.condo.pk).lpr_enabled)
        self.assertEqual(self.client.patch(url, {"is_active": False}).status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)


class SetupTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.admin = make_staff("boss", self.condo, ADMIN)
        self.client.force_authenticate(self.admin)
        self.block = m.Block.objects.create(condominium=self.condo, name="Tower A")

    def test_bulk_units_skips_existing(self):
        m.Unit.objects.create(condominium=self.condo, block=self.block, floor="02", unit_number="01")
        body = {"condominium": self.condo.pk, "block": self.block.pk, "floor_from": 2, "floor_to": 4, "units": "01-03, 10"}
        response = self.client.post("/v1/units/bulk/", body, format="json")
        self.assertEqual((response.status_code, response.data), (201, {"created": 11, "skipped": 1}))
        self.assertTrue(m.Unit.objects.filter(floor="04", unit_number="10").exists())
        self.client.force_authenticate(make_staff("guard", self.condo, SECURITY))
        self.assertEqual(self.client.post("/v1/units/bulk/", body, format="json").status_code, 403)

    def test_block_in_use_returns_conflict(self):
        m.Unit.objects.create(condominium=self.condo, block=self.block, floor="02", unit_number="01")
        response = self.client.delete(f"/v1/blocks/{self.block.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertIn("units", response.data["detail"])

    @mock.patch("core.relays.pulse")
    def test_relay_test_button(self, pulse):
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        relay = m.RelayController.objects.create(gate=gate, name="R1", provider="shelly")
        pulse.return_value = RelayResult(via="cloud", detail="switched")
        self.assertEqual(self.client.post(f"/v1/relays/{relay.pk}/test/").data, {"ok": True, "via": "cloud", "detail": "switched"})
        pulse.side_effect = RelayError("Timed out")
        response = self.client.post(f"/v1/relays/{relay.pk}/test/")
        self.assertEqual((response.status_code, response.data["detail"]), (502, "Timed out"))

    def test_camera_exposes_webhook_url_and_payload(self):
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        response = self.client.post("/v1/cameras/", {"gate": gate.pk, "name": "Cam", "device_id": "D1",
                                                     "webhook_username": "cam1", "webhook_password": "pw-123456"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["has_webhook_password"])
        self.assertTrue(response.data["webhook_url"].endswith("/v1/lpr-webhook/"))
        self.assertIn("last_payload", response.data)


class SystemSettingsApiTests(APITestCase):
    def test_superuser_only_and_secret_write_only(self):
        condo = make_condo()
        self.client.force_authenticate(make_staff("boss", condo, ADMIN))
        self.assertEqual(self.client.get("/v1/system-settings/").status_code, 403)
        self.client.force_authenticate(m.User.objects.create_superuser("root", "r@example.com", "pw-123456!"))
        response = self.client.patch("/v1/system-settings/", {"livekit_url": "wss://x.livekit.cloud", "livekit_api_secret": "sekret"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("livekit_api_secret", response.data)
        self.assertTrue(response.data["has_livekit_api_secret"])
        self.assertEqual(response.data["sources"]["livekit_url"], "admin")
        self.client.patch("/v1/system-settings/", {"livekit_api_secret": ""}, format="json")
        self.assertEqual(m.SystemSettings.load().livekit_api_secret, "sekret")
        with mock.patch("core.livekit.list_rooms", return_value=[]):
            self.assertEqual(self.client.post("/v1/system-settings/test-livekit/").data["ok"], True)
