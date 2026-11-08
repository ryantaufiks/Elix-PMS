import base64
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit, make_user

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
Role = m.StaffAssignment.Role


@override_settings(CACHES=LOCMEM)
class SignInTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("alice")

    def login(self, password="pw-123456!", ip="203.0.113.1", username="alice"):
        return self.client.post("/v1/auth/token/", {"username": username, "password": password}, REMOTE_ADDR=ip)

    def test_guessing_one_account_is_capped_across_addresses(self):
        for i in range(10):
            self.assertEqual(self.login("wrong", ip=f"203.0.113.{i}").status_code, 401)
        self.assertEqual(self.login(ip="198.51.100.7").status_code, 429)

    def test_guessing_from_one_address_is_capped(self):
        for i in range(20):
            self.login("wrong", username=f"user{i}")
        self.assertEqual(self.login().status_code, 429)

    def test_sign_out_and_password_change_revoke_refresh_tokens(self):
        refresh = self.login().data["refresh"]
        self.assertEqual(self.client.post("/v1/auth/logout/", {"refresh": refresh}).status_code, 200)
        self.assertEqual(self.client.post("/v1/auth/token/refresh/", {"refresh": refresh}).status_code, 401)

        refresh = self.login().data["refresh"]
        self.user.set_password("another-Long-pass-456")
        self.user.save()
        self.assertEqual(self.client.post("/v1/auth/token/refresh/", {"refresh": refresh}).status_code, 401)

    def test_disabling_an_account_revokes_its_sessions(self):
        refresh = self.login().data["refresh"]
        self.user.is_active = False
        self.user.save()
        self.user.is_active = True
        self.user.save()
        self.assertEqual(self.client.post("/v1/auth/token/refresh/", {"refresh": refresh}).status_code, 401)

    def test_used_refresh_token_cannot_be_reused(self):
        refresh = self.login().data["refresh"]
        self.assertEqual(self.client.post("/v1/auth/token/refresh/", {"refresh": refresh}).status_code, 200)
        self.assertEqual(self.client.post("/v1/auth/token/refresh/", {"refresh": refresh}).status_code, 401)

    def test_admin_login_is_rate_limited(self):
        for _ in range(10):
            self.client.post("/v1/admin/login/", {"username": "alice", "password": "wrong"}, REMOTE_ADDR="203.0.113.9")
        self.assertEqual(self.client.post("/v1/admin/login/", {"username": "alice", "password": "x"}, REMOTE_ADDR="203.0.113.9").status_code, 429)


class ApiDocsTests(APITestCase):
    def test_schema_and_docs_are_for_platform_admins_only(self):
        self.assertIn(self.client.get("/v1/schema/").status_code, (401, 403))
        self.assertIn(self.client.get("/v1/docs/").status_code, (401, 403))
        self.client.force_authenticate(make_staff("admin", make_condo(), Role.ADMIN))
        self.assertEqual(self.client.get("/v1/schema/").status_code, 403)
        self.client.force_authenticate(make_user("root", is_staff=True, is_superuser=True))
        self.assertEqual(self.client.get("/v1/schema/").status_code, 200)


class MembershipTests(APITestCase):
    """People of another site cannot be pulled in by ID (that would expose their contact details)."""

    def setUp(self):
        self.a, self.b = make_condo("a"), make_condo("b")
        self.unit_a = make_unit(self.a)
        self.admin_a = make_staff("admin_a", self.a, Role.ADMIN)
        self.outsider = make_resident("outsider", make_unit(self.b))
        self.local = make_resident("local", self.unit_a)
        self.client.force_authenticate(self.admin_a)

    def test_only_people_of_the_site_can_be_linked(self):
        r = self.client.post("/v1/staff-assignments/", {"user": self.outsider.pk, "condominium": self.a.pk, "role": "security"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("user_detail", r.data)
        r = self.client.post("/v1/residencies/", {"user": self.outsider.pk, "unit": make_unit(self.a, number="02").pk}, format="json")
        self.assertEqual(r.status_code, 400)
        # Someone already at the site can be given a staff role or a second unit.
        r = self.client.post("/v1/staff-assignments/", {"user": self.local.pk, "condominium": self.a.pk, "role": "security"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_the_person_of_a_link_cannot_be_swapped(self):
        residency = self.local.residencies.get()
        r = self.client.patch(f"/v1/residencies/{residency.pk}/", {"user": self.outsider.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.patch(f"/v1/residencies/{residency.pk}/", {"resident_type": "tenant"}, format="json").status_code, 200)

    def test_other_sites_get_permission_denied(self):
        self.client.force_authenticate(make_staff("admin_b", self.b, Role.ADMIN))
        r = self.client.post("/v1/staff-assignments/", {"user": self.local.pk, "condominium": self.a.pk, "role": "admin"}, format="json")
        self.assertEqual(r.status_code, 403)


@override_settings(CACHES=LOCMEM)
@mock.patch("core.tasks.open_gate.delay")
class LprWebhookLimitTests(APITestCase):
    def setUp(self):
        cache.clear()
        gate = m.AccessGate.objects.create(condominium=make_condo(lpr_enabled=True), name="Main")
        camera = m.LprCamera(gate=gate, name="Entry", device_id="E1", webhook_username="cam1")
        camera.set_webhook_password("campw")
        camera.save()

    def post(self, password):
        auth = base64.b64encode(f"cam1:{password}".encode()).decode()
        return self.client.post("/v1/lpr-webhook/", "{}", content_type="application/json", HTTP_AUTHORIZATION=f"Basic {auth}",
                                REMOTE_ADDR="203.0.113.5")

    def test_password_guessing_is_locked_out(self, _):
        for _ in range(20):
            self.assertEqual(self.post("wrong").status_code, 401)
        self.assertEqual(self.post("campw").status_code, 429)
