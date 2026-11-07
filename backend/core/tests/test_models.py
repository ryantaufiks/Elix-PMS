from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from core import models as m
from core.tasks import expire_invitations
from core.validators import normalize_plate

from .factories import make_condo, make_invitation, make_resident, make_unit


class EncryptedFieldTests(TestCase):
    def test_secret_is_encrypted_at_rest_and_readable_in_python(self):
        account = m.IntegrationAccount.objects.create(
            condominium=make_condo(), provider=m.Provider.SHELLY, label="Shelly",
            shelly_server_uri="https://shelly-103-eu.shelly.cloud", shelly_auth_key="super-secret",
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT shelly_auth_key FROM core_integrationaccount WHERE id = %s", [account.pk])
            raw = cursor.fetchone()[0]
        self.assertTrue(raw.startswith("enc$"))
        self.assertNotIn("super-secret", raw)
        self.assertEqual(m.IntegrationAccount.objects.get(pk=account.pk).shelly_auth_key, "super-secret")

    def test_provider_specific_fields_are_required(self):
        account = m.IntegrationAccount(condominium=make_condo(), provider=m.Provider.EWELINK, label="x")
        with self.assertRaises(ValidationError) as ctx:
            account.full_clean()
        self.assertIn("ewelink_app_id", ctx.exception.message_dict)


class UnitAndVehicleTests(TestCase):
    def test_singapore_unit_label(self):
        unit = make_unit(make_condo(), floor="05", number="12")
        self.assertEqual(unit.label, "#05-12")
        self.assertEqual(str(unit), "Block 1 #05-12")

    def test_plate_is_normalised(self):
        self.assertEqual(normalize_plate("sba 1234-a"), "SBA1234A")
        unit = make_unit(make_condo())
        vehicle = m.Vehicle.objects.create(unit=unit, plate_number="sba 1234 a")
        self.assertEqual(vehicle.plate_number, "SBA1234A")
        self.assertEqual(vehicle.condominium, unit.condominium)


class RelayValidationTests(TestCase):
    def test_account_must_match_provider_and_condo(self):
        condo, other = make_condo("alpha"), make_condo("beta")
        gate = m.AccessGate.objects.create(condominium=condo, name="Main")
        account = m.IntegrationAccount.objects.create(
            condominium=other, provider=m.Provider.SHELLY, label="S",
            shelly_server_uri="https://x.shelly.cloud", shelly_auth_key="k",
        )
        relay = m.RelayController(gate=gate, name="Barrier", provider=m.Provider.EWELINK, account=account,
                                  cloud_device_id="1000abc")
        with self.assertRaises(ValidationError) as ctx:
            relay.full_clean()
        self.assertIn("account", ctx.exception.message_dict)

    def test_local_mode_requires_ip(self):
        gate = m.AccessGate.objects.create(condominium=make_condo(), name="Main")
        relay = m.RelayController(gate=gate, name="Door", provider=m.Provider.SHELLY,
                                  control_mode=m.RelayController.ControlMode.LOCAL)
        with self.assertRaises(ValidationError) as ctx:
            relay.full_clean()
        self.assertIn("local_ip", ctx.exception.message_dict)


class InvitationTests(TestCase):
    def setUp(self):
        self.condo = make_condo(invitation_max_days=7)
        self.unit = make_unit(self.condo)
        self.host = make_resident("host", self.unit)

    def test_single_entry_invitation_completes_after_use(self):
        invitation = make_invitation(self.unit, self.host, vehicle_plate="sjk 88 x")
        self.assertEqual(invitation.vehicle_plate, "SJK88X")
        self.assertEqual(invitation.check_usable(), (True, ""))
        invitation.record_entry()
        self.assertEqual(invitation.status, m.Invitation.Status.COMPLETED)
        self.assertFalse(invitation.check_usable()[0])

    def test_validity_window_cannot_exceed_condo_limit(self):
        now = timezone.now()
        invitation = m.Invitation(unit=self.unit, host=self.host, visitor_name="X",
                                  valid_from=now, valid_until=now + timedelta(days=8))
        with self.assertRaises(ValidationError) as ctx:
            invitation.full_clean()
        self.assertIn("valid_until", ctx.exception.message_dict)

    def test_face_requirement_needs_condo_feature(self):
        now = timezone.now()
        invitation = m.Invitation(unit=self.unit, host=self.host, visitor_name="X", require_face=True,
                                  valid_from=now, valid_until=now + timedelta(hours=1))
        with self.assertRaises(ValidationError) as ctx:
            invitation.full_clean()
        self.assertIn("require_face", ctx.exception.message_dict)

    def test_expire_task(self):
        now = timezone.now()
        past = make_invitation(self.unit, self.host, valid_from=now - timedelta(days=2), valid_until=now - timedelta(days=1))
        current = make_invitation(self.unit, self.host)
        self.assertEqual(expire_invitations(), 1)
        past.refresh_from_db(); current.refresh_from_db()
        self.assertEqual(past.status, m.Invitation.Status.EXPIRED)
        self.assertEqual(current.status, m.Invitation.Status.ACTIVE)


class LprCameraTests(TestCase):
    def test_webhook_password_is_hashed(self):
        gate = m.AccessGate.objects.create(condominium=make_condo(), name="Main")
        camera = m.LprCamera(gate=gate, name="Cam", device_id="DH-001", webhook_username="cam1")
        camera.set_webhook_password("cam-pass")
        camera.save()
        self.assertNotIn("cam-pass", camera.webhook_password_hash)
        self.assertTrue(camera.check_webhook_password("cam-pass"))
        self.assertFalse(camera.check_webhook_password("wrong"))
