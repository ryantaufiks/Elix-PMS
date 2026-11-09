import base64
import io
import json
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from core import models as m

from .factories import make_condo, make_staff, make_user

Role = m.StaffAssignment.Role


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, "PNG")
    return SimpleUploadedFile("map.png", buffer.getvalue(), content_type="image/png")


class FakeOpenAI:
    """Stands in for api.openai.com and remembers what was sent."""

    def __init__(self, tool_calls=None, content="The pool is on level 3 of Tower A."):
        self.calls = []
        self.tool_calls = tool_calls or []
        self.content = content

    def __call__(self, url, headers=None, json=None, data=None, files=None, timeout=None):
        self.calls.append({"url": url, "key": headers["Authorization"], "json": json, "data": data})
        response = mock.Mock(status_code=200, content=b"MP3DATA", text="")
        if url.endswith("audio/transcriptions"):
            response.json.return_value = {"text": "Where is the pool?"}
        elif url.endswith("chat/completions"):
            follow = json.get("tool_choice") == "none"
            message = {"content": self.content if (follow or not self.tool_calls) else None,
                       "tool_calls": None if follow else self.tool_calls}
            response.json.return_value = {"choices": [{"message": message}]}
        elif url.endswith("realtime/client_secrets"):
            response.json.return_value = {"value": "ek_test", "expires_at": 0}
        return response

    def sent(self, path):
        return [c for c in self.calls if c["url"].endswith(path)]


class AssistantTests(APITestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media, OPENAI_API_KEY=""))
        self.condo = make_condo()
        self.kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby kiosk")
        self.kiosk_client = self.kiosk_api(self.kiosk)
        settings = m.SystemSettings.load()
        settings.openai_api_key = "sk-platform"
        settings.save()
        m.AssistantSettings.objects.create(condominium=self.condo, enabled=True, name="Ava", greeting="Hello!")
        m.AssistantModule.objects.create(condominium=self.condo, title="Facilities", content="Pool: level 3, Tower A, 7am-10pm.")
        self.map = m.AssistantMap.objects.create(condominium=self.condo, name="Site map", description="Towers and pool", image=png())
        self.admin = make_staff("admin", self.condo, Role.ADMIN)

    def kiosk_api(self, kiosk):
        token = kiosk.issue_token()
        kiosk.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")
        return client

    def openai(self, fake):
        return mock.patch("core.assistant.requests.post", side_effect=fake)

    def start(self):
        response = self.kiosk_client.post("/v1/kiosk/assistant/sessions/")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_kiosk_sees_it_only_when_enabled_with_a_key(self):
        self.assertTrue(self.kiosk_client.get("/v1/kiosk/assistant/").data["enabled"])
        m.SystemSettings.objects.update(openai_api_key="")
        self.assertFalse(self.kiosk_client.get("/v1/kiosk/assistant/").data["enabled"])
        self.assertEqual(self.kiosk_client.post("/v1/kiosk/assistant/sessions/").status_code, 503)

    def test_speech_to_text_turn(self):
        tool = [{"id": "c1", "type": "function", "function": {"name": "show_map", "arguments": json.dumps({"map_id": self.map.pk})}}]
        fake = FakeOpenAI(tool_calls=tool)
        with self.openai(fake):
            session = self.start()
            self.assertEqual(session["mode"], "pipeline")
            self.assertEqual(base64.b64decode(session["greeting_audio"]), b"MP3DATA")
            audio = SimpleUploadedFile("speech.webm", b"webm-bytes", content_type="audio/webm")
            reply = self.kiosk_client.post(f"/v1/kiosk/assistant/sessions/{session['session']}/turns/",
                                           {"audio": audio, "history": json.dumps([{"role": "assistant", "content": "Hello!"}])},
                                           format="multipart").data
        self.assertEqual(reply["heard"], "Where is the pool?")
        self.assertEqual(reply["reply"], "The pool is on level 3 of Tower A.")
        self.assertEqual(reply["actions"], [{"type": "show_map", "map_id": self.map.pk}])
        system = fake.sent("chat/completions")[0]["json"]["messages"][0]["content"]
        self.assertIn("Pool: level 3, Tower A", system)
        self.assertIn("Never reveal or confirm anything about residents", system)
        self.assertIn(f"{self.map.pk}: Site map", system)
        self.assertEqual(fake.calls[0]["key"], "Bearer sk-platform")
        self.assertEqual(m.AssistantSession.objects.get().turns, 1)  # Counted; nothing said is kept.

    def test_actions_from_the_model_are_checked(self):
        tool = [
            {"id": "a", "type": "function", "function": {"name": "start_walk_in", "arguments": json.dumps(
                {"unit": "05-12", "visitor_name": "Tan", "purpose": "hack", "company": "X" * 300})}},
            {"id": "b", "type": "function", "function": {"name": "open_gate", "arguments": "{}"}},
            {"id": "c", "type": "function", "function": {"name": "show_map", "arguments": "not json"}},
        ]
        with self.openai(FakeOpenAI(tool_calls=tool)):
            session = self.start()
            reply = self.kiosk_client.post(f"/v1/kiosk/assistant/sessions/{session['session']}/turns/", {"text": "I visit 05-12"}).data
        self.assertEqual(reply["actions"], [{"type": "start_walk_in", "unit": "05-12", "visitor_name": "Tan", "company": "X" * 100, "purpose": ""}])

    def test_realtime_mode_gets_a_client_secret_with_the_sites_own_key(self):
        m.SystemSettings.objects.update(assistant_mode="realtime")
        m.AssistantSettings.objects.update(openai_api_key="sk-site")
        fake = FakeOpenAI()
        with self.openai(fake):
            session = self.start()
        self.assertEqual(session["client_secret"], "ek_test")
        sent = fake.sent("realtime/client_secrets")[0]
        self.assertEqual(sent["key"], "Bearer sk-site")
        self.assertEqual(sent["json"]["expires_after"]["seconds"], 60)
        self.assertIn("show_map", [t["name"] for t in sent["json"]["session"]["tools"]])
        self.assertNotIn("sk-", json.dumps(session))

    def test_daily_limit_and_other_sites(self):
        m.SystemSettings.objects.update(assistant_daily_sessions=1)
        with self.openai(FakeOpenAI()):
            self.start()
            self.assertEqual(self.kiosk_client.post("/v1/kiosk/assistant/sessions/").status_code, 503)
        other = m.Kiosk.objects.create(condominium=make_condo("other"), name="Other")
        client = self.kiosk_api(other)
        self.assertEqual(client.get(f"/v1/kiosk/assistant/maps/{self.map.pk}/").status_code, 404)
        session = m.AssistantSession.objects.get()
        self.assertEqual(client.post(f"/v1/kiosk/assistant/sessions/{session.pk}/turns/", {"text": "hi"}).status_code, 404)

    def test_only_site_admins_configure_it_and_the_key_is_write_only(self):
        staff = make_staff("office", self.condo, Role.STAFF)
        url = f"/v1/assistant-settings/?condominium={self.condo.pk}"
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(f"/v1/assistant-modules/?condominium={self.condo.pk}").data["count"], 0)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(url, {"openai_api_key": "sk-site", "name": "Ava"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("openai_api_key", response.data)
        self.assertTrue(response.data["has_openai_api_key"])
        stranger = make_user("stranger")
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get(url).status_code, 403)
