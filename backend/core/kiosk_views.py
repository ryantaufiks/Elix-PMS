"""API for kiosk tablets (``Authorization: Kiosk <token>``)."""
from django.core.cache import cache
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import access, assistant, entitlements, intercom, livekit, visits
from . import visitor_identity as identity
from . import models as m
from . import serializers as s
from .kiosk_auth import IsKiosk, KioskTokenAuthentication


class Rejected(Exception):
    def __init__(self, body, status_code=status.HTTP_400_BAD_REQUEST):
        self.response = Response(body, status=status_code)


class KioskView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsKiosk]

    @property
    def kiosk(self):
        return self.request.auth

    def handle_exception(self, exc):
        if isinstance(exc, Rejected):
            return exc.response
        return super().handle_exception(exc)

    def visitor_details(self, data, unit, *, details, photo, method, blocked_reason):
        """Validate what the visitor entered and record the visit. Returns (name, visitor, consented).

        ``details`` / ``photo``: whether this site requires them. Raises Rejected (400, or 403 for a
        blocked visitor, which is also logged as a denied entry)."""
        if unit.condominium_id != self.kiosk.condominium_id:
            raise Rejected({"unit": ["Unknown unit."]})
        try:
            phone = identity.normalize_phone(data["visitor_phone"])
            id_partial = identity.normalize_id_partial(data["visitor_id_partial"])
        except identity.InvalidIdentity as exc:
            field = "visitor_phone" if "mobile" in str(exc) else "visitor_id_partial"
            raise Rejected({field: [str(exc)]}) from exc
        name = data["visitor_name"].strip()
        returning = identity.visitor_from_ref(self.kiosk, data["visitor_ref"]) if data["visitor_ref"] else None
        errors = {}
        if details:
            if not name and returning is None:
                errors["visitor_name"] = ["Please enter your name."]
            if not data["purpose"]:
                errors["purpose"] = ["Please choose the purpose of your visit."]
        if photo and not data.get("snapshot"):
            errors["snapshot"] = ["A photo is required at this site."]
        if (details or photo) and not data["consent"]:
            errors["consent"] = ["Please accept the privacy notice."]
        if errors:
            raise Rejected(errors)

        # Personal data is kept only with the visitor's consent (the kiosk shows the privacy notice).
        consented = data["consent"]
        visitor = identity.record_visit(self.kiosk, ref=data["visitor_ref"] if returning else "", name=name,
                                        phone=phone, id_partial=id_partial, company=data["company"].strip(),
                                        consent=True) if consented else None
        if visitor is not None and visitor.is_blacklisted:
            if self.kiosk.gate_id:
                access.deny(self.kiosk.gate, method, reason=blocked_reason, unit=unit, visitor=visitor)
            raise Rejected({"detail": "Please see the guardhouse.", "blocked": True}, status.HTTP_403_FORBIDDEN)
        return name or (visitor.full_name if visitor else ""), visitor, consented


class KioskCallThrottle(SimpleRateThrottle):
    """Limits how fast one kiosk can ring units (prank protection)."""

    scope = "kiosk_call"

    @property
    def THROTTLE_RATES(self):
        # Read at request time (not import time) so settings overrides apply.
        return api_settings.DEFAULT_THROTTLE_RATES

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": f"kiosk-{request.auth.pk}"}


def face_template(condo, data, photo):
    """The face template sent with a photo, kept only when the site uses face check-out."""
    return data.get("face_descriptor") if condo.kiosk_checkout and condo.kiosk_face_checkout and photo else None


class KioskMeView(KioskView):
    @extend_schema(responses=s.KioskSelfSerializer)
    def get(self, request):
        """This kiosk's configuration. Also serves as a heartbeat (updates last seen)."""
        return Response(s.KioskSelfSerializer(self.kiosk).data)


class KioskWeatherView(KioskView):
    @extend_schema(responses=s.WeatherSerializer)
    def get(self, request):
        """The weather at this kiosk's site, shown under the date."""
        from .feed_views import weather_response

        return weather_response(self.kiosk.condominium)


