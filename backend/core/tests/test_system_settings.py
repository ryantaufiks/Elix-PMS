import json
from unittest import mock

import jwt
from django.db import connection
from django.test import TestCase, override_settings

from core import config, livekit, push
from core import models as m

URL = "/v1/admin/core/systemsettings/1/change/"
FCM_JSON = json.dumps({"type": "service_account", "project_id": "elix-sg", "client_email": "x@elix-sg.iam",
                       "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"})


def form(**kw):
    return {"livekit_url": "", "livekit_api_key": "", "livekit_api_secret": "", "livekit_token_ttl_seconds": "",
            "intercom_unlock_window_seconds": "", "fcm_service_account_json": "", "relay_http_timeout": "",
            "lpr_debounce_seconds": "", "_continue": "Save", **kw}


@override_settings(LIVEKIT_URL="wss://env.livekit.cloud", LIVEKIT_API_KEY="envkey", LIVEKIT_API_SECRET="e" * 32,
                   LPR_DEBOUNCE_SECONDS=20, FCM_SERVICE_ACCOUNT_FILE="")
class SystemSettingsTests(TestCase):
    def setUp(self):
        self.client.force_login(m.User.objects.create_superuser("root", "root@example.com", "pw-123456!"))

    def test_blank_falls_back_to_env_and_admin_value_wins(self):
        self.assertEqual(config.get("LIVEKIT_URL"), "wss://env.livekit.cloud")
        m.SystemSettings.objects.create(livekit_url="wss://admin.livekit.cloud", lpr_debounce_seconds=0)
        self.assertEqual(config.get("LIVEKIT_URL"), "wss://admin.livekit.cloud")
        self.assertEqual(config.get("LIVEKIT_API_KEY"), "envkey")
        self.assertEqual(config.get("LPR_DEBOUNCE_SECONDS"), 0)  # 0 is a real value, not "unset"
        self.assertEqual((config.source("LIVEKIT_URL"), config.source("LIVEKIT_API_KEY")), ("admin", ".env"))

    def test_changelist_opens_the_single_row(self):
        response = self.client.get("/v1/admin/core/systemsettings/")
        self.assertRedirects(response, URL)
        self.assertEqual(m.SystemSettings.objects.count(), 1)

    def test_secrets_saved_encrypted_never_rendered_and_used_for_tokens(self):
        self.client.get("/v1/admin/core/systemsettings/")
        response = self.client.post(URL, form(livekit_url=" wss://admin.livekit.cloud ", livekit_api_key="APIadmin",
                                               livekit_api_secret="s" * 32, fcm_service_account_json=FCM_JSON))
        self.assertEqual(response.status_code, 302)
        page = self.client.get(URL).content.decode()
        self.assertNotIn("s" * 32, page)
        self.assertNotIn("BEGIN PRIVATE KEY", page)
        self.assertIn("Configured (admin)", page)

        self.client.post(URL, form(livekit_url="wss://admin.livekit.cloud", livekit_api_key="APIadmin"))
        row = m.SystemSettings.load()
        self.assertEqual((row.livekit_api_secret, row.fcm_service_account_json), ("s" * 32, FCM_JSON))
        with connection.cursor() as cursor:
            cursor.execute("SELECT livekit_api_secret FROM core_systemsettings")
            self.assertTrue(cursor.fetchone()[0].startswith("enc$"))

        info = livekit.connection_info("room-1", "kiosk-1")
        self.assertEqual(info["url"], "wss://admin.livekit.cloud")
        claims = jwt.decode(info["token"], "s" * 32, algorithms=["HS256"])
        self.assertEqual(claims["iss"], "APIadmin")
        self.assertTrue(push.is_enabled())

    def test_invalid_values_rejected(self):
        self.client.get("/v1/admin/core/systemsettings/")
        response = self.client.post(URL, form(livekit_url="livekit.cloud", fcm_service_account_json='{"project_id": "x"}'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Must start with wss://")
        self.assertContains(response, "Missing client_email, private_key")

    @mock.patch("core.livekit.list_rooms", return_value=[{"name": "a"}])
    def test_save_and_test_livekit_button(self, list_rooms):
        self.client.get("/v1/admin/core/systemsettings/")
        response = self.client.post(URL, form(_test_livekit="1"), follow=True)
        self.assertContains(response, "LiveKit OK - 1 active room(s).")
        list_rooms.side_effect = RuntimeError("401 Unauthorized")
        response = self.client.post(URL, form(_test_livekit="1"), follow=True)
        self.assertContains(response, "LiveKit test failed: 401 Unauthorized")

    def test_cannot_add_or_delete(self):
        self.client.get("/v1/admin/core/systemsettings/")
        self.assertEqual(self.client.get("/v1/admin/core/systemsettings/add/").status_code, 403)
        self.assertEqual(self.client.get("/v1/admin/core/systemsettings/1/delete/").status_code, 403)
