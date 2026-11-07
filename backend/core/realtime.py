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


class JWTQueryAuthMiddleware:
    """Authenticates a WebSocket from a ``?token=`` query parameter (browsers cannot set headers)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = parse_qs(scope.get("query_string", b"").decode()).get("token", [None])[0]
        scope["user"] = await self._user(token) if token else AnonymousUser()
        return await self.app(scope, receive, send)

    @database_sync_to_async
    def _user(self, token):
        auth = JWTAuthentication()
        try:
            return auth.get_user(auth.get_validated_token(token))
        except (InvalidToken, TokenError):
            return AnonymousUser()


class EventsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        self.groups_joined = await self._groups(user)
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


def broadcast(condo_id, unit_id, event_type, data):
    layer = get_channel_layer()
    payload = {"type": "event", "payload": {"type": event_type, "data": data}}
    async_to_sync(layer.group_send)(condo_group(condo_id), payload)
    if unit_id:
        async_to_sync(layer.group_send)(unit_group(unit_id), payload)