class DirectoryView(KioskView, generics.ListAPIView):
    """Units a visitor can call: active units with at least one resident taking calls.

    ``?walk_in=1`` lists every active unit (walk-ins do not ring anyone). Resident names are
    deliberately not exposed. Filter with ``?q=`` (unit, floor or block)."""

    serializer_class = s.DirectoryUnitSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return m.Unit.objects.none()
        takes_calls = m.Residency.objects.filter(unit=OuterRef("pk"), is_active=True, receives_intercom_calls=True)
        qs = m.Unit.objects.filter(condominium=self.kiosk.condominium_id, is_active=True).select_related("block")
        if self.request.query_params.get("walk_in") != "1":
            if not entitlements.has(self.kiosk.condominium, "intercom"):
                return m.Unit.objects.none()  # no calls without the intercom module
            qs = qs.filter(Exists(takes_calls))
        if q := self.request.query_params.get("q", "").strip().lstrip("#"):
            floor, _, number = q.partition("-")
            qs = qs.filter(Q(unit_number__iexact=q) | Q(block__name__icontains=q)
                           | (Q(floor=floor, unit_number=number) if number else Q(floor=q)))
        return qs[:200]


class StartCallView(KioskView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [KioskCallThrottle]

    @extend_schema(request=s.StartCallSerializer, responses={201: s.CallWithConnectionSerializer})
    def post(self, request):
        """Ring a unit, or the guardhouse with ``guardhouse=true``. Returns the call and this kiosk's LiveKit
        connection; join the room straight away."""
        body = s.StartCallSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        condo = self.kiosk.condominium
        if data["guardhouse"]:
            # Someone who needs help: ring the guards straight away, nothing to fill in and nothing kept.
            unit, name, visitor, consented, purpose, company = None, "", None, False, "", ""
        else:
            unit, purpose, company = data["unit"], data["purpose"], data["company"].strip()
            name, visitor, consented = self.visitor_details(
                data, unit, details=condo.kiosk_visitor_form, photo=condo.kiosk_photo_required,
                method=m.AccessLog.Method.INTERCOM, blocked_reason="Blocked visitor tried to call a unit")
        try:
            livekit.ensure_configured()  # Fail before ringing anyone.
            snapshot = data.get("snapshot") if consented else None
            call = intercom.start(self.kiosk, unit, name, snapshot, visitor=visitor,
                                  purpose=purpose, company=company,
                                  face_descriptor=face_template(condo, data, snapshot))
            connection = livekit.connection_info(call.room_name, f"kiosk-{self.kiosk.pk}", self.kiosk.name)
        except livekit.LiveKitNotConfigured:
            return Response({"detail": "Video intercom is not configured on the server."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except intercom.CallError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"call": s.IntercomCallSerializer(call).data, "livekit": connection},
                        status=status.HTTP_201_CREATED)


class KioskCallView(KioskView):
    def _call(self, pk):
        return generics.get_object_or_404(m.IntercomCall, pk=pk, kiosk=self.kiosk)

    @extend_schema(responses=s.IntercomCallSerializer)
    def get(self, request, pk):
        """Poll the call state (the WebSocket pushes the same updates)."""
        return Response(s.IntercomCallSerializer(self._call(pk)).data)


class KioskHangupView(KioskCallView):
    @extend_schema(request=None, responses=s.IntercomCallSerializer)
    def post(self, request, pk):
        """Visitor walked away or pressed cancel."""
        call = intercom.hang_up(self._call(pk), m.IntercomCall.Status.CANCELLED)
        return Response(s.IntercomCallSerializer(call).data)


class KioskCheckInThrottle(KioskCallThrottle):
    scope = "kiosk_checkin"


def _pass(invitation):
    return s.InvitationPassSerializer(invitation).data if invitation else None


class QrLookupView(KioskView):
    throttle_classes = [KioskCheckInThrottle]

    @extend_schema(request=s.QrCodeSerializer, responses=s.QrCheckInResultSerializer)
    def post(self, request):
        """Show who a scanned QR belongs to and what the kiosk still needs (face photo), without opening."""
        body = s.QrCodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not self.kiosk.gate_id:
            return Response({"detail": "This kiosk is not linked to a gate."}, status=status.HTTP_409_CONFLICT)
        invitation = access.find_invitation(self.kiosk.condominium_id, body.validated_data["code"])
        problem = access.qr_problem(invitation, self.kiosk.gate)
        result = "denied" if problem else ("face_required" if invitation.needs_face else "granted")
        return Response({"result": result, "reason": problem, "invitation": _pass(invitation)})


class QrCheckInView(KioskView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [KioskCheckInThrottle]

    @extend_schema(request=s.QrCheckInSerializer, responses=s.QrCheckInResultSerializer)
    def post(self, request):
        """Check a visitor in with their invitation QR. Opens the kiosk's gate when granted.

        ``plate`` (optional) must match the invitation's plate if both are set. Invitations that
        require a face check answer ``face_required`` until ``face_photo`` is sent."""
        body = s.QrCheckInSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not self.kiosk.gate_id:
            return Response({"detail": "This kiosk is not linked to a gate."}, status=status.HTTP_409_CONFLICT)
        data = body.validated_data
        try:
            log = access.handle_qr(self.kiosk, data["code"], data["plate"], data.get("face_photo"),
                                   face_template(self.kiosk.condominium, data, data.get("face_photo")))
        except access.FaceRequired:
            invitation = access.find_invitation(self.kiosk.condominium_id, data["code"])
            return Response({"result": "face_required", "reason": "Please look at the camera.", "invitation": _pass(invitation)})
        invitation = log.invitation
        if invitation is not None:
            invitation.refresh_from_db()
        return Response({"result": log.result, "reason": log.reason, "invitation": _pass(invitation)})


class VisitorLookupView(KioskView):
    throttle_classes = [KioskCheckInThrottle]

    @extend_schema(request=s.VisitorLookupSerializer, responses=s.VisitorLookupResultSerializer)
    def post(self, request):
        """Find a returning visitor by mobile number or last 4 of NRIC/FIN. Only a masked name is returned."""
        body = s.VisitorLookupSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            phone = identity.normalize_phone(body.validated_data["phone"])
            id_partial = identity.normalize_id_partial(body.validated_data["id_partial"])
        except identity.InvalidIdentity as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        visitor = identity.find_returning(self.kiosk.condominium_id, phone, id_partial)
        if visitor is None:
            return Response({"found": False, "blocked": False, "ref": "", "masked_name": "", "company": "", "purpose": ""})
        last_call = visitor.calls.exclude(visitor_purpose="").order_by("-created_at").first()
        return Response({
            "found": True,
            "blocked": visitor.is_blacklisted,
            "ref": "" if visitor.is_blacklisted else identity.make_ref(self.kiosk, visitor),
            "masked_name": identity.mask_name(visitor.full_name),
            "company": visitor.company,
            "purpose": last_call.visitor_purpose if last_call else "",
        })


class WalkInView(KioskView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [KioskCheckInThrottle]

    @extend_schema(request=s.WalkInRegisterSerializer, responses={201: s.VisitSlipSerializer})
    def post(self, request):
        """Register a walk-in visitor. Returns the slip to print: pass number (e.g. V001) and check-out QR.

        The gate is not opened; the visitor shows the slip to security."""
        condo = self.kiosk.condominium
        if not condo.kiosk_walk_in:
            return Response({"detail": "Walk-in registration is turned off at this site."}, status=status.HTTP_409_CONFLICT)
        body = s.WalkInRegisterSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        name, visitor, _ = self.visitor_details(data, data["unit"], details=True, photo=condo.kiosk_walk_in_photo,
                                                method=m.AccessLog.Method.WALK_IN,
                                                blocked_reason="Blocked visitor tried to register as a walk-in")
        visit = visits.issue(self.kiosk, data["unit"], data["purpose"], name, company=data["company"].strip(),
                             visitor=visitor, snapshot=data.get("snapshot"),
                             face_descriptor=face_template(condo, data, data.get("snapshot")))
        return Response(s.VisitSlipSerializer(visit).data, status=status.HTTP_201_CREATED)


PIN_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 60


class WalkInCheckOutView(KioskView):
    throttle_classes = [KioskCheckInThrottle]

    def _pin_failures(self):
        return f"kiosk-pin-failures-{self.kiosk.pk}"

    @extend_schema(request=s.KioskCheckOutSerializer, responses=s.WalkInCheckOutResultSerializer)
    def post(self, request):
        """Check a visitor out with the QR on their pass (or invitation), its 4-digit PIN, or their face template.

        A PIN or face only matches a visitor still on site. After 5 wrong PINs the kiosk refuses PINs for a
        minute. A face must match one visitor closely and clearly better than anyone else; otherwise the
        answer is 404 with ``reason`` (no_match, ambiguous or none_enrolled)."""
        body = s.KioskCheckOutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        code, pin, face = body.validated_data["code"], body.validated_data["pin"], body.validated_data["face"]
        condo = self.kiosk.condominium
        if face and not code and not pin:
            if not (condo.kiosk_checkout and condo.kiosk_face_checkout and entitlements.has(condo, "face_kiosk")):
                return Response({"detail": "Face check-out is turned off at this site."}, status=status.HTTP_409_CONFLICT)
            with transaction.atomic():
                visit, reason = visits.match_face(condo.pk, face, lock=True)
                if visit is None:
                    return Response({"detail": "Face not recognised.", "reason": reason}, status=status.HTTP_404_NOT_FOUND)
                done = visits.check_out(visit)
            return Response({"result": "checked_out" if done else "already_checked_out",
                             "walk_in": s.VisitSlipSerializer(visit).data})
        if pin and not code:
            if not condo.kiosk_checkout:
                return Response({"detail": "Self check-out is turned off at this site."}, status=status.HTTP_409_CONFLICT)
            if cache.get(self._pin_failures(), 0) >= PIN_ATTEMPTS:
                return Response({"detail": "Too many wrong PINs. Please wait a minute or see the guardhouse."},
                                status=status.HTTP_429_TOO_MANY_REQUESTS)
        with transaction.atomic():
            visit = visits.find(condo.pk, code, lock=True) if code else visits.find_by_pin(condo.pk, pin, lock=True)
            if visit is None:
                if not code:
                    cache.set(self._pin_failures(), cache.get(self._pin_failures(), 0) + 1, PIN_LOCKOUT_SECONDS)
                return Response({"detail": "Unknown PIN." if not code else "Unknown pass."}, status=status.HTTP_404_NOT_FOUND)
            done = visits.check_out(visit)
        return Response({"result": "checked_out" if done else "already_checked_out",
                         "walk_in": s.VisitSlipSerializer(visit).data})


class KioskCallPassView(KioskCallView):
    @extend_schema(responses=s.VisitSlipSerializer)
    def get(self, request, pk):
        """The visitor pass (QR and PIN) for a call the resident approved, to show on screen and optionally print."""
        visit = self._call(pk).visits.order_by("-created_at").first()
        if visit is None:
            return Response({"detail": "No pass for this call."}, status=status.HTTP_404_NOT_FOUND)
        return Response(s.VisitSlipSerializer(visit).data)


# --- AI assistant -------------------------------------------------------------------------------------

class KioskAssistantThrottle(KioskCallThrottle):
    scope = "kiosk_assistant"


class KioskAssistantView(KioskView):
    @extend_schema(responses=s.KioskAssistantSerializer)
    def get(self, request):
        """Whether this kiosk offers the assistant, how it introduces itself, and its maps."""
        condo = self.kiosk.condominium
        site = assistant.site_settings(condo)
        maps = m.AssistantMap.objects.filter(condominium=condo, is_active=True)
        return Response(s.KioskAssistantSerializer({
            "enabled": assistant.available(condo), "name": site.name, "greeting": site.greeting,
            "mode": m.SystemSettings.load().assistant_mode,
            "max_session_seconds": m.SystemSettings.load().assistant_max_session_seconds,
            "maps": [{"id": x.pk, "name": x.name} for x in maps],
        }).data)


class AssistantSessionMixin:
    def session(self, pk):
        found = m.AssistantSession.objects.filter(pk=pk, kiosk=self.kiosk).first()
        if found is None:
            raise Rejected({"detail": "Unknown conversation."}, status.HTTP_404_NOT_FOUND)
        try:
            assistant.check_session(found)
        except assistant.AssistantError as exc:
            raise Rejected({"detail": str(exc)}, status.HTTP_409_CONFLICT)
        return found


class KioskAssistantStartView(KioskView):
    throttle_classes = [KioskAssistantThrottle]

    @extend_schema(request=None, responses=s.KioskAssistantStartSerializer)
    def post(self, request):
        """Start a conversation. Speech-to-text mode gets the spoken greeting; realtime mode a one-minute
        client secret for the WebRTC connection to OpenAI (the API key stays on the server)."""
        condo = self.kiosk.condominium
        try:
            session = assistant.start_session(self.kiosk)
            body = {"session": session.pk, "mode": session.mode, "greeting": assistant.site_settings(condo).greeting,
                    "greeting_speech": "", "client_secret": ""}
            if session.mode == m.AssistantSession.Mode.REALTIME:
                body["client_secret"] = assistant.realtime_secret(condo)
            else:
                body["greeting_speech"] = assistant.speech_url(condo, body["greeting"])
        except assistant.AssistantError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(s.KioskAssistantStartSerializer(body).data, status=status.HTTP_201_CREATED)


class KioskAssistantTurnView(AssistantSessionMixin, KioskView):
    throttle_classes = [KioskAssistantThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(request=s.KioskAssistantTurnSerializer, responses=s.KioskAssistantReplySerializer)
    def post(self, request, pk):
        """One exchange in speech-to-text mode: what the visitor said (``audio`` or ``text``) and the recent
        ``history`` in; what was heard, the answer, screen actions and a link to the spoken answer out
        (the text comes back first; the speech streams from the link). Nothing is kept."""
        session = self.session(pk)
        body = s.KioskAssistantTurnSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        condo = self.kiosk.condominium
        try:
            heard = data.get("text", "").strip() or (assistant.transcribe(condo, data["audio"]) if data.get("audio") else "")
            if not heard:
                return Response(s.KioskAssistantReplySerializer({"heard": "", "reply": "", "speech": "", "actions": []}).data)
            history = assistant.clean_history(data.get("history") or [])
            text, actions = assistant.reply(condo, [*history, {"role": "user", "content": heard[:assistant.MAX_TEXT]}])
        except assistant.AssistantError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        m.AssistantSession.objects.filter(pk=session.pk).update(turns=session.turns + 1)
        return Response(s.KioskAssistantReplySerializer(
            {"heard": heard, "reply": text, "speech": assistant.speech_url(condo, text), "actions": actions}).data)


def assistant_speech(request, key):
    """The spoken answer behind a link from a turn, streamed as OpenAI makes it. The link is the
    authorisation (random, two minutes), since an <audio> element cannot send the kiosk token."""
    try:
        stream = assistant.speech_stream(key)
    except assistant.AssistantError:
        return HttpResponse(status=503)
    if stream is None:
        return HttpResponse(status=404)
    response = StreamingHttpResponse(stream, content_type="audio/mpeg")
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"  # nginx passes each piece straight on.
    return response


class KioskAssistantEndView(KioskView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request, pk):
        m.AssistantSession.objects.filter(pk=pk, kiosk=self.kiosk, ended_at__isnull=True).update(ended_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


class KioskAssistantMapView(KioskView):
    @extend_schema(responses={(200, "image/*"): None})
    def get(self, request, pk):
        found = m.AssistantMap.objects.filter(pk=pk, condominium=self.kiosk.condominium, is_active=True).first()
        if found is None or not found.image:
            return Response(status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(found.image.open("rb"))
        response["Cache-Control"] = "private, max-age=3600"
        return response
