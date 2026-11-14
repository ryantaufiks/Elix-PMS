from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from core import models as m

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit

ADMIN, SECURITY = m.StaffAssignment.Role.ADMIN, m.StaffAssignment.Role.SECURITY


class TenantScopingTests(APITestCase):
    def setUp(self):
        self.alpha, self.beta = make_condo("alpha"), make_condo("beta")
        self.alpha_unit, self.alpha_unit2 = make_unit(self.alpha, "05", "12"), make_unit(self.alpha, "06", "01")
        self.beta_unit = make_unit(self.beta)
        self.alpha_gate = m.AccessGate.objects.create(condominium=self.alpha, name="Main")
        self.beta_gate = m.AccessGate.objects.create(condominium=self.beta, name="Main")
        self.admin = make_staff("alpha-admin", self.alpha, ADMIN)
        self.guard = make_staff("alpha-guard", self.alpha, SECURITY)
        self.resident = make_resident("alpha-resident", self.alpha_unit)

    def ids(self, response):
        return {row["id"] for row in response.data["results"]}

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/v1/gates/").status_code, 401)

    def test_health_is_public(self):
        self.assertEqual(self.client.get("/v1/health/").status_code, 200)

    def test_jwt_login_and_me(self):
        response = self.client.post("/v1/auth/token/", {"username": "alpha-admin", "password": "pw-123456!"})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me = self.client.get("/v1/auth/me/")
        self.assertEqual(me.data["staff_assignments"][0]["role"], ADMIN)

    def test_admin_sees_only_own_condo(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.ids(self.client.get("/v1/gates/")), {self.alpha_gate.id})
        self.assertEqual(self.client.get(f"/v1/gates/{self.beta_gate.id}/").status_code, 404)

    def test_admin_cannot_create_in_other_condo(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/v1/gates/", {"condominium": self.beta.id, "name": "Side"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/v1/gates/", {"condominium": self.alpha.id, "name": "Side"})
        self.assertEqual(response.status_code, 201)

    def test_security_cannot_see_device_credentials(self):
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/v1/integration-accounts/").data["count"], 0)
        self.assertEqual(self.client.get("/v1/relays/").data["count"], 0)
        self.assertEqual(self.client.post("/v1/gates/", {"condominium": self.alpha.id, "name": "X"}).status_code, 403)

    def test_resident_vehicles_limited_to_own_unit(self):
        m.Vehicle.objects.create(unit=self.alpha_unit2, plate_number="SBA1111A")
        self.client.force_authenticate(self.resident)
        response = self.client.post("/v1/vehicles/", {"unit": self.alpha_unit.id, "plate_number": "sgx 1234 b"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["plate_number"], "SGX1234B")
        self.assertEqual(response.data["condominium"], self.alpha.id)
        self.assertEqual(self.client.get("/v1/vehicles/").data["count"], 1)
        response = self.client.post("/v1/vehicles/", {"unit": self.alpha_unit2.id, "plate_number": "SGX9999C"})
        self.assertEqual(response.status_code, 403)

    def test_only_management_sets_vehicle_passes(self):
        today = timezone.localdate()
        self.client.force_authenticate(self.resident)
        response = self.client.post("/v1/vehicles/", {"unit": self.alpha_unit.id, "plate_number": "SGX1B", "kind": "season",
                                                      "valid_until": str(today + timedelta(days=400))}, format="json")
        self.assertEqual((response.data["kind"], response.data["valid_until"]), ("resident", None))
        self.client.force_authenticate(self.admin)
        response = self.client.post("/v1/vehicles/", {"unit": self.alpha_unit.id, "plate_number": "SGX2C", "kind": "season"}, format="json")
        self.assertIn("valid_until", response.data)  # A season pass needs an end date.
        response = self.client.post("/v1/vehicles/", {"unit": self.alpha_unit.id, "plate_number": "SGX2C", "kind": "season",
                                                      "holder_name": "Mr Lee", "valid_until": str(today + timedelta(days=5))}, format="json")
        self.assertEqual((response.status_code, response.data["status"]), (201, "expiring"))
        self.assertEqual(self.client.get("/v1/vehicles/", {"status": "expiring"}).data["count"], 1)
        # The unit's resident is reminded in the app's notifications.
        self.client.force_authenticate(self.resident)
        kinds = [n["kind"] for n in self.client.get("/v1/notifications/").data["results"]]
        self.assertIn("vehicle_expiring", kinds)

    def test_integration_secrets_are_write_only(self):
        self.client.force_authenticate(self.admin)
        payload = {
            "condominium": self.alpha.id, "provider": "ewelink", "label": "Main",
            "ewelink_app_id": "appid", "ewelink_app_secret": "s3cret", "ewelink_access_token": "tok",
        }
        response = self.client.post("/v1/integration-accounts/", payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("ewelink_app_secret", response.data)
        self.assertTrue(response.data["has_ewelink_app_secret"])
        self.assertFalse(response.data["has_shelly_auth_key"])
        # Blank on update keeps the stored secret.
        url = f"/v1/integration-accounts/{response.data['id']}/"
        self.client.patch(url, {"ewelink_app_secret": "", "label": "Renamed"})
        account = m.IntegrationAccount.objects.get(pk=response.data["id"])
        self.assertEqual((account.label, account.ewelink_app_secret), ("Renamed", "s3cret"))

    def test_kiosk_token_shown_once(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/v1/kiosks/", {"condominium": self.alpha.id, "name": "Lobby"})
        self.assertEqual(response.status_code, 201)
        token = response.data["token"]
        kiosk = m.Kiosk.objects.get(pk=response.data["id"])
        self.assertEqual(kiosk.token_hash, m.Kiosk.hash_token(token))
        self.assertNotIn("token", self.client.get(f"/v1/kiosks/{kiosk.id}/").data)


class InvitationApiTests(APITestCase):
    def setUp(self):
        self.condo = make_condo("alpha")
        self.unit, self.other_unit = make_unit(self.condo, "05", "12"), make_unit(self.condo, "07", "03")
        self.resident = make_resident("resident", self.unit)
        self.client.force_authenticate(self.resident)

    def payload(self, **kw):
        now = timezone.now()
        return {"unit": self.unit.id, "visitor_name": "Lim Mei Ling", "valid_from": now.isoformat(),
                "valid_until": (now + timedelta(hours=4)).isoformat(), **kw}

    def test_resident_creates_invitation_and_gets_qr(self):
        response = self.client.post("/v1/invitations/", self.payload(vehicle_plate="sba 1 a"))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["host"], self.resident.id)
        self.assertEqual(response.data["vehicle_plate"], "SBA1A")
        self.assertIn("/i/", response.data["share_url"])
        qr = self.client.get(f"/v1/invitations/{response.data['id']}/qr/")
        self.assertEqual(qr["Content-Type"], "image/png")
        self.assertTrue(qr.content.startswith(b"\x89PNG"))

    def test_resident_cannot_invite_to_other_unit(self):
        response = self.client.post("/v1/invitations/", self.payload(unit=self.other_unit.id))
        self.assertEqual(response.status_code, 403)

    def test_invalid_window_rejected(self):
        now = timezone.now()
        response = self.client.post("/v1/invitations/", self.payload(valid_until=(now - timedelta(hours=1)).isoformat()))
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid_until", response.data)

    def test_cancel(self):
        invitation = make_invitation(self.unit, self.resident)
        response = self.client.post(f"/v1/invitations/{invitation.id}/cancel/")
        self.assertEqual(response.data["status"], "cancelled")
        self.assertEqual(self.client.post(f"/v1/invitations/{invitation.id}/cancel/").status_code, 400)
