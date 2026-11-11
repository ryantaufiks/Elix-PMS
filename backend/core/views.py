from datetime import timedelta
from io import BytesIO

import qrcode
from django.db import connection
from django.db.models import Count, Q
from django.db.models.functions import ExtractHour
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from . import access, assistant, backups, entitlements, intercom, livekit, mail, privacy, push, relays, visits
from . import visitor_identity as identity
from . import models as m
from . import serializers as s
from .auth_views import client_ip
from .scoping import ADMIN, ALL_STAFF, MANAGEMENT, resident_condo_ids, resident_unit_ids, staff_condo_ids
from .validators import normalize_plate


def _fans_out(model, path):
    """Whether following ``path`` crosses a to-many relation (so one row can match more than once)."""
    for name in path.split("__"):
        if name == "pk":
            return False
        field = model._meta.get_field(name)
        if field.many_to_many or field.one_to_many:
            return True
        if not field.is_relation:
            return False
        model = field.related_model
    return False


def _resolve_pk(source, path):
    """Follow an ORM-style path (``gate__condominium``) from an instance or validated-data dict to a pk."""
    first, *rest = path.split("__")
    value = source.get(first) if isinstance(source, dict) else getattr(source, first, None)
    for attr in rest:
        if value is None:
            return None
        value = getattr(value, attr)
    return getattr(value, "pk", value)


class ScopedViewSetMixin:
    """Restricts rows to the condominiums/units the user belongs to.

    - Staff with a role in ``staff_read_roles`` see every row of their condominium;
      ``staff_write_roles`` may also write.
    - Residents see rows of their own units (``resident_unit_path``) and, if
      ``resident_condo_read``, every row of their condominium. They may write
      rows of their own units when ``resident_writable``.
    - Superusers see and write everything.
    """

    condo_path = "condominium"
    module = None  # Module the site needs for these records (core.entitlements); None: always available.
    limit_key = None  # Plan limit counted when a record is added (core.entitlements.LIMITS).
    setup = False  # Site setup: locked while the site's subscription is suspended.
    staff_read_roles = ALL_STAFF
    staff_write_roles = (ADMIN,)
    resident_unit_path = None
    resident_condo_read = False
    resident_writable = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Asking for one site's records: say plainly when its plan does not include them.
        condo_id = request.query_params.get("condominium")
        if self.module and condo_id and condo_id.isdigit():
            condo = m.Condominium.objects.filter(pk=condo_id).only("modules").first()
            if condo is not None:
                entitlements.require(condo, self.module)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if self.module:
            lookup = "modules__contains" if self.condo_path == "id" else f"{self.condo_path}__modules__contains"
            qs = qs.filter(**{lookup: [self.module]})
        if user.is_superuser:
            return qs
        scope = Q(**{f"{self.condo_path}__in": staff_condo_ids(user, self.staff_read_roles)})
        if self.resident_condo_read:
            scope |= Q(**{f"{self.condo_path}__in": resident_condo_ids(user)})
        if self.resident_unit_path:
            scope |= Q(**{f"{self.resident_unit_path}__in": resident_unit_ids(user)})
        qs = qs.filter(scope)
        # DISTINCT only when a path can repeat rows: over every column (JSON included) it costs a sort of
        # whole rows on every list and count, which is most of the database's work under load.
        paths = [self.condo_path] + ([self.resident_unit_path] if self.resident_unit_path else [])
        return qs.distinct() if any(_fans_out(qs.model, p) for p in paths) else qs

    def check_write(self, source):
        user = self.request.user
        if self.module or self.setup:
            condo = m.Condominium.objects.filter(pk=_resolve_pk(source, self.condo_path)).select_related("subscription").first()
            if condo is not None and self.module:
                entitlements.require(condo, self.module)
            if condo is not None and self.setup and not user.is_superuser and entitlements.setup_locked(condo):
                raise entitlements.SiteSuspended()
        if user.is_superuser:
            return
        if _resolve_pk(source, self.condo_path) in staff_condo_ids(user, self.staff_write_roles):
            return
        if (
            self.resident_writable
            and self.resident_unit_path
            and _resolve_pk(source, self.resident_unit_path) in resident_unit_ids(user)
        ):
            return
        raise PermissionDenied("You do not have permission to modify this record.")


    def check_limit(self, source, adding=1):
        if self.limit_key:
            condo = m.Condominium.objects.filter(pk=_resolve_pk(source, self.condo_path)).first()
            if condo is not None:
                entitlements.check_limit(condo, self.limit_key, adding)


class ScopedModelViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
        self.check_limit(serializer.validated_data)
        serializer.save()

    def perform_update(self, serializer):
        self.check_write(serializer.instance)
        changed = serializer.validated_data.keys()
        paths = [self.condo_path] + ([self.resident_unit_path] if self.resident_unit_path else [])
        if any(path.split("__")[0] in changed for path in paths):
            # Moving a record: the user must also be allowed to write at the destination.
            self.check_write({**{p.split("__")[0]: getattr(serializer.instance, p.split("__")[0]) for p in paths},
                              **serializer.validated_data})
        serializer.save()

    def perform_destroy(self, instance):
        self.check_write(instance)
        instance.delete()


