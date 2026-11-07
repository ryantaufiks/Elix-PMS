"""LiveKit Cloud: short-lived room tokens (HS256 JWT) and room cleanup via the Twirp RoomService API."""
import time

import jwt
import requests

from . import config


class LiveKitNotConfigured(Exception):
    pass


def ensure_configured():
    url, key, secret = (config.get(n) for n in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))
    if not (url and key and secret):
        raise LiveKitNotConfigured(
            "LiveKit URL, API key and API secret must be set (admin > System settings, or LIVEKIT_* in .env)")
    return url, key, secret


def _sign(claims, ttl):
    _, key, secret = ensure_configured()
    now = int(time.time())
    return jwt.encode({"iss": key, "nbf": now, "exp": now + ttl, **claims}, secret, algorithm="HS256")


def room_token(room, identity, name="", can_publish=True):
    """Token letting ``identity`` join ``room`` only, valid for LIVEKIT_TOKEN_TTL_SECONDS."""
    return _sign({
        "sub": identity,
        "name": name or identity,
        "video": {"room": room, "roomJoin": True, "canPublish": can_publish, "canSubscribe": True,
                  "canPublishData": True},
    }, config.get("LIVEKIT_TOKEN_TTL_SECONDS"))


def connection_info(room, identity, name=""):
    return {"url": config.get("LIVEKIT_URL"), "room": room, "token": room_token(room, identity, name)}


def _api_url(method):
    base = config.get("LIVEKIT_URL").replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
    return f"{base}/twirp/livekit.RoomService/{method}"


def _room_service(method, payload, room=""):
    grants = {"roomCreate": True, "roomList": True, "roomAdmin": True}
    if room:
        grants["room"] = room
    token = _sign({"sub": "elix-server", "video": grants}, 60)
    response = requests.post(_api_url(method), json=payload, timeout=5,
                             headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json() if response.content else {}


def delete_room(room):
    """Disconnect everyone from a call room. A room that never started counts as success."""
    try:
        _room_service("DeleteRoom", {"room": room}, room)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise


def list_rooms():
    return _room_service("ListRooms", {}).get("rooms", [])
