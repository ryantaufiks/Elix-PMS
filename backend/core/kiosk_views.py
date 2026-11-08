"""API for kiosk tablets (``Authorization: Kiosk <token>``)."""
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import access, intercom, livekit, walk_ins
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


class KioskMeView(KioskView):
    @extend_schema(responses=s.KioskSelfSerializer)
    def get(self, request):
        """This kiosk's configuration. Also serves as a heartbeat (updates last seen)."""
        return Response(s.KioskSelfSerializer(self.kiosk).data)


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
        """Ring a unit. Returns the call and this kiosk's LiveKit connection; join the room straight away."""
        body = s.StartCallSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        unit = data["unit"]
        condo = self.kiosk.condominium
        name, visitor, consented = self.visitor_details(
            data, unit, details=condo.kiosk_visitor_form, photo=condo.kiosk_photo_required,
            method=m.AccessLog.Method.INTERCOM, blocked_reason="Blocked visitor tried to call a unit")
        try:
            livekit.ensure_configured()  # Fail before ringing anyone.
            call = intercom.start(self.kiosk, unit, name,
                                  data.get("snapshot") if consented else None, visitor=visitor,
                                  purpose=data["purpose"], company=data["company"].strip())
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

    @extend_schema(request=s.WalkInRegisterSerializer, responses={201: s.WalkInSlipSerializer})
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
        walk_in = walk_ins.issue(self.kiosk, data["unit"], data["purpose"], name, company=data["company"].strip(),
                                 visitor=visitor, snapshot=data.get("snapshot"))
        return Response(s.WalkInSlipSerializer(walk_in).data, status=status.HTTP_201_CREATED)


class WalkInCheckOutView(KioskView):
    throttle_classes = [KioskCheckInThrottle]

    @extend_schema(request=s.QrCodeSerializer, responses=s.WalkInCheckOutResultSerializer)
    def post(self, request):
        """Check a walk-in visitor out with the QR on their slip."""
        body = s.QrCodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            walk_in = walk_ins.find(self.kiosk.condominium_id, body.validated_data["code"], lock=True)
            if walk_in is None:
                return Response({"detail": "Unknown pass."}, status=status.HTTP_404_NOT_FOUND)
            done = walk_ins.check_out(walk_in)
        return Response({"result": "checked_out" if done else "already_checked_out",
                         "walk_in": s.WalkInSlipSerializer(walk_in).data})