class ScopedReadOnlyViewSet(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    pass


# --- Auth & health -----------------------------------------------------------

class MeView(generics.RetrieveUpdateAPIView):
    """The signed-in user, with their staff roles and residencies."""

    serializer_class = s.MeSerializer

    def get_object(self):
        return m.User.objects.prefetch_related(
            "staff_assignments__condominium", "residencies__unit__block", "residencies__unit__condominium"
        ).get(pk=self.request.user.pk)


@extend_schema(responses={200: OpenApiResponse(description="Service is healthy")})
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})


# --- Tenancy -----------------------------------------------------------------

class CondominiumViewSet(ScopedModelViewSet):
    setup = True
    queryset = m.Condominium.objects.all()
    serializer_class = s.CondominiumSerializer
    condo_path = "id"
    resident_condo_read = True
    search_fields = ["name", "code", "postal_code"]
    filterset_fields = ["is_active"]

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Only the platform administrator can add condominiums.")
        plan = serializer.validated_data.pop("plan", None)
        condo = serializer.save()  # Starts a trial on the default plan (signal); switch to the chosen one.
        sub = m.Subscription.objects.filter(condominium=condo).first()
        if sub is not None:
            if plan is not None and sub.plan_id != plan.pk:
                sub.plan = plan
                sub.save(update_fields=["plan", "updated_at"])
                sub.events.update(summary=f"Trial started on {plan.name} until {sub.trial_ends_on:%d %b %Y}.")
                condo.subscription = sub  # The response shows the chosen plan.
            sub.events.filter(actor=None).update(actor=self.request.user)

    def perform_update(self, serializer):
        serializer.validated_data.pop("plan", None)  # The plan changes on the Subscription, not here.
        if "is_active" in serializer.validated_data and not self.request.user.is_superuser \
                and serializer.validated_data["is_active"] != serializer.instance.is_active:
            raise PermissionDenied("Only the platform administrator can activate or deactivate a condominium.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Only the platform administrator can delete condominiums.")
        instance.delete()


class BlockViewSet(ScopedModelViewSet):
    setup = True
    queryset = m.Block.objects.all()
    serializer_class = s.BlockSerializer
    resident_condo_read = True
    filterset_fields = ["condominium"]
    search_fields = ["name"]


