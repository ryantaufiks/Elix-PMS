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
