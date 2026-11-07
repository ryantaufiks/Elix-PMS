from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from core import models as m
from myproject.asgi import application

from .factories import make_condo, make_staff

IN_MEMORY = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
class EventsSocketTests(TransactionTestCase):
    async def test_staff_receive_access_logs_of_their_condo(self):
        condo, other = await sync_to_async(make_condo)("alpha"), await sync_to_async(make_condo)("beta")
        guard = await sync_to_async(make_staff)("guard", condo, m.StaffAssignment.Role.SECURITY)
        token = await sync_to_async(lambda: str(AccessToken.for_user(guard)))()

        socket = WebsocketCommunicator(application, f"/ws/events/?token={token}")
        connected, _ = await socket.connect()
        self.assertTrue(connected)

        await sync_to_async(m.AccessLog.objects.create)(condominium=other, method="manual", result="granted")
        await sync_to_async(m.AccessLog.objects.create)(condominium=condo, method="manual", result="granted",
                                                        reason="mine")
        message = await socket.receive_json_from(timeout=3)
        self.assertEqual((message["type"], message["data"]["reason"]), ("access_log", "mine"))
        self.assertTrue(await socket.receive_nothing(timeout=0.2))
        await socket.disconnect()

    async def test_rejects_missing_token(self):
        socket = WebsocketCommunicator(application, "/ws/events/")
        connected, code = await socket.connect()
        self.assertFalse(connected)


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
class KioskSocketTests(TransactionTestCase):
    async def test_kiosk_hears_its_call_being_approved(self):
        from unittest import mock

        from core import intercom
        from .factories import make_resident, make_unit

        def setup():
            condo = make_condo("alpha")
            gate = m.AccessGate.objects.create(condominium=condo, name="Lobby")
            kiosk = m.Kiosk(condominium=condo, gate=gate, name="Lobby kiosk")
            token = kiosk.issue_token()
            kiosk.save()
            unit = make_unit(condo)
            return kiosk, token, unit, make_resident("alice", unit)

        kiosk, token, unit, alice = await sync_to_async(setup)()
        socket = WebsocketCommunicator(application, f"/ws/events/?kiosk_token={token}")
        self.assertTrue((await socket.connect())[0])

        with mock.patch("core.tasks.push_incoming_call.delay"), mock.patch("core.tasks.expire_call.apply_async"), \
                mock.patch("core.tasks.finish_call.apply_async"), mock.patch("core.tasks.open_gate.delay"):
            call = await sync_to_async(intercom.start)(kiosk, unit, "Courier")
            self.assertEqual((await socket.receive_json_from(timeout=3))["data"]["status"], "ringing")
            await sync_to_async(intercom.unlock)(call, alice)
        message = await socket.receive_json_from(timeout=3)
        self.assertEqual((message["type"], message["data"]["status"]), ("intercom_call", "approved"))
        await socket.disconnect()

    async def test_bad_kiosk_token_rejected(self):
        socket = WebsocketCommunicator(application, "/ws/events/?kiosk_token=kio_nope")
        self.assertFalse((await socket.connect())[0])