class UnitViewSet(ScopedModelViewSet):
    limit_key = "units"
    setup = True
    queryset = m.Unit.objects.select_related("block")
    serializer_class = s.UnitSerializer
    resident_unit_path = "id"
    filterset_fields = {"condominium": ["exact"], "block": ["exact", "isnull"], "floor": ["exact"], "is_active": ["exact"]}
    search_fields = ["unit_number", "floor", "block__name"]

    @extend_schema(request=s.BulkUnitsSerializer, responses={201: OpenApiResponse(description="{'created': n, 'skipped': n}")})
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Create every unit for a range of floors, e.g. floors 2-15 x units '01-08'. Existing units are skipped."""
        body = s.BulkUnitsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        self.check_write({"condominium": data["condominium"]})
        block = data.get("block")
        existing = set(m.Unit.objects.filter(condominium=data["condominium"], block=block)
                       .values_list("floor", "unit_number"))
        new = [
            m.Unit(condominium=data["condominium"], block=block, floor=str(floor).zfill(2), unit_number=number)
            for floor in range(data["floor_from"], data["floor_to"] + 1)
            for number in data["numbers"]
            if (str(floor).zfill(2), number) not in existing
        ]
        self.check_limit({"condominium": data["condominium"]}, adding=len(new))
        m.Unit.objects.bulk_create(new)
        total = (data["floor_to"] - data["floor_from"] + 1) * len(data["numbers"])
        return Response({"created": len(new), "skipped": total - len(new)}, status=status.HTTP_201_CREATED)


class MembershipViewSet(ScopedModelViewSet):
    """Links a person to a site. Only people already at the site can be linked (new people are added
    through /users/), and the person of a link never changes: otherwise any user ID on the platform
    could be pulled in, with their contact details."""

    def _check_person(self, serializer):
        data = serializer.validated_data
        person = data.get("user")
        if serializer.instance is not None:
            if person is not None and person != serializer.instance.user:
                raise ValidationError({"user": "The person of a membership cannot be changed."})
            return
        if self.request.user.is_superuser:
            return
        condo_id = _resolve_pk(data, self.condo_path)
        known = m.StaffAssignment.objects.filter(user=person, condominium_id=condo_id).exists() or \
            m.Residency.objects.filter(user=person, unit__condominium_id=condo_id).exists()
        if not known:
            raise ValidationError({"user": "Only people already at this site can be linked; add new people as staff or residents."})

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)  # Permission first, so other sites get 403, not hints.
        self._check_person(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self.check_write(serializer.instance)
        self._check_person(serializer)
        super().perform_update(serializer)


class StaffAssignmentViewSet(MembershipViewSet):
    queryset = m.StaffAssignment.objects.select_related("user")
    serializer_class = s.StaffAssignmentSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "role", "user"]

    def check_limit(self, source, adding=1):
        # A person who already has a role at the site is not a new staff account.
        data = source if isinstance(source, dict) else {}
        if not m.StaffAssignment.objects.filter(user=data.get("user"), condominium=data.get("condominium")).exists():
            entitlements.check_limit(data["condominium"], "staff_accounts", adding)


class ResidencyViewSet(MembershipViewSet):
    queryset = m.Residency.objects.select_related("user", "unit__block", "unit__condominium")
    serializer_class = s.ResidencySerializer
    staff_write_roles = MANAGEMENT
    condo_path = "unit__condominium"
    resident_unit_path = "unit"
    filterset_fields = ["unit", "unit__condominium", "resident_type", "is_active", "user"]
    search_fields = ["user__first_name", "user__last_name", "user__username", "unit__unit_number", "unit__floor", "unit__block__name"]


class ResidentDocumentViewSet(ScopedModelViewSet):
    """Documents the management keeps for each resident (ownership, tenancy…). Site admins and staff
    manage them; officers never see them; a resident sees only their own, read-only."""

    queryset = m.ResidentDocument.objects.select_related("residency__user", "residency__unit__block", "uploaded_by")
    serializer_class = s.ResidentDocumentSerializer
    condo_path = "residency__unit__condominium"
    staff_read_roles = MANAGEMENT
    staff_write_roles = MANAGEMENT
    filterset_fields = ["residency", "kind", "residency__unit__condominium"]
    search_fields = ["title", "file_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_superuser:
            return qs
        own = m.ResidentDocument.objects.filter(residency__user=self.request.user, residency__is_active=True)
        return (qs | own).select_related("residency__user", "residency__unit__block", "uploaded_by")

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        old = serializer.instance.file.name if "file" in serializer.validated_data else None
        super().perform_update(serializer)
        if old and old != serializer.instance.file.name:
            serializer.instance.file.storage.delete(old)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiResponse(description="The document")})
    @action(detail=True)
    def download(self, request, pk=None):
        document = self.get_object()
        if not document.file:
            raise ValidationError("This document has no file.")
        response = FileResponse(document.file.open("rb"), as_attachment=True, filename=document.file_name or document.file.name)
        response["Cache-Control"] = "private, no-store"
        return response


class VehicleViewSet(ScopedModelViewSet):
    queryset = m.Vehicle.objects.all()
    serializer_class = s.VehicleSerializer
    staff_write_roles = MANAGEMENT
    resident_unit_path = "unit"
    resident_writable = True
    filterset_fields = ["condominium", "unit", "is_active"]
    search_fields = ["plate_number", "make", "model"]


# --- Devices (site admins only) ----------------------------------------------

class IntegrationAccountViewSet(ScopedModelViewSet):
    setup = True
    queryset = m.IntegrationAccount.objects.all()
    serializer_class = s.IntegrationAccountSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "provider", "is_active"]


class ResidentOpenThrottle(UserRateThrottle):
    scope = "resident_open"


class AccessGateViewSet(ScopedModelViewSet):
    limit_key = "gates"
    setup = True
    queryset = m.AccessGate.objects.all()
    serializer_class = s.AccessGateSerializer
    resident_condo_read = True
    filterset_fields = ["condominium", "gate_type", "direction", "is_active", "resident_remote_open"]
    search_fields = ["name"]

    @extend_schema(request=s.ManualOpenSerializer, responses={202: s.AccessLogSerializer})
    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        """Open the gate now (any site staff). Logged as a manual opening by the caller."""
        gate = self.get_object()
        if not request.user.is_superuser and gate.condominium_id not in staff_condo_ids(request.user, ALL_STAFF):
            raise PermissionDenied("Only site staff can open gates manually.")
        if not gate.is_active:
            return Response({"detail": "Gate is disabled."}, status=status.HTTP_409_CONFLICT)
        body = s.ManualOpenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        log = access.grant(gate, m.AccessLog.Method.MANUAL, actor=request.user, reason=body.validated_data["reason"])
        return Response(s.AccessLogSerializer(log).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses={202: s.AccessLogSerializer})
    @action(detail=True, methods=["post"], throttle_classes=[ResidentOpenThrottle])
    def remote_open(self, request, pk=None):
        """A resident opens the gate from the app (only gates with *Residents can open from the app*)."""
        gate = self.get_object()
        units = m.Unit.objects.filter(pk__in=resident_unit_ids(request.user), condominium_id=gate.condominium_id)
        unit = units.first()
        if unit is None:
            raise PermissionDenied("Only residents of this condominium can open its gates from the app.")
        if not gate.resident_remote_open:
            raise PermissionDenied("This gate cannot be opened from the app.")
        if not gate.is_active:
            return Response({"detail": "Gate is disabled."}, status=status.HTTP_409_CONFLICT)
        log = access.grant(gate, m.AccessLog.Method.APP, actor=request.user, unit=unit, reason="Opened from the resident app")
        return Response(s.AccessLogSerializer(log).data, status=status.HTTP_202_ACCEPTED)


class RelayControllerViewSet(ScopedModelViewSet):
    setup = True
    queryset = m.RelayController.objects.all()
    serializer_class = s.RelayControllerSerializer
    condo_path = "gate__condominium"
    staff_read_roles = (ADMIN,)
    filterset_fields = ["gate", "gate__condominium", "provider", "is_active"]

    def _command(self, name):
        relay = self.get_object()
        self.check_write(relay)
        try:
            result = getattr(relays, name)(relay)
        except relays.RelayError as exc:
            return Response({"ok": False, "via": "", "detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"ok": True, "via": result.via, "detail": result.detail})

    @extend_schema(request=None, responses={200: s.RelayCommandResultSerializer, 502: s.RelayCommandResultSerializer})
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Pulse the relay now (the gate really opens; not written to the access log)."""
        return self._command("pulse")

    @extend_schema(request=None, responses={200: s.RelayCommandResultSerializer, 502: s.RelayCommandResultSerializer})
    @action(detail=True, methods=["post"])
    def check(self, request, pk=None):
        """Ask the device for its current state without switching it."""
        return self._command("status")


