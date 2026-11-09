"""The kiosk AI assistant (OpenAI): knowledge, rules and actions, for both modes.

- **Speech to text** (default): the kiosk records what the visitor says; the server transcribes it,
  asks a chat model for the answer and the screen actions, and turns the answer into speech.
- **Realtime**: the server mints a short-lived client secret with the same instructions and actions,
  and the kiosk talks to OpenAI directly over WebRTC. The site's API key never reaches the kiosk.

Nothing the visitor says is stored: the kiosk keeps the conversation in memory and sends the recent
turns with each request; the server only counts sessions and turns for the usage limits.
"""
import json
import logging

import requests
from django.utils import timezone

from . import config
from . import models as m

log = logging.getLogger(__name__)

API = "https://api.openai.com/v1/"
TIMEOUT = 30
MAX_HISTORY = 12
MAX_TEXT = 1000
PURPOSES = ["guest", "delivery", "food", "contractor", "pickup", "other"]


class AssistantError(Exception):
    """Shown to the visitor (in general terms) and logged; never includes what they said."""


def api_key(condo):
    site = m.AssistantSettings.objects.filter(condominium=condo).first()
    return (site.openai_api_key if site else "") or config.get("OPENAI_API_KEY")


def site_settings(condo):
    return m.AssistantSettings.objects.filter(condominium=condo).first() or m.AssistantSettings(condominium=condo)


def available(condo):
    return site_settings(condo).enabled and bool(api_key(condo))


# --- What the assistant knows and may do -------------------------------------------------------------

def instructions(condo):
    site = site_settings(condo)
    maps = m.AssistantMap.objects.filter(condominium=condo, is_active=True)
    modules = m.AssistantModule.objects.filter(condominium=condo, is_active=True)
    parts = [
        f"You are {site.name}, the voice concierge on the visitor kiosk at the entrance of {condo.name}"
        f"{f', {condo.address}' if condo.address else ''}, a residential condominium in Singapore. You help visitors, "
        "delivery riders and contractors with directions, facilities, rules and registering their visit.",
        "Rules:",
        "- Only talk about this condominium, visiting it and its immediate surroundings. Politely decline anything else.",
        "- Never reveal or confirm anything about residents: names, who lives in which unit, phone numbers, whether "
        "someone is home. If asked, say the visitor can call the unit from this kiosk.",
        "- You cannot open gates or let anyone in. Entry is by calling the unit, an invitation QR, or a walk-in pass.",
        "- Use only the knowledge below. If you do not know, say so and suggest the guardhouse or management office.",
        "- This is spoken: answer in one to three short sentences, warm and clear, without lists, symbols or markdown.",
        f"- Reply in the language the visitor speaks{f' (you speak {site.languages})' if site.languages else ''}.",
        "- To register a walk-in, ask for the unit they are visiting, their name and the purpose (and the company for "
        "deliveries or contractors), then call start_walk_in. The kiosk then asks for the rest on screen.",
        "- When a map would help, call show_map with the best match, then describe the way in words.",
    ]
    if site.instructions.strip():
        parts += ["Guidance from the management:", site.instructions.strip()]
    if maps:
        parts += ["Maps you can show (id: name - what it shows):",
                  *[f"{x.pk}: {x.name}{f' - {x.description}' if x.description else ''}" for x in maps]]
    if modules:
        parts.append("Knowledge:")
        for module in modules:
            parts += [f"## {module.title}", module.content.strip()]
    return "\n".join(parts)


def tools(condo):
    """Screen actions, as JSON-schema functions (the kiosk carries them out)."""
    map_ids = list(m.AssistantMap.objects.filter(condominium=condo, is_active=True).values_list("pk", flat=True))
    found = [
        {"name": "start_walk_in", "description": "Open the walk-in registration with what the visitor said.",
         "parameters": {"type": "object", "properties": {
             "unit": {"type": "string", "description": "Unit they visit as said, e.g. '05-12' or 'Block 2 #05-12'."},
             "visitor_name": {"type": "string"},
             "purpose": {"type": "string", "enum": PURPOSES},
             "company": {"type": "string", "description": "Courier, food platform or contractor company."},
         }, "required": ["unit"]}},
        {"name": "call_resident", "description": "Open the screen to video call a unit (the visitor confirms the unit).",
         "parameters": {"type": "object", "properties": {"unit": {"type": "string"}}, "required": ["unit"]}},
        {"name": "open_screen", "description": "Open a kiosk screen: scan an invitation QR, or check out when leaving.",
         "parameters": {"type": "object", "properties": {"screen": {"type": "string", "enum": ["invitation", "checkout"]}},
                        "required": ["screen"]}},
        {"name": "end_conversation", "description": "Close the assistant when the visitor is done or says goodbye.",
         "parameters": {"type": "object", "properties": {}}},
    ]
    if map_ids:
        found.insert(0, {"name": "show_map", "description": "Show a map or floor plan on the kiosk screen.",
                         "parameters": {"type": "object", "properties": {"map_id": {"type": "integer", "enum": map_ids}},
                                        "required": ["map_id"]}})
    return found


