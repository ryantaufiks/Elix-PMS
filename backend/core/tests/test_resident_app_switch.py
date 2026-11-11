from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from core import assistant
from core import models as m
from core.scoping import ADMIN

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit, make_user, set_plan
from .test_intercom import LIVEKIT


@override_settings(**LIVEKIT)
@mock.patch("core.tasks.push_incoming_call.delay")
class ResidentAppSwitchTests(APITestCase):
    """A site without the resident app runs on the kiosk and the dashboard only."""

    def setUp(self):
        cache.clear()
        self.condo = make_condo("alpha", kiosk_visitor_form=False, kiosk_photo_required=False)
        self.unit = make_unit(self.condo)
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby", gate_type="pedestrian")
        self.kiosk = m.Kiosk(condominium=self.condo, gate=gate, name="Lobby kiosk")
        self.token = self.kiosk.issue_token()
        self.kiosk.save()
        self.alice = make_resident("alice", self.unit)
        self.invitation = make_invitation(self.unit, self.alice)

    def switch_off(self):
        set_plan(self.condo, "full", disabled_modules=["resident_app"])

    def kiosk_get(self, url):
        return self.client.get(url, HTTP_AUTHORIZATION=f"Kiosk {self.token}")

    def test_residents_lose_access_but_see_why(self, *mocks):
        self.client.force_authenticate(self.alice)
        self.assertEqual(len(self.client.get("/v1/invitations/").data["results"]), 1)
        self.switch_off()
        self.assertEqual(self.client.get("/v1/invitations/").data["results"], [])
        response = self.client.post("/v1/invitations/", {
            "unit": self.unit.id, "visitor_name": "Tan", "valid_from": self.invitation.valid_from.isoformat(),
            "valid_until": self.invitation.valid_until.isoformat()})
        self.assertIn(response.status_code, (400, 403))
        # The app learns from /me that the site does not use it, and says so.
        residency = self.client.get("/v1/auth/me/").data["residencies"][0]
        self.assertFalse(residency["resident_app_enabled"])

    def test_kiosk_offers_no_calls(self, *mocks):
        self.assertTrue(self.kiosk_get("/v1/kiosk/me/").data["call_resident"])
        self.switch_off()
        self.assertFalse(self.kiosk_get("/v1/kiosk/me/").data["call_resident"])
        self.assertEqual(self.kiosk_get("/v1/kiosk/directory/").data, [])
        self.assertEqual(len(self.kiosk_get("/v1/kiosk/directory/?walk_in=1").data), 1)
        response = self.client.post("/v1/kiosk/calls/", {"unit": self.unit.id, "visitor_name": "Grab", "consent": "true"},
                                    HTTP_AUTHORIZATION=f"Kiosk {self.token}")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertFalse(m.IntercomCall.objects.exists())
        mocks[0].assert_not_called()

    def test_assistant_cannot_call(self, *mocks):
        self.assertIn("call_resident", [t["name"] for t in assistant.tools(self.condo)])
        self.switch_off()
        self.condo.refresh_from_db()
        self.assertNotIn("call_resident", [t["name"] for t in assistant.tools(self.condo)])
        self.assertNotIn("call_resident", assistant.instructions(self.condo))

    def test_only_the_platform_admin_switches_it(self, *mocks):
        url = f"/v1/subscriptions/{self.condo.pk}/"
        self.client.force_authenticate(make_staff("admin", self.condo, ADMIN))
        self.assertEqual(self.client.patch(url, {"disabled_modules": ["resident_app"]}, format="json").status_code, 403)
        self.client.force_authenticate(make_user("root", is_superuser=True, is_staff=True))
        self.assertEqual(self.client.patch(url, {"disabled_modules": ["resident_app"]}, format="json").status_code, 200)
        self.condo.refresh_from_db()
        self.assertFalse(self.condo.resident_app_enabled)
        self.assertNotIn("intercom", self.condo.modules)  # needs the resident app