class LprCameraViewSet(ScopedModelViewSet):
    module = "lpr"
    limit_key = "lpr_cameras"
    setup = True
    queryset = m.LprCamera.objects.all()
    serializer_class = s.LprCameraSerializer
    condo_path = "gate__condominium"
    staff_read_roles = (ADMIN,)
    filterset_fields = ["gate", "gate__condominium", "direction", "is_active"]
    search_fields = ["name", "device_id"]


class KioskViewSet(ScopedModelViewSet):
    limit_key = "kiosks"
    setup = True
    queryset = m.Kiosk.objects.all()
    serializer_class = s.KioskSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "gate", "is_active"]

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
        self.check_limit(serializer.validated_data)
        kiosk = serializer.save()
        self._raw_token = kiosk.issue_token()
        kiosk.save(update_fields=["token_hint", "token_hash"])

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data["token"] = self._raw_token
        return response

    @extend_schema(request=None, responses={200: OpenApiResponse(description="{'token': '<new device token>'}")})
    @action(detail=True, methods=["post"])
    def regenerate_token(self, request, pk=None):
        """Issue a new device token. The old one stops working; the new one is shown only here."""
        kiosk = self.get_object()
        self.check_write(kiosk)
        raw = kiosk.issue_token()
        kiosk.save(update_fields=["token_hint", "token_hash", "updated_at"])
        return Response({"token": raw})


# --- Visitors & access -------------------------------------------------------

class VisitorViewSet(ScopedModelViewSet):
    """People who identified themselves; their visits are ``/visits/?visitor=<id>``. Security blocks them and
    admins erase them (PDPA) from the visitor list."""

    queryset = m.Visitor.objects.all()
    serializer_class = s.VisitorSerializer
    staff_write_roles = ALL_STAFF
    filterset_fields = ["condominium", "is_blacklisted"]
    search_fields = ["full_name", "phone", "id_partial", "company"]
    ordering_fields = ["last_visit_at", "created_at", "full_name"]

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        """PDPA erasure request: also removes the visitor's photos and details from calls and invitations."""
        if not self.request.user.is_superuser and instance.condominium_id not in staff_condo_ids(self.request.user, (ADMIN,)):
            raise PermissionDenied("Only site admins can erase visitor data.")
        privacy.erase_visitor(instance)