def action(name, arguments):
    """A tool call the kiosk may act on, or None. Arguments are checked: they come from the model."""
    try:
        args = json.loads(arguments or "{}")
    except ValueError:
        return None
    if not isinstance(args, dict):
        return None
    clip = lambda v: str(v or "").strip()[:100]  # noqa: E731
    if name == "show_map" and isinstance(args.get("map_id"), int):
        return {"type": "show_map", "map_id": args["map_id"]}
    if name in ("start_walk_in", "call_resident") and clip(args.get("unit")):
        found = {"type": name, "unit": clip(args["unit"])}
        if name == "start_walk_in":
            found |= {"visitor_name": clip(args.get("visitor_name")), "company": clip(args.get("company")),
                      "purpose": args.get("purpose") if args.get("purpose") in PURPOSES else ""}
        return found
    if name == "open_screen" and args.get("screen") in ("invitation", "checkout"):
        return {"type": "open_screen", "screen": args["screen"]}
    if name == "end_conversation":
        return {"type": "end_conversation"}
    return None


# --- OpenAI calls ------------------------------------------------------------------------------------

def _post(key, path, **kwargs):
    try:
        response = requests.post(API + path, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        log.warning("OpenAI %s unreachable: %s", path, type(exc).__name__)
        raise AssistantError("The assistant is not reachable right now.") from exc
    if response.status_code >= 400:
        # The error body describes the request (model, key, quota), never the visitor's words.
        log.warning("OpenAI %s failed: HTTP %s %s", path, response.status_code, response.text[:300])
        raise AssistantError("The assistant is not available right now.")
    return response


def transcribe(condo, audio):
    s = m.SystemSettings.load()
    response = _post(api_key(condo), "audio/transcriptions",
                     data={"model": s.assistant_transcribe_model, "prompt": f"A visitor at {condo.name} condominium kiosk."},
                     files={"file": (audio.name or "speech.webm", audio.read(), audio.content_type or "audio/webm")})
    return response.json().get("text", "").strip()


def reply(condo, history):
    """(answer text, screen actions) for the conversation so far (the last message is the visitor's)."""
    s = m.SystemSettings.load()
    key = api_key(condo)
    functions = tools(condo)
    messages = [{"role": "system", "content": instructions(condo)}, *history]
    body = {"model": s.assistant_chat_model, "messages": messages, "max_completion_tokens": 300,
            "tools": [{"type": "function", "function": f} for f in functions]}
    choice = _post(key, "chat/completions", json=body).json()["choices"][0]["message"]
    calls = choice.get("tool_calls") or []
    actions = [a for a in (action(c["function"]["name"], c["function"].get("arguments")) for c in calls) if a]
    text = (choice.get("content") or "").strip()
    if calls and not text:
        # The model only acted: ask once more for what to say about it.
        messages += [{"role": "assistant", "content": None, "tool_calls": calls},
                     *[{"role": "tool", "tool_call_id": c["id"], "content": json.dumps({"done": True})} for c in calls]]
        follow = _post(key, "chat/completions", json={**body, "messages": messages, "tool_choice": "none"}).json()
        text = (follow["choices"][0]["message"].get("content") or "").strip()
    return text, actions


def speak(condo, text):
    """MP3 of ``text`` in the platform's voice."""
    s = m.SystemSettings.load()
    response = _post(api_key(condo), "audio/speech", json={
        "model": s.assistant_tts_model, "voice": s.assistant_voice, "input": text[:1500], "response_format": "mp3",
        "instructions": "Speak like a warm, attentive concierge: clear, friendly and unhurried.",
    })
    return response.content


def realtime_secret(condo):
    """A client secret (valid one minute) for one realtime conversation with this site's assistant."""
    s = m.SystemSettings.load()
    session = {
        "type": "realtime",
        "model": s.assistant_realtime_model,
        "instructions": instructions(condo),
        "max_output_tokens": 400,
        "audio": {
            "input": {"transcription": {"model": s.assistant_transcribe_model}, "turn_detection": {"type": "server_vad"}},
            "output": {"voice": s.assistant_voice},
        },
        "tools": [{"type": "function", **f} for f in tools(condo)],
    }
    data = _post(api_key(condo), "realtime/client_secrets",
                 json={"expires_after": {"anchor": "created_at", "seconds": 60}, "session": session}).json()
    return data["value"]


# --- Sessions and limits -----------------------------------------------------------------------------

def start_session(kiosk):
    """A new conversation at ``kiosk``, or AssistantError when it is off or over today's limit."""
    condo = kiosk.condominium
    if not available(condo):
        raise AssistantError("The assistant is not available at this kiosk.")
    s = m.SystemSettings.load()
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    if m.AssistantSession.objects.filter(kiosk=kiosk, started_at__gte=today).count() >= s.assistant_daily_sessions:
        raise AssistantError("The assistant is resting for today. Please ask at the guardhouse.")
    return m.AssistantSession.objects.create(condominium=condo, kiosk=kiosk, mode=s.assistant_mode)


def check_session(session):
    """Raise AssistantError once a conversation is over its time or turn budget."""
    s = m.SystemSettings.load()
    if session.ended_at or (timezone.now() - session.started_at).total_seconds() > s.assistant_max_session_seconds + 30:
        raise AssistantError("This conversation has ended. Tap the assistant to start again.")
    if session.turns >= 40:
        raise AssistantError("This conversation has ended. Tap the assistant to start again.")


def clean_history(history):
    """The recent turns the kiosk sent, reduced to plain user/assistant text."""
    if not isinstance(history, list):
        return []
    found = [{"role": h["role"], "content": h["content"][:MAX_TEXT]} for h in history
             if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str) and h["content"].strip()]
    return found[-MAX_HISTORY:]
