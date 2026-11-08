from unittest import mock

from rest_framework.test import APITestCase

from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit

Role = m.StaffAssignment.Role


@mock.patch("core.tasks.open_gate.delay")
class StaffRoleTests(APITestCase):
    """Staff (management office) sit between the site admin and officers."""

    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        self.admin = make_staff("admin", self.condo, Role.ADMIN)
        self.staff = make_staff("office", self.condo, Role.STAFF)
        self.officer = make_staff("guard", self.condo, Role.SECURITY)
        self.resident = make_resident("res", self.unit)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_staff_open_gates_and_handle_visitors(self, _):
        self.assertEqual(self.as_(self.staff).post(f"/v1/gates/{self.gate.id}/open/", {"reason": "Lorry"}).status_code, 202)
        response = self.as_(self.staff).post("/v1/visits/", {"unit": self.unit.pk, "visitor_name": "Tan", "purpose": "guest", "consent": True})
        self.assertEqual(response.status_code, 201, response.data)

    def test_staff_manage_residents_and_vehicles_officers_only_read(self, _):
        body = {"username": "new", "first_name": "New", "password": "a-Long-pass-123",
                "residency": {"unit": self.unit.pk, "resident_type": "tenant"}}
        self.assertEqual(self.as_(self.officer).post("/v1/users/", body, format="json").status_code, 403)
        self.assertEqual(self.as_(self.staff).post("/v1/users/", body, format="json").status_code, 201)
        self.assertEqual(self.as_(self.staff).patch(f"/v1/users/{self.resident.pk}/", {"phone": "+6591234567"}).status_code, 200)

        vehicle = {"condominium": self.condo.pk, "unit": self.unit.pk, "plate_number": "SGX1234A"}
        self.assertEqual(self.as_(self.officer).post("/v1/vehicles/", vehicle).status_code, 403)
        self.assertEqual(self.as_(self.staff).post("/v1/vehicles/", vehicle).status_code, 201)
        self.assertEqual(self.as_(self.officer).get(f"/v1/vehicles/?condominium={self.condo.pk}").data["count"], 1)

    def test_staff_cannot_manage_staff_accounts_or_setup(self, _):
        body = {"username": "guard2", "password": "a-Long-pass-123", "staff": {"condominium": self.condo.pk, "role": "security"}}
        self.assertEqual(self.as_(self.staff).post("/v1/users/", body, format="json").status_code, 403)
        self.assertEqual(self.as_(self.admin).post("/v1/users/", body, format="json").status_code, 201)
        # Staff accounts are neither listed for nor editable by staff.
        self.assertNotIn(self.officer.pk, [u["id"] for u in self.as_(self.staff).get("/v1/users/").data["results"]])
        self.assertEqual(self.as_(self.staff).post(f"/v1/users/{self.officer.pk}/set-password/", {"password": "x-Long-pass-999"}).status_code, 404)
        self.assertEqual(self.as_(self.staff).get(f"/v1/staff-assignments/?condominium={self.condo.pk}").data["count"], 0)
        self.assertEqual(self.as_(self.staff).patch(f"/v1/condominiums/{self.condo.pk}/", {"name": "X"}).status_code, 403)
        self.assertEqual(self.as_(self.staff).post("/v1/gates/", {"condominium": self.condo.pk, "name": "Side"}).status_code, 403)

    def test_staff_reply_to_feedback_officers_cannot(self, _):
        feedback = m.Feedback.objects.create(condominium=self.condo, unit=self.unit, user=self.resident, rating=3, category="security")
        url = f"/v1/feedback/{feedback.pk}/reply/"
        self.assertEqual(self.as_(self.officer).post(url, {"reply": "Hi"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.staff).post(url, {"reply": "Thanks"}, format="json").status_code, 200)

    def test_role_labels(self, _):
        self.assertEqual([label for _, label in Role.choices], ["Site admin", "Staff", "Officer"])