class InvitationViewSet(ScopedModelViewSet):
    queryset = m.Invitation.objects.select_related("host", "unit").prefetch_related("gates")
    serializer_class = s.InvitationSerializer
    staff_write_roles = MANAGEMENT
    resident_unit_path = "unit"
    resident_writable = True
    filterset_fields = ["condominium", "unit", "status", "purpose", "host"]
    search_fields = ["visitor_name", "visitor_phone", "vehicle_plate"]
    ordering_fields = ["valid_from", "valid_until", "created_at"]

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
        serializer.save(host=self.request.user)

    @extend_schema(request=None, responses=s.InvitationSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invitation = self.get_object()
        self.check_write(invitation)
        if invitation.status != m.Invitation.Status.ACTIVE:
            return Response({"detail": "Only active invitations can be cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        invitation.cancel()
        return Response(self.get_serializer(invitation).data)

    @extend_schema(responses={(200, "image/png"): OpenApiResponse(description="QR code PNG")})
    @action(detail=True, methods=["get"])
    def qr(self, request, pk=None):
        """QR code PNG encoding the invitation's share link, for sending to the visitor."""
        invitation = self.get_object()
        buffer = BytesIO()
        qrcode.make(invitation.share_url, box_size=10, border=2).save(buffer)
        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        return response


def _call_error(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)


def _livekit_unavailable():
    return Response({"detail": "Video intercom is not configured on the server."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE)


class IntercomCallViewSet(ScopedReadOnlyViewSet):
    """Calls to the user's units (residents) or condominium (staff), with the resident-side actions."""

    module = "intercom"
    queryset = m.IntercomCall.objects.select_related("unit__block", "kiosk")
    serializer_class = s.IntercomCallSerializer
    resident_unit_path = "unit"
    filterset_fields = ["condominium", "unit", "status", "kiosk"]

    def _handled(self):
        call = self.get_object()
        if not intercom.can_handle(self.request.user, call):
            raise PermissionDenied("You do not take intercom calls for this unit.")
        return call

    @extend_schema(request=None, responses=s.CallWithConnectionSerializer)
    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        """Pick up the call; returns the LiveKit connection for this phone. Only the first answer wins."""
        call = self._handled()
        try:
            call = intercom.answer(call, request.user)
            connection = livekit.connection_info(call.room_name, f"user-{request.user.pk}",
                                                 request.user.get_full_name() or request.user.get_username())
        except intercom.CallError as exc:
            return _call_error(exc)
        except livekit.LiveKitNotConfigured:
            return _livekit_unavailable()
        return Response({"call": s.IntercomCallSerializer(call).data, "livekit": connection})

    @extend_schema(request=None, responses=s.AccessLogSerializer)
    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        """Swipe to unlock: approve the visitor and open the gate at the calling kiosk."""
        call = self._handled()
        try:
            call, log = intercom.unlock(call, request.user)
        except intercom.CallError as exc:
            return _call_error(exc)
        return Response(s.AccessLogSerializer(log).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses=s.IntercomCallSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        call = self._handled()
        try:
            call = intercom.reject(call, request.user)
        except intercom.CallError as exc:
            return _call_error(exc)
        return Response(s.IntercomCallSerializer(call).data)

    @extend_schema(request=None, responses=s.IntercomCallSerializer)
    @action(detail=True, methods=["post"])
    def hangup(self, request, pk=None):
        call = intercom.hang_up(self._handled(), m.IntercomCall.Status.CANCELLED)
        return Response(s.IntercomCallSerializer(call).data)

    @extend_schema(responses={(200, "image/jpeg"): OpenApiResponse(description="Visitor snapshot")})
    @action(detail=True, methods=["get"])
    def snapshot(self, request, pk=None):
        """The kiosk's photo of the visitor, shown before answering. Personal data: never cached."""
        call = self.get_object()
        if not call.visitor_snapshot:
            return Response(status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(call.visitor_snapshot.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response


class VisitViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, ScopedReadOnlyViewSet):
    """Visitors on site and past visits, for security. Every check-in (kiosk walk-in, invitation,
    intercom) appears here; security can also register walk-ins, edit notes and check visitors out.

    ``?state=on_site|checked_out|expired``, ``?date_from=`` / ``?date_to=`` (local dates)."""

    queryset = m.Visit.objects.select_related("unit__block", "kiosk", "gate", "visitor", "created_by", "checked_out_by",
                                              "intercom_call", "entry_log")
    serializer_class = s.VisitSerializer
    resident_unit_path = "unit"
    staff_write_roles = ALL_STAFF
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["condominium", "unit", "purpose", "source", "issued_on", "kiosk", "gate", "visitor"]
    search_fields = ["pass_number", "pin", "visitor_name", "company", "vehicle_plate", "notes"]
    ordering_fields = ["created_at", "pass_number", "checked_out_at"]

    @extend_schema(parameters=[
        OpenApiParameter("state", enum=["on_site", "checked_out", "expired"]),
        OpenApiParameter("date_from", type=str, description="YYYY-MM-DD"),
        OpenApiParameter("date_to", type=str, description="YYYY-MM-DD"),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        now = timezone.now()
        state = params.get("state")
        if state == "on_site":
            qs = qs.filter(checked_out_at__isnull=True, valid_until__gte=now)
        elif state == "checked_out":
            qs = qs.filter(checked_out_at__isnull=False)
        elif state == "expired":
            qs = qs.filter(checked_out_at__isnull=True, valid_until__lt=now)
        if params.get("date_from"):
            qs = qs.filter(issued_on__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(issued_on__lte=params["date_to"])
        return qs

    def _staff_only(self, condominium_id):
        if not self.request.user.is_superuser and condominium_id not in staff_condo_ids(self.request.user, ALL_STAFF):
            raise PermissionDenied("Only security and management can do this.")

    @extend_schema(request=s.StaffVisitCreateSerializer, responses={201: s.VisitSerializer})
    def create(self, request, *args, **kwargs):
        """Register a walk-in at the guardhouse. Print its slip with ``GET …/{id}/slip/``."""
        body = s.StaffVisitCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        unit = data["unit"]
        self._staff_only(unit.condominium_id)
        try:
            phone = identity.normalize_phone(data["visitor_phone"])
            id_partial = identity.normalize_id_partial(data["visitor_id_partial"])
        except identity.InvalidIdentity as exc:
            field = "visitor_phone" if "mobile" in str(exc) else "visitor_id_partial"
            return Response({field: [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        name, company = data["visitor_name"].strip(), data["company"].strip()
        visitor = identity.record_visit(condominium_id=unit.condominium_id, name=name, phone=phone,
                                        id_partial=id_partial, company=company, consent=True)
        if visitor is not None and visitor.is_blacklisted:
            reason = f": {visitor.blacklist_reason}" if visitor.blacklist_reason else ""
            return Response({"detail": f"{visitor.full_name} is blocked{reason}", "blocked": True},
                            status=status.HTTP_403_FORBIDDEN)
        visit = visits.create(unit.condominium_id, unit=unit, purpose=data["purpose"], name=name,
                              source=m.Visit.Source.STAFF, company=company, visitor=visitor,
                              vehicle_plate=normalize_plate(data["vehicle_plate"]), notes=data["notes"].strip(),
                              created_by=request.user, snapshot=data.get("snapshot"))
        return Response(s.VisitSerializer(visit).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        self._staff_only(serializer.instance.condominium_id)
        serializer.save()

    @extend_schema(request=None, responses=s.VisitSerializer)
    @action(detail=True, methods=["post"])
    def check_out(self, request, pk=None):
        """Security checks the visitor out (e.g. they left without scanning their slip)."""
        visit = self.get_object()
        self._staff_only(visit.condominium_id)
        visits.check_out(visit, request.user)
        return Response(s.VisitSerializer(visit).data)

    @extend_schema(request=s.VisitIdsSerializer, responses=s.BulkCheckOutResultSerializer)
    @action(detail=False, methods=["post"])
    def bulk_check_out(self, request):
        """Check out several visitors at once (e.g. everyone still on site at the end of the day)."""
        body = s.VisitIdsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        qs = self.get_queryset().filter(pk__in=body.validated_data["ids"])
        if not request.user.is_superuser:
            qs = qs.filter(condominium__in=staff_condo_ids(request.user, ALL_STAFF))
        return Response({"checked_out": visits.check_out_many(qs, request.user)})

    @extend_schema(responses=s.VisitSlipSerializer)
    @action(detail=True, methods=["get"])
    def slip(self, request, pk=None):
        """The slip to print (pass number, details and the check-out QR)."""
        visit = self.get_object()
        self._staff_only(visit.condominium_id)
        return Response(s.VisitSlipSerializer(visit).data)

    @extend_schema(responses={(200, "image/jpeg"): OpenApiResponse(description="Visitor photo")})
    @action(detail=True, methods=["get"])
    def snapshot(self, request, pk=None):
        """The visitor's photo (kiosk, call or check-in snapshot). Personal data: never cached."""
        photo = self.get_object().photo()
        if photo is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(photo.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response


class PushDeviceViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    """Phones of the signed-in user that receive push notifications. Re-registering a token moves it here."""

    serializer_class = s.PushDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return m.PushDevice.objects.none()
        return m.PushDevice.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, created = m.PushDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={**serializer.validated_data, "user": request.user},
        )
        return Response(self.get_serializer(device).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AccessLogViewSet(ScopedReadOnlyViewSet):
    queryset = m.AccessLog.objects.select_related("gate", "unit__block", "actor", "visitor", "invitation", "intercom_call")
    serializer_class = s.AccessLogSerializer
    resident_unit_path = "unit"
    filterset_fields = {
        "condominium": ["exact"], "gate": ["exact"], "method": ["exact"], "result": ["exact"],
        "unit": ["exact"], "plate_number": ["exact"], "occurred_at": ["gte", "lte"],
    }
    search_fields = ["plate_number", "reason"]

    @extend_schema(responses={(200, "image/jpeg"): OpenApiResponse(description="Camera snapshot")})
    @action(detail=True, methods=["get"])
    def snapshot(self, request, pk=None):
        """Camera picture stored with the event. Personal data: never cached."""
        log = self.get_object()
        if not log.snapshot:
            return Response(status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(log.snapshot.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response


# --- Dashboard ---------------------------------------------------------------

KIOSK_OFFLINE_AFTER = timedelta(minutes=5)
CAMERA_OFFLINE_AFTER = timedelta(hours=24)


class DashboardSummaryView(generics.GenericAPIView):
    """Today's counters and device health for one condominium (staff of that condo only)."""

    serializer_class = s.DashboardSummarySerializer

    @extend_schema(parameters=[OpenApiParameter("condominium", int, required=True)])
    def get(self, request):
        try:
            condo_id = int(request.query_params.get("condominium", ""))
        except ValueError:
            return Response({"condominium": "Required."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.is_superuser and condo_id not in staff_condo_ids(request.user, ALL_STAFF):
            raise PermissionDenied("Only staff of this condominium can see its dashboard.")
        now = timezone.now()
        start_of_day = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        logs = m.AccessLog.objects.filter(condominium_id=condo_id, occurred_at__gte=start_of_day)
        counts = dict(logs.values_list("result").annotate(n=Count("id")))
        relays = m.RelayController.objects.filter(gate__condominium_id=condo_id, is_active=True)
        cameras = m.LprCamera.objects.filter(gate__condominium_id=condo_id, is_active=True)
        kiosks = m.Kiosk.objects.filter(condominium_id=condo_id, is_active=True)
        stale = lambda qs, after: qs.filter(Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - after)).count()
        data = {
            "granted_today": counts.get(m.AccessLog.Result.GRANTED, 0),
            "denied_today": counts.get(m.AccessLog.Result.DENIED, 0),
            "errors_today": counts.get(m.AccessLog.Result.ERROR, 0),
            "invitations_today": m.Invitation.objects.filter(
                condominium_id=condo_id, status=m.Invitation.Status.ACTIVE,
                valid_from__lte=now + timedelta(days=1), valid_until__gte=now).count(),
            "open_calls": m.IntercomCall.objects.filter(
                condominium_id=condo_id, status__in=m.IntercomCall.OPEN_STATUSES, ended_at__isnull=True).count(),
            "relays_total": relays.count(),
            "relays_failing": relays.exclude(last_error="").count(),
            "cameras_total": cameras.count(),
            "cameras_offline": stale(cameras, CAMERA_OFFLINE_AFTER),
            "kiosks_total": kiosks.count(),
            "kiosks_offline": stale(kiosks, KIOSK_OFFLINE_AFTER),
            "lpr_enabled": m.Condominium.objects.filter(pk=condo_id).values_list("lpr_enabled", flat=True).first(),
            "hourly": self._hourly(logs),
            "by_method": dict(logs.values_list("method").annotate(n=Count("id"))),
            "gates": self._gates(condo_id),
        }
        return Response(self.get_serializer(data).data)

    @staticmethod
    def _hourly(logs):
        """24 buckets (local hours) of today's decisions, for the traffic chart."""
        buckets = [{"hour": h, "granted": 0, "denied": 0, "error": 0} for h in range(24)]
        rows = logs.annotate(hour=ExtractHour("occurred_at", tzinfo=timezone.get_current_timezone())) \
            .values_list("hour", "result").annotate(n=Count("id"))
        for hour, result, n in rows:
            buckets[hour][result] = n
        return buckets

    @staticmethod
    def _gates(condo_id):
        gates = m.AccessGate.objects.filter(condominium_id=condo_id).order_by("name").annotate(
            relays_total=Count("relays", filter=Q(relays__is_active=True)),
            relays_failing=Count("relays", filter=Q(relays__is_active=True) & ~Q(relays__last_error="")),
        )
        return [
            {"id": g.id, "name": g.name, "gate_type": g.gate_type, "is_active": g.is_active,
             "relays_total": g.relays_total, "relays_failing": g.relays_failing}
            for g in gates
        ]


# --- People & system ---------------------------------------------------------

class ManagedUserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                         mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """People of the caller's condominiums: site admins manage residents and staff, staff manage residents.

    Only people who belong exclusively to the caller's own condominiums can be changed; anyone also
    attached elsewhere, and superusers, are left to the platform administrator.
    """

    serializer_class = s.ManagedUserSerializer
    filterset_fields = ["is_active"]
    search_fields = ["username", "first_name", "last_name", "email", "phone"]

    def get_queryset(self):
        qs = m.User.objects.prefetch_related("residencies__unit__block", "residencies__unit__condominium", "staff_assignments") \
            .order_by("first_name", "last_name", "username")
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        user = self.request.user
        if not user.is_superuser:
            qs = qs.filter(Q(residencies__unit__condominium__in=staff_condo_ids(user, MANAGEMENT))
                           | Q(staff_assignments__condominium__in=staff_condo_ids(user, (ADMIN,))))
        condo = self.request.query_params.get("condominium")
        if condo:
            qs = qs.filter(Q(residencies__unit__condominium=condo) | Q(staff_assignments__condominium=condo))
        return qs.distinct()

    def _check_manage(self, target):
        user = self.request.user
        if user.is_superuser:
            return
        if target.is_superuser:
            raise PermissionDenied("Platform administrators can only be changed by another platform administrator.")
        homes = set(target.residencies.values_list("unit__condominium_id", flat=True))
        posts = set(target.staff_assignments.values_list("condominium_id", flat=True))
        if posts and not posts <= staff_condo_ids(user, (ADMIN,)):
            raise PermissionDenied("Staff accounts are managed by the site admin; for other sites ask the platform administrator.")
        if not (homes | posts) or not homes <= staff_condo_ids(user, MANAGEMENT):
            raise PermissionDenied("This person also belongs to another condominium; ask the platform administrator.")

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_superuser:
            data = serializer.validated_data
            # Each membership in the request is checked on its own: a resident at one of the caller's sites
            # and a staff role at another site must not pass together.
            allowed = True
            if data.get("residency"):
                allowed &= data["residency"]["unit"].condominium_id in staff_condo_ids(user, MANAGEMENT)
            if data.get("staff"):
                allowed &= data["staff"]["condominium"].pk in staff_condo_ids(user, (ADMIN,))
            if not allowed:
                raise PermissionDenied("You can only add residents to your own sites, and staff only to sites you administer.")
        if serializer.validated_data.get("staff"):
            entitlements.check_limit(serializer.validated_data["staff"]["condominium"], "staff_accounts")
        serializer.save()

    def perform_update(self, serializer):
        self._check_manage(serializer.instance)
        serializer.save()

    @extend_schema(request=s.SetPasswordSerializer, responses={204: None})
    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        target = self.get_object()
        self._check_manage(target)
        body = s.SetPasswordSerializer(data=request.data, context={"user": target})
        body.is_valid(raise_exception=True)
        target.set_password(body.validated_data["password"])
        target.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class IsSuperuser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class SystemSettingsView(generics.RetrieveUpdateAPIView):
    """Server-wide integrations (platform administrator only). Blank values fall back to .env."""

    serializer_class = s.SystemSettingsSerializer
    permission_classes = [IsSuperuser]
    http_method_names = ["get", "patch"]

    def get_object(self):
        return m.SystemSettings.load()


# --- Kiosk AI assistant (site admins) -------------------------------------------------------------------

class AssistantSettingsView(generics.GenericAPIView):
    """The site's kiosk assistant: on/off, name, greeting, languages, guidance and its own optional OpenAI
    key (``?condominium=``). Site admins and platform admins."""

    serializer_class = s.AssistantSettingsSerializer

    def condo(self):
        try:
            condo = m.Condominium.objects.get(pk=self.request.query_params.get("condominium"))
        except (m.Condominium.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"condominium": "Choose the site."})
        if not self.request.user.is_superuser and condo.pk not in staff_condo_ids(self.request.user, (ADMIN,)):
            raise PermissionDenied("Only the site admin manages the assistant.")
        entitlements.require(condo, "ai_concierge")
        return condo

    def get_object(self):
        condo = self.condo()
        return m.AssistantSettings.objects.get_or_create(condominium=condo)[0]

    def get(self, request):
        return Response(self.get_serializer(self.get_object()).data)

    def patch(self, request):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AssistantTestView(AssistantSettingsView):
    @extend_schema(request=s.AssistantTestSerializer, responses=s.AssistantTestSerializer)
    def post(self, request):
        """Ask the assistant a typed question with the saved knowledge (no voice), to check its answers."""
        condo = self.condo()
        body = s.AssistantTestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not assistant.api_key(condo):
            raise ValidationError({"message": "Add an OpenAI API key first (System settings, or this site's own key)."})
        history = assistant.clean_history(body.validated_data.get("history") or [])
        try:
            text, actions = assistant.reply(condo, [*history, {"role": "user", "content": body.validated_data["message"]}])
        except assistant.AssistantError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"message": body.validated_data["message"], "reply": text, "actions": actions})


class AssistantModuleViewSet(ScopedModelViewSet):
    module = "ai_concierge"
    setup = True
    queryset = m.AssistantModule.objects.all()
    serializer_class = s.AssistantModuleSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "is_active"]


class AssistantMapViewSet(ScopedModelViewSet):
    module = "ai_concierge"
    setup = True
    queryset = m.AssistantMap.objects.all()
    serializer_class = s.AssistantMapSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "is_active"]

    def perform_update(self, serializer):
        old = serializer.instance.image.name if "image" in serializer.validated_data else None
        super().perform_update(serializer)
        if old and old != serializer.instance.image.name:
            serializer.instance.image.storage.delete(old)

    @extend_schema(responses={(200, "image/*"): OpenApiResponse(description="Map image")})
    @action(detail=True)
    def image(self, request, pk=None):
        found = self.get_object()
        response = FileResponse(found.image.open("rb"))
        response["Cache-Control"] = "private, max-age=3600"
        return response


class BackupViewSet(mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    """Platform backups and site exports (platform administrator only). Creating one queues it;
    poll the list until it is ``ready``. Every download is recorded."""

    queryset = m.Backup.objects.select_related("condominium", "created_by").prefetch_related("downloads__user")
    serializer_class = s.BackupSerializer
    permission_classes = [IsSuperuser]
    filterset_fields = ["kind", "condominium", "status"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        backup = backups.start(data["kind"], data.get("condominium"), user=request.user)
        if backup is None:
            return Response({"detail": "This backup is already running."}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(backup).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiResponse(description="The archive")})
    @action(detail=True)
    def download(self, request, pk=None):
        backup = self.get_object()
        if backup.status != m.Backup.Status.READY or not backup.file:
            raise ValidationError("This backup is not ready.")
        m.BackupDownload.objects.create(backup=backup, user=request.user, ip=client_ip(request) or None)
        response = FileResponse(backup.file.open("rb"), as_attachment=True, filename=backup.file.name)
        response["Cache-Control"] = "private, no-store"
        return response


@extend_schema(request=None, responses={200: OpenApiResponse(description="{'ok': bool, 'detail': str}")})
@api_view(["POST"])
@permission_classes([IsSuperuser])
def test_livekit(request):
    try:
        rooms = livekit.list_rooms()
    except Exception as exc:
        return Response({"ok": False, "detail": str(exc)})
    return Response({"ok": True, "detail": f"LiveKit OK - {len(rooms)} active room(s)."})


@extend_schema(request=None, responses={200: OpenApiResponse(description="{'ok': bool, 'detail': str}")})
@api_view(["POST"])
@permission_classes([IsSuperuser])
def test_fcm(request):
    if not push.is_enabled():
        return Response({"ok": False, "detail": "No Firebase service account configured."})
    try:
        _, project_id = push._access_token()
    except Exception as exc:
        return Response({"ok": False, "detail": f"{exc.__class__.__name__}: {exc}"})
    return Response({"ok": True, "detail": f"Firebase OK - project {project_id}."})


@extend_schema(request=s.TestEmailSerializer, responses={200: OpenApiResponse(description="{'ok': bool, 'detail': str}")})
@api_view(["POST"])
@permission_classes([IsSuperuser])
def test_email(request):
    body = s.TestEmailSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    to = body.validated_data.get("to") or request.user.email
    if not to:
        return Response({"ok": False, "detail": "Enter an address to send the test to (your account has no email)."})
    ok, detail = mail.send_test(to)
    return Response({"ok": ok, "detail": detail})


class EmailLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Outgoing emails of the last 30 days (platform administrator only)."""

    queryset = m.EmailLog.objects.select_related("condominium")
    serializer_class = s.EmailLogSerializer
    permission_classes = [IsSuperuser]
    filterset_fields = ["status", "condominium", "template"]
    search_fields = ["to", "subject"]


# --- Public visitor pass -----------------------------------------------------

class PassThrottle(AnonRateThrottle):
    scope = "visitor_pass"


def _pass_invitation(token):
    return m.Invitation.objects.select_related("condominium", "unit__block", "host").filter(token=token).first()


@extend_schema(responses=s.InvitationPassSerializer)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PassThrottle])
def visitor_pass(request, token):
    """The visitor's pass behind the share link: validity and where to go. Anyone with the link can see it."""
    invitation = _pass_invitation(token)
    if invitation is None:
        return Response({"detail": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)
    response = Response(s.InvitationPassSerializer(invitation).data)
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(responses={(200, "image/png"): OpenApiResponse(description="QR code PNG")})
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PassThrottle])
def visitor_pass_qr(request, token):
    invitation = _pass_invitation(token)
    if invitation is None:
        return Response(status=status.HTTP_404_NOT_FOUND)
    buffer = BytesIO()
    qrcode.make(invitation.share_url, box_size=10, border=2).save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Cache-Control"] = "private, no-store"
    return response
