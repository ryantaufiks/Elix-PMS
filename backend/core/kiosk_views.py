"""API for kiosk tablets (``Authorization: Kiosk <token>``)."""
from django.db.models import Exists, OuterRef, Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import access, intercom, livekit
from . import models as m
from . import serializers as s
from .kiosk_auth import IsKiosk, KioskTokenAuthentication


class KioskView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsKiosk]

    @property
    def kiosk(self):
        return self.request.auth


class KioskCallThrottle(SimpleRateThrottle):
    """Limits how fast one kiosk can ring units (prank protection)."""

    scope = "kiosk_call"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": f"kiosk-{request.auth.pk}"}


class KioskMeView(KioskView):
    @extend_schema(responses=s.KioskSelfSerializer)
    def get(self, request):
        """This kiosk's configuration. Also serves as a heartbeat (updates last seen)."""
        return Response(s.KioskSelfSerializer(self.kiosk).data)


class DirectoryView(KioskView, generics.ListAPIView):
    """Units a visitor can call: active units with at least one resident taking calls.

    Resident names are deliberately not exposed. Filter with ``?q=`` (unit, floor or block)."""

    serializer_class = s.DirectoryUnitSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return m.Unit.objects.none()
        takes_calls = m.Residency.objects.filter(unit=OuterRef("pk"), is_active=True, receives_intercom_calls=True)
        qs = (m.Unit.objects.filter(condominium=self.kiosk.condominium_id, is_active=True)
              .filter(Exists(takes_calls)).select_related("block"))
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
        """Ring a unit. Returns the call and this kiosk's LiveKit connection; join the room straight away."""
        body = s.StartCallSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        unit = body.validated_data["unit"]
        if unit.condominium_id != self.kiosk.condominium_id:
            return Response({"unit": ["Unknown unit."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            livekit.ensure_configured()  # Fail before ringing anyone.
            call = intercom.start(self.kiosk, unit, body.validated_data["visitor_name"],
                                  body.validated_data.get("snapshot"))
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
        result = "denied" if problem else ("face_required" if invitation.require_face else "granted")
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
            log = access.handle_qr(self.kiosk, data["code"], data["plate"], data.get("face_photo"))
        except access.FaceRequired:
            invitation = access.find_invitation(self.kiosk.condominium_id, data["code"])
            return Response({"result": "face_required", "reason": "Please look at the camera.", "invitation": _pass(invitation)})
        invitation = log.invitation
        if invitation is not None:
            invitation.refresh_from_db()
        return Response({"result": log.result, "reason": log.reason, "invitation": _pass(invitation)})
