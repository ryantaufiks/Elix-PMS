import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from core import models as m
from core import privacy

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit

LIVEKIT = {"LIVEKIT_URL": "wss://x.livekit.cloud", "LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s" * 32}


def jpeg(name="v.jpg"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class MediaMixin:
    def use_temp_media(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media))


@override_settings(**LIVEKIT)
@mock.patch("core.tasks.push_incoming_call.delay")
@mock.patch("core.tasks.expire_call.apply_async")
@mock.patch("core.tasks.finish_call.apply_async")
class KioskVisitorDetailsTests(MediaMixin, APITestCase):
    def setUp(self):
        self.use_temp_media()
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        make_resident("alice", self.unit)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby")
        self.kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby kiosk", gate=self.gate)
        token = self.kiosk.issue_token()
        self.kiosk.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")

    def call(self, **fields):
        return self.client.post("/v1/kiosk/calls/", {"unit": self.unit.pk, **fields}, format="multipart")

    def test_site_requires_details_photo_and_consent(self, *mocks):
        response = self.call()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {"visitor_name", "purpose", "snapshot", "consent"})
        self.assertEqual(self.client.get("/v1/kiosk/me/").data["visitor_form"], True)
        self.assertIn("deleted after 90 days", self.client.get("/v1/kiosk/me/").data["privacy_notice"])

    def test_full_details_create_visitor_and_show_on_call(self, *mocks):
        response = self.call(visitor_name="Budi Santoso", visitor_phone="9123 4567", visitor_id_partial="567a",
                             purpose="delivery", company="Ninja Van", consent="true", snapshot=jpeg())
        self.assertEqual(response.status_code, 201, response.data)
        call = response.data["call"]
        self.assertEqual((call["visitor_purpose"], call["visitor_company"], call["visitor_phone"]),
                         ("delivery", "Ninja Van", "+6591234567"))
        visitor = m.Visitor.objects.get()
        self.assertEqual((visitor.id_partial, str(visitor.phone)), ("567A", "+6591234567"))
        self.assertIsNotNone(visitor.face_consent_at)

    def test_returning_visitor_lookup_is_masked_and_ref_works(self, *mocks):
        self.call(visitor_name="Budi Santoso", visitor_phone="91234567", purpose="food", company="GrabFood",
                  consent="true", snapshot=jpeg())
        found = self.client.post("/v1/kiosk/visitors/lookup/", {"phone": "+65 9123 4567"}).data
        self.assertEqual((found["found"], found["masked_name"], found["company"], found["purpose"]),
                         (True, "B*** S***", "GrabFood", "food"))
        self.assertNotIn("Budi", str(found))
        by_ic = self.client.post("/v1/kiosk/visitors/lookup/", {"id_partial": "999Z"}).data
        self.assertFalse(by_ic["found"])

        response = self.call(visitor_ref=found["ref"], purpose="food", consent="true", snapshot=jpeg())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["call"]["visitor_name"], "Budi Santoso")
        self.assertEqual(m.Visitor.objects.count(), 1)

    def test_ref_from_another_kiosk_is_ignored(self, *mocks):
        visitor = m.Visitor.objects.create(condominium=self.condo, full_name="Eve", phone="+6591230000")
        other = m.Kiosk.objects.create(condominium=self.condo, name="Side")
        from core import visitor_identity
        forged = visitor_identity.make_ref(other, visitor)
        response = self.call(visitor_ref=forged, purpose="guest", consent="true", snapshot=jpeg())
        self.assertEqual(response.status_code, 400)
        self.assertIn("visitor_name", response.data)

    def test_blacklisted_visitor_cannot_call(self, *mocks):
        m.Visitor.objects.create(condominium=self.condo, full_name="Mallory", phone="+6598887777", is_blacklisted=True)
        lookup = self.client.post("/v1/kiosk/visitors/lookup/", {"phone": "98887777"}).data
        self.assertEqual((lookup["blocked"], lookup["ref"]), (True, ""))
        response = self.call(visitor_name="Mallory", visitor_phone="98887777", purpose="guest", consent="true",
                             snapshot=jpeg())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(m.IntercomCall.objects.exists())
        self.assertEqual(m.AccessLog.objects.get().reason, "Blocked visitor tried to call a unit")

    def test_site_can_switch_both_off(self, *mocks):
        self.condo.kiosk_visitor_form = False
        self.condo.kiosk_photo_required = False
        self.condo.save()
        response = self.call(snapshot=jpeg())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["call"]["has_snapshot"])  # no consent given, so no photo kept
        self.assertFalse(m.Visitor.objects.exists())

    def test_invalid_numbers_rejected(self, *mocks):
        response = self.call(visitor_name="X", visitor_phone="12", purpose="guest", consent="true", snapshot=jpeg())
        self.assertIn("visitor_phone", response.data)
        response = self.call(visitor_name="X", visitor_id_partial="S1234567A", purpose="guest", consent="true", snapshot=jpeg())
        self.assertIn("visitor_id_partial", response.data)


