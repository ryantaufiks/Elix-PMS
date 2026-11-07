import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from core import models as m

from .factories import make_condo, make_invitation, make_resident, make_unit


def jpeg():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "JPEG")
    return SimpleUploadedFile("face.jpg", buffer.getvalue(), content_type="image/jpeg")


@mock.patch("core.tasks.open_gate.delay")
class KioskCheckInTests(APITestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.condo = make_condo(face_verification_enabled=True)
        self.unit = make_unit(self.condo)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby")
        self.other_gate = m.AccessGate.objects.create(condominium=self.condo, name="Carpark")
        self.kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby kiosk", gate=self.gate)
        token = self.kiosk.issue_token()
        self.kiosk.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")
        self.host = make_resident("alice", self.unit)
        self.host.first_name = "Alice"
        self.host.save()

    def checkin(self, code, **extra):
        return self.client.post("/v1/kiosk/checkin/", {"code": code, **extra}, format="multipart")

    def test_share_link_grants_once_and_opens_gate(self, open_gate):
        inv = make_invitation(self.unit, self.host, max_entries=1)
        lookup = self.client.post("/v1/kiosk/checkin/lookup/", {"code": inv.share_url}).data
        self.assertEqual((lookup["result"], lookup["invitation"]["visitor_name"], lookup["invitation"]["host_first_name"]),
                         ("granted", "Tan Ah Kow", "Alice"))
        self.assertFalse(m.AccessLog.objects.exists())  # lookup never logs or opens

        with self.captureOnCommitCallbacks(execute=True):
            data = self.checkin(inv.share_url).data
        self.assertEqual(data["result"], "granted")
        self.assertEqual(data["invitation"]["status"], "completed")
        log = m.AccessLog.objects.get()
        self.assertEqual((log.method, log.gate, log.invitation, log.unit), ("qr", self.gate, inv, self.unit))
        open_gate.assert_called_once_with(log.pk)

        again = self.checkin(inv.token).data
        self.assertEqual((again["result"], again["reason"]), ("denied", "Invitation is completed."))

    def test_unknown_expired_wrong_gate_and_other_condo(self, open_gate):
        self.assertEqual(self.checkin("nonsense").data["reason"], "Unknown QR code.")
        expired = make_invitation(self.unit, self.host, valid_from=timezone.now() - timedelta(days=2),
                                  valid_until=timezone.now() - timedelta(days=1))
        self.assertEqual(self.checkin(expired.token).data["reason"], "Invitation has expired.")
        carpark_only = make_invitation(self.unit, self.host)
        carpark_only.gates.set([self.other_gate])
        self.assertEqual(self.checkin(carpark_only.token).data["reason"], "This invitation is not valid at this gate.")
        other_unit = make_unit(make_condo("beta"))
        foreign = make_invitation(other_unit, make_resident("bob", other_unit))
        self.assertEqual(self.checkin(foreign.token).data["reason"], "Unknown QR code.")
        self.assertEqual(m.AccessLog.objects.filter(result="denied").count(), 4)
        open_gate.assert_not_called()

    def test_face_required_then_photo_stored(self, open_gate):
        inv = make_invitation(self.unit, self.host, require_face=True)
        first = self.checkin(inv.token).data
        self.assertEqual(first["result"], "face_required")
        self.assertFalse(m.AccessLog.objects.exists())
        data = self.checkin(inv.token, face_photo=jpeg()).data
        self.assertEqual(data["result"], "granted")
        log = m.AccessLog.objects.get()
        self.assertTrue(log.snapshot)
        self.assertIn("Face photo captured", log.reason)

    def test_plate_must_match_when_both_given(self, open_gate):
        inv = make_invitation(self.unit, self.host, vehicle_plate="SBA1234A", max_entries=0)
        self.assertEqual(self.checkin(inv.token, plate="sgx 999 b").data["result"], "denied")
        self.assertEqual(self.checkin(inv.token, plate="sba-1234 a").data["result"], "granted")
        self.assertEqual(self.checkin(inv.token).data["result"], "granted")

    def test_kiosk_without_gate(self, open_gate):
        self.kiosk.gate = None
        self.kiosk.save()
        inv = make_invitation(self.unit, self.host)
        self.assertEqual(self.checkin(inv.token).status_code, 409)


class VisitorPassTests(APITestCase):
    def test_public_pass_and_qr(self):
        condo = make_condo()
        unit = make_unit(condo)
        host = make_resident("alice", unit)
        host.first_name, host.last_name = "Alice", "Secret-Surname"
        host.save()
        inv = make_invitation(unit, host)
        client = APIClient()
        data = client.get(f"/v1/public/invitations/{inv.token}/").data
        self.assertEqual((data["visitor_name"], data["host_first_name"], data["usable"]), ("Tan Ah Kow", "Alice", True))
        self.assertNotIn("Secret-Surname", str(data))
        self.assertNotIn("token", data)
        qr = client.get(f"/v1/public/invitations/{inv.token}/qr/")
        self.assertEqual((qr.status_code, qr["Content-Type"]), (200, "image/png"))
        self.assertEqual(client.get("/v1/public/invitations/nope/").status_code, 404)
