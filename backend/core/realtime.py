"""Live events over WebSocket.

Clients connect to ``/ws/events/?token=<JWT access token>`` and receive JSON
``{"type": "access_log", "data": {...}}`` for the condominiums they staff and
the units they live in.
"""
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .scoping import resident_unit_ids, staff_condo_ids


def condo_group(condo_id):
    return f"condo.{condo_id}"


def unit_group(unit_id):
    return f"unit.{unit_id}"


def kiosk_group(kiosk_id):
    return f"kiosk.{kiosk_id}"


class JWTQueryAuthMiddleware:
    """Authenticates a WebSocket from a ``?token=`` query parameter (browsers cannot set headers)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [None])[0]
        kiosk_token = query.get("kiosk_token", [None])[0]
        scope["user"] = await self._user(token) if token else AnonymousUser()
        scope["kiosk"] = await self._kiosk(kiosk_token) if kiosk_token else None
        return await self.app(scope, receive, send)

    @database_sync_to_async
    def _kiosk(self, raw):
        from .kiosk_auth import kiosk_from_token

        return kiosk_from_token(raw)

    @database_sync_to_async
    def _user(self, token):
        auth = JWTAuthentication()
        try:
            return auth.get_user(auth.get_validated_token(token))
        except (InvalidToken, TokenError):
            return AnonymousUser()


class EventsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user, kiosk = self.scope["user"], self.scope.get("kiosk")
        if kiosk is not None:
            self.groups_joined = [kiosk_group(kiosk.pk)]
        elif user.is_authenticated:
            self.groups_joined = await self._groups(user)
        else:
            await self.close(code=4401)
            return
        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        for group in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    @database_sync_to_async
    def _groups(self, user):
        return [condo_group(c) for c in staff_condo_ids(user)] + [unit_group(u) for u in resident_unit_ids(user)]

    async def event(self, message):
        await self.send_json(message["payload"])


def broadcast(condo_id, unit_id, event_type, data, kiosk_id=None):
    layer = get_channel_layer()
    payload = {"type": "event", "payload": {"type": event_type, "data": data}}
    groups = [condo_group(condo_id)] + ([unit_group(unit_id)] if unit_id else []) + \
        ([kiosk_group(kiosk_id)] if kiosk_id else [])
    for group in groups:
        async_to_sync(layer.group_send)(group, payload)


def broadcast_call(call):
    """Tell the kiosk, the unit's phones and the guardhouse about a call's new state."""
    import logging

    from .serializers import IntercomCallSerializer

    try:
        broadcast(call.condominium_id, call.unit_id, "intercom_call", IntercomCallSerializer(call).data,
                  kiosk_id=call.kiosk_id)
    except Exception:  # Redis trouble must not break the call flow.
        logging.getLogger(__name__).exception("Failed to broadcast call %s", call.pk)
