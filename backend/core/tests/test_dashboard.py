import shutil
import tempfile
from datetime import timedelta

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.files.base import ContentFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from core import models as m
from myproject.asgi import application

from .factories import make_condo, make_invitation, make_resident, make_staff, make_unit, make_user

SECURITY, ADMIN = m.StaffAssignment.Role.SECURITY, m.StaffAssignment.Role.ADMIN


class DashboardSummaryTests(APITestCase):
    def setUp(self):
        self.condo, self.other = make_condo("alpha"), make_condo("beta")
        self.unit = make_unit(self.condo)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")
        self.guard = make_staff("guard", self.condo, SECURITY)

    def summary(self, condo):
        return self.client.get("/v1/dashboard/summary/", {"condominium": condo.pk})

    def test_counts_today_and_device_health(self):
        log = lambda result, **kw: m.AccessLog.objects.create(condominium=self.condo, method="manual", result=result, **kw)
        log("granted"), log("granted"), log("denied"), log("error")
        log("granted", occurred_at=timezone.now() - timedelta(days=2))
        m.AccessLog.objects.create(condominium=self.other, method="manual", result="granted")
        make_invitation(self.unit, make_resident("alice", self.unit))
        m.RelayController.objects.create(gate=self.gate, name="R1", provider="shelly", last_error="Timed out")
        m.RelayController.objects.create(gate=self.gate, name="R2", provider="shelly")
        m.Kiosk.objects.create(condominium=self.condo, name="Lobby", last_seen_at=timezone.now())
        m.Kiosk.objects.create(condominium=self.condo, name="Side")

        self.client.force_authenticate(self.guard)
        data = self.summary(self.condo).data
        self.assertEqual((data["granted_today"], data["denied_today"], data["errors_today"]), (2, 1, 1))
        self.assertEqual(data["invitations_today"], 1)
        self.assertEqual((data["relays_total"], data["relays_failing"]), (2, 1))
        self.assertEqual((data["kiosks_total"], data["kiosks_offline"]), (2, 1))
        self.assertEqual(len(data["hourly"]), 24)
        self.assertEqual(sum(h["granted"] for h in data["hourly"]), 2)
        self.assertEqual(data["by_method"], {"manual": 4})
        self.assertEqual(data["gates"], [{"id": self.gate.pk, "name": "Main", "gate_type": "vehicle", "is_active": True,
                                          "relays_total": 2, "relays_failing": 1}])

    def test_only_staff_of_the_condo(self):
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.summary(self.other).status_code, 403)
        self.client.force_authenticate(make_resident("bob", self.unit))
        self.assertEqual(self.summary(self.condo).status_code, 403)
        self.client.force_authenticate(m.User.objects.create_superuser("root", "r@example.com", "pw-123456!"))
        self.assertEqual(self.summary(self.other).status_code, 200)


class AccessLogDisplayTests(APITestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main gate")
        self.guard = make_staff("guard", self.condo, SECURITY)
        self.guard.first_name, self.guard.last_name = "Ali", "Rahman"
        self.guard.save()

    def test_names_for_display_and_snapshot_behind_auth(self):
        invitation = make_invitation(self.unit, make_resident("alice", self.unit), visitor_name="Lim Mei")
        log = m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, unit=self.unit, method="qr",
                                         result="granted", actor=self.guard, invitation=invitation)
        log.snapshot.save("cam.jpg", ContentFile(b"\xff\xd8jpeg"))
        self.client.force_authenticate(self.guard)
        row = self.client.get("/v1/access-logs/").data["results"][0]
        self.assertEqual((row["gate_name"], row["actor_name"], row["visitor_name"]), ("Main gate", "Ali Rahman", "Lim Mei"))
        self.assertIn("#05-12", row["unit_display"])
        self.assertTrue(row["has_snapshot"])
        self.assertNotIn("snapshot", row)
        response = self.client.get(f"/v1/access-logs/{log.pk}/snapshot/")
        self.assertEqual((response.status_code, response["Cache-Control"]), (200, "private, no-store"))
        m.AccessLog.objects.create(condominium=self.condo, gate=None, method="lpr", result="denied", plate_number="SGX1A")
        row = self.client.get("/v1/access-logs/").data["results"][0]
        self.assertEqual((row["unit_display"], row["gate_name"], row["visitor_name"]), ("", "", ""))
        self.client.force_authenticate(make_user("stranger"))
        self.assertEqual(self.client.get(f"/v1/access-logs/{log.pk}/snapshot/").status_code, 404)


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class SuperuserSocketTests(TransactionTestCase):
    async def test_superuser_receives_every_condo(self):
        condo = await sync_to_async(make_condo)("alpha")
        root = await sync_to_async(m.User.objects.create_superuser)("root", "r@example.com", "pw-123456!")
        token = await sync_to_async(lambda: str(AccessToken.for_user(root)))()
        socket = WebsocketCommunicator(application, f"/ws/events/?token={token}")
        self.assertTrue((await socket.connect())[0])
        await sync_to_async(m.AccessLog.objects.create)(condominium=condo, method="manual", result="granted")
        message = await socket.receive_json_from(timeout=3)
        self.assertEqual(message["type"], "access_log")
        await socket.disconnect()
