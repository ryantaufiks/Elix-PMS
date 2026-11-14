import hashlib
import hmac
import shutil
import tempfile
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit
from .test_amenities import hitpay_response


@mock.patch("core.permits.broadcast")
class PermitTests(APITestCase):
    def setUp(self):
        self.condo = make_condo(renovation_permits_enabled=True, contractor_days=[0, 1, 2, 3, 4], contractor_from=time(9),
                                overstay_contractor_until=time(17))
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.admin = make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN)
        self.client.force_authenticate(self.alice)

    def apply(self, **extra):
        start = timezone.localdate() + timedelta(days=3)
        data = {"unit": self.unit.pk, "category": "carpentry", "description": "Kitchen cabinets", "contractor_company": "Ace Reno",
                "contractor_contact": "Mr Tan", "contractor_phone": "+65 9123 4567", "workers": 3,
                "start_date": str(start), "end_date": str(start + timedelta(days=10)), "plates": ["gba 1 a"], **extra}
        return self.client.post("/v1/renovation-permits/", data, format="json")

    def as_admin(self, action, pk, **body):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/v1/renovation-permits/{pk}/{action}/", body, format="json")
        self.client.force_authenticate(self.alice)
        return response

    def test_apply_approve_and_complete(self, _):
        response = self.apply()
        self.assertEqual(response.status_code, 201, response.data)
        permit = response.data["permit"]
        self.assertEqual((permit["status"], permit["payment_status"], permit["plates"], response.data["payment_url"]),
                         ("submitted", "none", ["GBA1A"], ""))
        # Residents cannot decide.
        self.assertEqual(self.client.post(f"/v1/renovation-permits/{permit['id']}/approve/").status_code, 403)

        approved = self.as_admin("approve", permit["id"], note="No hacking after 5 pm").data
        self.assertEqual((approved["status"], approved["decision_note"]), ("approved", "No hacking after 5 pm"))
        self.assertTrue(approved["pass_url"])
        passes = m.Invitation.objects.filter(permit_id=permit["id"])
        self.assertEqual(sorted(passes.values_list("vehicle_plate", flat=True)), ["", "GBA1A"])
        shared = passes.get(vehicle_plate="")
        self.assertEqual((shared.company, shared.purpose, shared.weekdays, shared.daily_from, shared.daily_until, shared.max_entries),
                         ("Ace Reno", "contractor", [0, 1, 2, 3, 4], time(9), time(17), 0))
        kinds = [n["kind"] for n in self.client.get("/v1/notifications/").data["results"]]
        self.assertIn("permit_approved", kinds)
        # Residents cannot cancel an approved permit; the office completes it and the passes end.
        self.assertEqual(self.client.post(f"/v1/renovation-permits/{permit['id']}/cancel/").status_code, 409)
        self.assertEqual(self.as_admin("complete", permit["id"]).data["status"], "completed")
        self.assertFalse(passes.filter(status="active").exists())

    def test_reject_and_cancel(self, _):
        first = self.apply().data["permit"]
        self.assertEqual(self.as_admin("reject", first["id"], note="Insurance missing").data["status"], "rejected")
        self.assertFalse(m.Invitation.objects.exists())
        second = self.apply().data["permit"]
        self.assertEqual(self.client.post(f"/v1/renovation-permits/{second['id']}/cancel/").data["status"], "cancelled")
        # Another unit's resident sees none of it.
        self.client.force_authenticate(make_resident("bob", make_unit(self.condo, "07", "01")))
        self.assertEqual(self.client.get("/v1/renovation-permits/").data["count"], 0)

    def test_rules(self, _):
        self.assertIn("start date has passed", self.apply(start_date=str(timezone.localdate() - timedelta(days=1))).data["detail"])
        self.assertEqual(self.apply(plates=["A1", "B2", "C3", "D4"]).status_code, 400)
        self.condo.renovation_permits_enabled = False
        self.condo.save()
        self.assertIn("not taken in the app", self.apply().data["detail"])

    @mock.patch("core.payments.requests.post", return_value=hitpay_response(id="pr_r", url="https://hitpay.test/pay/pr_r"))
    def test_deposit_paid_online_then_refunded(self, post, _):
        self.condo.renovation_deposit = Decimal("500.00")
        self.condo.save()
        m.PaymentSettings.objects.create(condominium=self.condo, enabled=True, hitpay_api_key="key", hitpay_salt="salt")
        response = self.apply()
        permit = response.data["permit"]
        self.assertEqual((permit["status"], permit["deposit"], response.data["payment_url"]),
                         ("pending_payment", "500.00", "https://hitpay.test/pay/pr_r"))
        self.assertEqual(post.call_args.kwargs["data"]["reference_number"], f"permit-{permit['id']}")
        fields = {"payment_request_id": "pr_r", "status": "completed", "reference_number": f"permit-{permit['id']}"}
        message = "".join(f"{k}{fields[k]}" for k in sorted(fields))
        signed = {**fields, "hmac": hmac.new(b"salt", message.encode(), hashlib.sha256).hexdigest()}
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="completed")):
            self.assertEqual(self.client.post("/v1/payments/hitpay/webhook/", signed).status_code, 200)
            page = self.client.get(f"/v1/payments/hitpay/return/?renovation={permit['id']}")
        self.assertContains(page, "Deposit paid")
        self.assertEqual(m.RenovationPermit.objects.get().status, "submitted")
        self.assertEqual(self.as_admin("refunded", permit["id"]).status_code, 409)  # Not while it is open.
        self.as_admin("reject", permit["id"])
        self.assertEqual(self.as_admin("refunded", permit["id"]).data["payment_status"], "refunded")

    def test_office_attaches_a_document(self, _):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media))
        permit = self.apply().data["permit"]
        self.client.force_authenticate(self.admin)
        url = f"/v1/renovation-permits/{permit['id']}/document/"
        bad = self.client.post(url, {"file": SimpleUploadedFile("x.pdf", b"not a pdf")}, format="multipart")
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(url, {"file": SimpleUploadedFile("insurance.pdf", b"%PDF-1.4 test")}, format="multipart")
        self.assertEqual((ok.status_code, ok.data["document_name"]), (200, "insurance.pdf"))
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.get(url).status_code, 200)
