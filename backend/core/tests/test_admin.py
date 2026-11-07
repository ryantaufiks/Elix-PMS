from django.test import TestCase

from core import models as m

from .factories import make_condo


class AdminCredentialFormTests(TestCase):
    def setUp(self):
        self.condo = make_condo()
        self.client.force_login(m.User.objects.create_superuser("root", "root@example.com", "pw-123456!"))

    def form_data(self, **kw):
        return {
            "condominium": self.condo.id, "provider": "shelly", "label": "Shelly main", "is_active": "on",
            "ewelink_region": "as", "shelly_server_uri": "https://shelly-103-eu.shelly.cloud", **kw,
        }

    def test_secret_never_rendered_and_blank_keeps_value(self):
        response = self.client.post("/v1/admin/core/integrationaccount/add/", self.form_data(shelly_auth_key="KEY-123"))
        self.assertEqual(response.status_code, 302)
        account = m.IntegrationAccount.objects.get()
        change_url = f"/v1/admin/core/integrationaccount/{account.id}/change/"

        page = self.client.get(change_url).content.decode()
        self.assertNotIn("KEY-123", page)
        self.assertIn("saved - leave blank to keep", page)

        response = self.client.post(change_url, self.form_data(label="Renamed", shelly_auth_key=""))
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual((account.label, account.shelly_auth_key), ("Renamed", "KEY-123"))

    def test_kiosk_token_issued_on_add(self):
        response = self.client.post("/v1/admin/core/kiosk/add/", {"condominium": self.condo.id, "name": "Lobby", "is_active": "on"}, follow=True)
        kiosk = m.Kiosk.objects.get()
        self.assertTrue(kiosk.token_hash)
        self.assertContains(response, "copy it now")

    def test_camera_requires_webhook_password(self):
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        data = {"gate": gate.id, "name": "Cam", "device_id": "DH-1", "direction": "entry", "webhook_username": "cam1", "is_active": "on"}
        self.assertEqual(self.client.post("/v1/admin/core/lprcamera/add/", data).status_code, 200)
        self.assertEqual(self.client.post("/v1/admin/core/lprcamera/add/", {**data, "webhook_password": "pw"}).status_code, 302)
        self.assertTrue(m.LprCamera.objects.get().check_webhook_password("pw"))
