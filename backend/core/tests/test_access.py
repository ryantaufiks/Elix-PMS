import base64
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core import models as m
from core.tasks import open_gate

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit

DAHUA_PAYLOAD = {"Picture": {"Plate": {"PlateNumber": "SBA 1234 A", "PlateColor": "White"}},
                 "deviceID": "DH-ENTRY-1"}


@mock.patch("core.tasks.open_gate.delay")
class LprWebhookTests(TestCase):
    def setUp(self):
        self.condo = make_condo(lpr_enabled=True)
        self.unit = make_unit(self.condo)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        self.camera = m.LprCamera(gate=self.gate, name="Entry", device_id="DH-ENTRY-1", webhook_username="cam1")
        self.camera.set_webhook_password("campw")
        self.camera.save()

    def post(self, payload, password="campw"):
        auth = base64.b64encode(f"cam1:{password}".encode()).decode()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post("/v1/lpr-webhook/", json.dumps(payload), content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Basic {auth}")

    def test_rejects_bad_credentials(self, delay):
        self.assertEqual(self.post(DAHUA_PAYLOAD, password="wrong").status_code, 401)
        self.assertEqual(self.client.post("/v1/lpr-webhook/", "{}", content_type="application/json").status_code, 401)

    def test_disabled_condo_only_records_payload(self, delay):
        self.condo.lpr_enabled = False
        self.condo.save()
        response = self.post(DAHUA_PAYLOAD)
        self.assertEqual(response.json()["status"], "recorded")
        self.camera.refresh_from_db()
        self.assertEqual(self.camera.last_payload, DAHUA_PAYLOAD)
        self.assertFalse(m.AccessLog.objects.exists())
        delay.assert_not_called()

    def test_resident_plate_opens_gate(self, delay):
        vehicle = m.Vehicle.objects.create(unit=self.unit, plate_number="SBA1234A")
        response = self.post(DAHUA_PAYLOAD)
        self.assertEqual(response.json(), {"status": "granted", "plate": "SBA1234A", "reason": ""})
        log = m.AccessLog.objects.get()
        self.assertEqual((log.vehicle, log.unit, log.camera), (vehicle, self.unit, self.camera))
        delay.assert_called_once_with(log.pk)

    def test_vehicle_pass_dates(self, delay):
        today = timezone.localdate()
        vehicle = m.Vehicle.objects.create(unit=self.unit, plate_number="SBA1234A", kind="season",
                                           valid_from=today - timedelta(days=30), valid_until=today - timedelta(days=1))
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["reason"], f"Vehicle pass ended on {vehicle.valid_until:%d %b %Y}")
        m.AccessLog.objects.all().delete()
        vehicle.valid_from, vehicle.valid_until = today + timedelta(days=2), today + timedelta(days=30)
        vehicle.save()
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["reason"], f"Vehicle pass starts on {vehicle.valid_from:%d %b %Y}")
        m.AccessLog.objects.all().delete()
        vehicle.valid_from = today  # The last day still opens.
        vehicle.valid_until = today
        vehicle.save()
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["status"], "granted")

    def test_repeat_reads_are_debounced(self, delay):
        m.Vehicle.objects.create(unit=self.unit, plate_number="SBA1234A")
        self.post(DAHUA_PAYLOAD)
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["status"], "duplicate")
        self.assertEqual(m.AccessLog.objects.count(), 1)

    def test_unknown_plate_denied(self, delay):
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["status"], "denied")
        delay.assert_not_called()

    def test_invited_plate_counts_entry(self, delay):
        host = make_resident("host", self.unit)
        invitation = make_invitation(self.unit, host, vehicle_plate="SBA1234A", max_entries=1)
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["status"], "granted")
        invitation.refresh_from_db()
        self.assertEqual((invitation.entry_count, invitation.status), (1, m.Invitation.Status.COMPLETED))

    def test_invitation_requiring_face_is_not_auto_opened(self, delay):
        self.condo.face_verification_enabled = True
        self.condo.save()
        make_invitation(self.unit, make_resident("host", self.unit), vehicle_plate="SBA1234A", require_face=True)
        response = self.post(DAHUA_PAYLOAD).json()
        self.assertEqual(response["status"], "denied")
        self.assertIn("face", response["reason"])

    def test_invitation_for_other_gate_not_used(self, delay):
        other_gate = m.AccessGate.objects.create(condominium=self.condo, name="Back")
        invitation = make_invitation(self.unit, make_resident("host", self.unit), vehicle_plate="SBA1234A")
        invitation.gates.set([other_gate])
        self.assertEqual(self.post(DAHUA_PAYLOAD).json()["status"], "denied")

    def test_custom_plate_field_path(self, delay):
        self.camera.plate_field = "Events.0.Data.Plate"
        self.camera.save()
        m.Vehicle.objects.create(unit=self.unit, plate_number="SGX77B")
        payload = {"Events": [{"Data": {"Plate": "sgx 77 b", "PlateNumber": "WRONG1A"}}]}
        self.assertEqual(self.post(payload).json()["plate"], "SGX77B")

    def test_payload_without_plate(self, delay):
        self.assertEqual(self.post({"Heartbeat": True}).json()["status"], "ignored")


class OpenGateTaskTests(TestCase):
    def setUp(self):
        self.condo = make_condo()
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        self.log = m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, method="manual", result="granted")

    def test_no_relay_marks_error(self):
        open_gate(self.log.pk)
        self.log.refresh_from_db()
        self.assertEqual(self.log.result, m.AccessLog.Result.ERROR)
        self.assertIn("No active relay", self.log.reason)

    def test_failed_relay_records_error(self):
        relay = m.RelayController.objects.create(gate=self.gate, name="R", provider="shelly", control_mode="local",
                                                 local_ip="127.0.0.1", local_port=1)
        open_gate(self.log.pk)
        self.log.refresh_from_db(); relay.refresh_from_db()
        self.assertEqual(self.log.result, m.AccessLog.Result.ERROR)
        self.assertIn("Cannot reach", relay.last_error)

    @mock.patch("core.relays.pulse")
    def test_success_records_relay(self, pulse):
        relay = m.RelayController.objects.create(gate=self.gate, name="R", provider="shelly", control_mode="local",
                                                 local_ip="127.0.0.1")
        open_gate(self.log.pk)
        self.log.refresh_from_db(); relay.refresh_from_db()
        self.assertEqual((self.log.result, self.log.relay), (m.AccessLog.Result.GRANTED, relay))
        self.assertIsNotNone(relay.last_triggered_at)


@mock.patch("core.tasks.open_gate.delay")
class ManualOpenApiTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        self.guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        self.resident = make_resident("res", make_unit(self.condo))

    def test_guard_can_open(self, delay):
        self.client.force_authenticate(self.guard)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/v1/gates/{self.gate.id}/open/", {"reason": "Ambulance"})
        self.assertEqual(response.status_code, 202)
        log = m.AccessLog.objects.get()
        self.assertEqual((log.method, log.actor, log.reason), ("manual", self.guard, "Ambulance"))
        delay.assert_called_once_with(log.pk)

    def test_resident_cannot_open(self, delay):
        self.client.force_authenticate(self.resident)
        self.assertEqual(self.client.post(f"/v1/gates/{self.gate.id}/open/").status_code, 403)
