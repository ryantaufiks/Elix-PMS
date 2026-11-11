import base64
import json
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from core import assistant
from core import models as m
from core.scoping import ADMIN

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit, make_user, set_plan

Status = m.Subscription.Status


class EffectiveModulesTests(APITestCase):
    def setUp(self):
        self.condo = make_condo("alpha", plan="standard")

    def test_plan_addons_and_switched_off(self):
        self.assertEqual(self.condo.modules, ["core", "resident_app", "intercom", "facilities", "advanced_reports"])
        set_plan(self.condo, "basic", addons=["ai_concierge", "lpr"])
        self.assertEqual(self.condo.modules, ["core", "lpr", "ai_concierge"])
        # Switching off the resident app takes what needs it along.
        set_plan(self.condo, "standard", addons=[], disabled_modules=["resident_app"])
        self.assertEqual(self.condo.modules, ["core", "advanced_reports"])

    def test_suspended_keeps_physical_access_and_export(self):
        set_plan(self.condo, "premium", status=Status.SUSPENDED)
        self.assertEqual(self.condo.modules, ["core", "lpr", "advanced_reports"])
        set_plan(self.condo, "premium", status=Status.CANCELLED)
        self.assertEqual(self.condo.modules, ["core", "lpr"])

    def test_editing_a_plan_updates_its_sites(self):
        plan = m.Plan.objects.get(code="standard")
        plan.modules = [*plan.modules, "ai_concierge"]
        plan.save()
        self.condo.refresh_from_db()
        self.assertIn("ai_concierge", self.condo.modules)

    def test_plan_validation(self):
        root = make_user("root", is_superuser=True, is_staff=True)
        self.client.force_authenticate(root)
        bad = self.client.post("/v1/plans/", {"code": "x", "name": "X", "modules": ["intercom"]}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("Video intercom needs Resident app", str(bad.data))
        self.assertEqual(self.client.post("/v1/plans/", {"code": "x", "name": "X", "modules": ["nope"]}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/v1/plans/", {"code": "x", "name": "X", "limits": {"kiosks": -1}}, format="json").status_code, 400)
        ok = self.client.post("/v1/plans/", {"code": "lite", "name": "Lite", "modules": ["lpr"], "limits": {"kiosks": 1}}, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)
        # A plan in use cannot be deleted.
        self.assertEqual(self.client.delete(f"/v1/plans/{m.Plan.objects.get(code='standard').pk}/").status_code, 400)


class ModuleGateTests(APITestCase):
    """A Basic site: management and kiosk only."""

    def setUp(self):
        self.condo = make_condo("alpha", plan="basic", lpr_enabled=True, kiosk_face_checkout=True)
        self.unit = make_unit(self.condo)
        self.admin = make_staff("admin", self.condo, ADMIN)
        self.root = make_user("root", is_superuser=True, is_staff=True)

    def get(self, user, url):
        self.client.force_authenticate(user)
        return self.client.get(url)

    def test_locked_lists_say_why(self):
        for url in ("/v1/facilities/", "/v1/bookings/", "/v1/feedback/", "/v1/intercom-calls/", "/v1/assistant-modules/"):
            for user in (self.admin, self.root):
                response = self.get(user, f"{url}?condominium={self.condo.pk}")
                self.assertEqual(response.status_code, 403, url)
                self.assertEqual(response.data["code"], "module_locked")
        self.assertEqual(self.get(self.admin, f"/v1/payment-settings/?condominium={self.condo.pk}").data["code"], "module_locked")
        self.assertEqual(self.get(self.admin, f"/v1/assistant-settings/?condominium={self.condo.pk}").data["code"], "module_locked")
        # Core keeps working.
        self.assertEqual(self.get(self.admin, f"/v1/invitations/?condominium={self.condo.pk}").status_code, 200)

    def test_locked_records_cannot_be_added(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/v1/facilities/", {"condominium": self.condo.pk, "name": "Pool"})
        self.assertEqual((response.status_code, response.data["module"]), (403, "facilities"))

    def test_reports_view_free_export_and_print_advanced(self):
        self.client.force_authenticate(self.admin)
        url = f"/v1/reports/visits/?condominium={self.condo.pk}"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url + "&export=csv").data["code"], "module_locked")
        self.assertEqual(self.client.get(url + "&page_size=print").data["code"], "module_locked")
        set_plan(self.condo, "standard")
        self.assertEqual(self.client.get(url + "&export=csv").status_code, 200)

    def test_kiosk_offers_only_what_the_plan_has(self):
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby", gate_type="pedestrian")
        kiosk = m.Kiosk(condominium=self.condo, gate=gate, name="Lobby kiosk")
        token = kiosk.issue_token()
        kiosk.save()
        me = self.client.get("/v1/kiosk/me/", HTTP_AUTHORIZATION=f"Kiosk {token}").data
        self.assertEqual(me["modules"], ["core"])
        self.assertFalse(me["call_resident"])
        self.assertFalse(me["face_checkout"])
        m.AssistantSettings.objects.create(condominium=self.condo, enabled=True, openai_api_key="sk-test")
        self.assertFalse(assistant.available(self.condo))
        set_plan(self.condo, "premium")
        self.assertTrue(assistant.available(self.condo))
        me = self.client.get("/v1/kiosk/me/", HTTP_AUTHORIZATION=f"Kiosk {token}").data
        self.assertTrue(me["call_resident"])
        self.assertTrue(me["face_checkout"])

    def test_face_check_only_with_the_module(self):
        invitation = make_invitation(self.unit, make_resident("alice", self.unit), require_face=True)
        self.assertFalse(invitation.needs_face)
        set_plan(self.condo, "premium")
        invitation.condominium.refresh_from_db()
        self.assertTrue(m.Invitation.objects.get(pk=invitation.pk).needs_face)

    def test_lpr_records_only_without_the_module(self):
        gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        camera = m.LprCamera(gate=gate, name="Entry", device_id="DH-1", webhook_username="cam1")
        camera.set_webhook_password("campw")
        camera.save()
        auth = base64.b64encode(b"cam1:campw").decode()
        response = self.client.post("/v1/lpr-webhook/", json.dumps({"PlateNumber": "SBA1234A"}),
                                    content_type="application/json", HTTP_AUTHORIZATION=f"Basic {auth}")
        self.assertEqual(response.json()["status"], "recorded")
        self.assertFalse(m.AccessLog.objects.exists())


class LimitTests(APITestCase):
    def setUp(self):
        self.condo = make_condo("alpha", plan="standard")
        set_plan(self.condo, "standard", limit_overrides={"kiosks": 1, "units": 3, "staff_accounts": 2, "gates": 1})
        self.admin = make_staff("admin", self.condo, ADMIN)
        self.client.force_authenticate(self.admin)

    def test_kiosks_and_gates(self):
        self.assertEqual(self.client.post("/v1/gates/", {"condominium": self.condo.pk, "name": "A"}).status_code, 201)
        second = self.client.post("/v1/gates/", {"condominium": self.condo.pk, "name": "B"})
        self.assertEqual((second.status_code, second.data["code"]), (403, "limit_reached"))
        self.assertIn("allows 1 gates", second.data["detail"])
        self.assertEqual(self.client.post("/v1/kiosks/", {"condominium": self.condo.pk, "name": "K1"}).status_code, 201)
        self.assertEqual(self.client.post("/v1/kiosks/", {"condominium": self.condo.pk, "name": "K2"}).status_code, 403)

    def test_units_in_bulk(self):
        body = {"condominium": self.condo.pk, "floor_from": 1, "floor_to": 2, "units": "01-02"}
        self.assertEqual(self.client.post("/v1/units/bulk/", body, format="json").data["code"], "limit_reached")
        self.assertFalse(m.Unit.objects.exists())
        body["floor_to"] = 1
        self.assertEqual(self.client.post("/v1/units/bulk/", body, format="json").status_code, 201)

    def test_staff_accounts(self):
        body = {"username": "officer1", "first_name": "A", "password": "pw-Long-123!",
                "staff": {"condominium": self.condo.pk, "role": "security"}}
        r = self.client.post("/v1/users/", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        body["username"] = "officer2"
        self.assertEqual(self.client.post("/v1/users/", body, format="json").data["code"], "limit_reached")


class SubscriptionApiTests(APITestCase):
    def setUp(self):
        self.root = make_user("root", is_superuser=True, is_staff=True)
        self.condo = make_condo("alpha", plan="standard")
        self.admin = make_staff("admin", self.condo, ADMIN)
        self.url = f"/v1/subscriptions/{self.condo.pk}/"

    def test_site_admin_reads_without_notes(self):
        m.Subscription.objects.filter(condominium=self.condo).update(notes="Invoice INV-1")
        self.client.force_authenticate(self.admin)
        data = self.client.get(self.url).data
        self.assertEqual(data["plan_name"], "Standard")
        self.assertNotIn("notes", data)
        self.assertNotIn("events", data)
        self.assertEqual(data["usage"]["kiosks"], 0)
        self.assertEqual(self.client.patch(self.url, {"status": "active"}, format="json").status_code, 403)
        other = make_condo("beta")
        self.assertEqual(self.client.get(f"/v1/subscriptions/{other.pk}/").status_code, 403)

    def test_platform_admin_changes_and_history(self):
        self.client.force_authenticate(self.root)
        premium = m.Plan.objects.get(code="premium")
        response = self.client.patch(self.url, {"plan": premium.pk, "status": "active", "addons": ["face_terminal"],
                                                "period_ends_on": "2027-11-30"}, format="json")
        self.assertEqual(response.status_code, 400)  # Face terminals need On-site devices.
        response = self.client.patch(self.url, {"plan": premium.pk, "status": "grace", "period_ends_on": "2027-11-30"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("ai_concierge", response.data["modules"])
        summary = response.data["events"][0]["summary"]
        self.assertIn("Plan Standard -> Premium", summary)
        self.assertIn("status Active -> Grace period", summary)
        self.assertEqual(response.data["events"][0]["actor_name"], "root")

    def test_new_site_starts_a_trial_on_the_chosen_plan(self):
        self.client.force_authenticate(self.root)
        response = self.client.post("/v1/condominiums/", {"name": "Gamma", "code": "gamma", "plan": "premium"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        sub = m.Subscription.objects.get(condominium_id=response.data["id"])
        self.assertEqual((sub.plan.code, sub.status), ("premium", Status.TRIAL))
        self.assertEqual(sub.trial_ends_on, timezone.localdate() + timedelta(days=30))
        self.assertIn("Premium", sub.events.get().summary)
        self.assertEqual(response.data["plan_name"], "Premium")
        # Without a plan: Standard.
        response = self.client.post("/v1/condominiums/", {"name": "Delta", "code": "delta"}, format="json")
        self.assertEqual(m.Subscription.objects.get(condominium_id=response.data["id"]).plan.code, "standard")

    def test_catalogue_names_the_plan_to_upgrade_to(self):
        self.client.force_authenticate(self.admin)
        modules = {x["key"]: x for x in self.client.get("/v1/modules/").data["modules"]}
        self.assertEqual(modules["intercom"]["upsell_plan"], "Standard")
        self.assertEqual(modules["ai_concierge"]["upsell_plan"], "Premium")
        self.assertEqual(modules["face_terminal"]["upsell_plan"], "")
        self.assertFalse(modules["face_terminal"]["available"])
        # Internal plans are not offered to site admins.
        self.assertNotIn("full", [p["code"] for p in self.client.get("/v1/plans/").data])
        self.assertEqual(self.client.post("/v1/plans/", {"code": "x", "name": "X"}, format="json").status_code, 403)