class PurgeTests(MediaMixin, APITestCase):
    def setUp(self):
        self.use_temp_media()
        self.condo = make_condo(visitor_data_retention_days=30)
        self.unit = make_unit(self.condo)
        self.host = make_resident("alice", self.unit)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby")
        old = timezone.now() - timedelta(days=40)
        self.visitor = m.Visitor.objects.create(condominium=self.condo, full_name="Old Visitor", last_visit_at=old)
        self.banned = m.Visitor.objects.create(condominium=self.condo, full_name="Banned", is_blacklisted=True, last_visit_at=old)
        self.call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, room_name="r", visitor=self.visitor,
                                                  visitor_name="Old Visitor", visitor_company="Grab", status="missed")
        self.call.visitor_snapshot.save("old.jpg", ContentFile(b"jpg"))
        m.IntercomCall.objects.filter(pk=self.call.pk).update(created_at=old)
        self.log = m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, method="lpr", result="denied",
                                              plate_number="SGX1A", occurred_at=old, raw_payload={"x": 1})
        self.inv = make_invitation(self.unit, self.host, valid_from=old - timedelta(hours=1), valid_until=old)
        self.fresh = m.Visitor.objects.create(condominium=self.condo, full_name="Recent", last_visit_at=timezone.now())

    def test_dry_run_changes_nothing(self):
        counts = privacy.purge_condominium(self.condo, dry_run=True)
        self.assertEqual((counts["visitors"], counts["call_photos"], counts["invitations"]), (1, 1, 1))
        self.call.refresh_from_db()
        self.assertTrue(self.call.visitor_snapshot.storage.exists(self.call.visitor_snapshot.name))
        self.assertEqual(m.Visitor.objects.count(), 3)

    def test_purge_after_retention(self):
        path = self.call.visitor_snapshot.name
        storage = self.call.visitor_snapshot.storage
        privacy.purge_condominium(self.condo)
        self.call.refresh_from_db()
        self.assertEqual((self.call.visitor_name, self.call.visitor_company, self.call.visitor_snapshot.name), ("", "", ""))
        self.assertFalse(storage.exists(path))
        self.log.refresh_from_db()
        self.assertEqual((self.log.plate_number, self.log.raw_payload), ("", {}))
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.visitor_name, privacy.REMOVED)
        self.assertEqual(set(m.Visitor.objects.values_list("full_name", flat=True)), {"Banned", "Recent"})

    def test_erasure_on_request(self):
        admin = make_staff("boss", self.condo, m.StaffAssignment.Role.ADMIN)
        guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        self.client.force_authenticate(guard)
        self.assertEqual(self.client.delete(f"/v1/visitors/{self.visitor.pk}/").status_code, 403)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.delete(f"/v1/visitors/{self.visitor.pk}/").status_code, 204)
        self.call.refresh_from_db()
        self.assertEqual((self.call.visitor_name, self.call.visitor_snapshot.name), ("", ""))
