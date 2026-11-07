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
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response

from . import access, intercom, livekit, push, relays
from . import models as m
from . import serializers as s
from .scoping import ADMIN, ALL_STAFF, resident_condo_ids, resident_unit_ids, staff_condo_ids


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
    staff_read_roles = ALL_STAFF
    staff_write_roles = (ADMIN,)
    resident_unit_path = None
    resident_condo_read = False
    resident_writable = False

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        scope = Q(**{f"{self.condo_path}__in": staff_condo_ids(user, self.staff_read_roles)})
        if self.resident_condo_read:
            scope |= Q(**{f"{self.condo_path}__in": resident_condo_ids(user)})
        if self.resident_unit_path:
            scope |= Q(**{f"{self.resident_unit_path}__in": resident_unit_ids(user)})
        return qs.filter(scope).distinct()

    def check_write(self, source):
        user = self.request.user
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


class ScopedModelViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
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
            "staff_assignments__condominium", "residencies__unit"
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
    queryset = m.Condominium.objects.all()
    serializer_class = s.CondominiumSerializer
    condo_path = "id"
    resident_condo_read = True
    search_fields = ["name", "code", "postal_code"]
    filterset_fields = ["is_active"]

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Only the platform administrator can add condominiums.")
        serializer.save()

    def perform_update(self, serializer):
        if "is_active" in serializer.validated_data and not self.request.user.is_superuser \
                and serializer.validated_data["is_active"] != serializer.instance.is_active:
            raise PermissionDenied("Only the platform administrator can activate or deactivate a condominium.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Only the platform administrator can delete condominiums.")
        instance.delete()


class BlockViewSet(ScopedModelViewSet):
    queryset = m.Block.objects.all()
    serializer_class = s.BlockSerializer
    resident_condo_read = True
    filterset_fields = ["condominium"]
    search_fields = ["name"]


class UnitViewSet(ScopedModelViewSet):
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
        m.Unit.objects.bulk_create(new)
        total = (data["floor_to"] - data["floor_from"] + 1) * len(data["numbers"])
        return Response({"created": len(new), "skipped": total - len(new)}, status=status.HTTP_201_CREATED)


class StaffAssignmentViewSet(ScopedModelViewSet):
    queryset = m.StaffAssignment.objects.select_related("user")
    serializer_class = s.StaffAssignmentSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "role", "user"]


class ResidencyViewSet(ScopedModelViewSet):
    queryset = m.Residency.objects.select_related("user", "unit")
    serializer_class = s.ResidencySerializer
    condo_path = "unit__condominium"
    resident_unit_path = "unit"
    filterset_fields = ["unit", "unit__condominium", "resident_type", "is_active", "user"]
    search_fields = ["user__first_name", "user__last_name", "user__username", "unit__unit_number", "unit__floor", "unit__block__name"]


class VehicleViewSet(ScopedModelViewSet):
    queryset = m.Vehicle.objects.all()
    serializer_class = s.VehicleSerializer
    resident_unit_path = "unit"
    resident_writable = True
    filterset_fields = ["condominium", "unit", "is_active"]
    search_fields = ["plate_number", "make", "model"]


# --- Devices (condo admins only) ---------------------------------------------

class IntegrationAccountViewSet(ScopedModelViewSet):
    queryset = m.IntegrationAccount.objects.all()
    serializer_class = s.IntegrationAccountSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "provider", "is_active"]


class AccessGateViewSet(ScopedModelViewSet):
    queryset = m.AccessGate.objects.all()
    serializer_class = s.AccessGateSerializer
    resident_condo_read = True
    filterset_fields = ["condominium", "gate_type", "direction", "is_active"]
    search_fields = ["name"]

    @extend_schema(request=s.ManualOpenSerializer, responses={202: s.AccessLogSerializer})
    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        """Open the gate now (security or condo admin). Logged as a manual opening by the caller."""
        gate = self.get_object()
        if not request.user.is_superuser and gate.condominium_id not in staff_condo_ids(request.user, ALL_STAFF):
            raise PermissionDenied("Only security staff and condo admins can open gates manually.")
        if not gate.is_active:
            return Response({"detail": "Gate is disabled."}, status=status.HTTP_409_CONFLICT)
        body = s.ManualOpenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        log = access.grant(gate, m.AccessLog.Method.MANUAL, actor=request.user, reason=body.validated_data["reason"])
        return Response(s.AccessLogSerializer(log).data, status=status.HTTP_202_ACCEPTED)


class RelayControllerViewSet(ScopedModelViewSet):
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
    queryset = m.LprCamera.objects.all()
    serializer_class = s.LprCameraSerializer
    condo_path = "gate__condominium"
    staff_read_roles = (ADMIN,)
    filterset_fields = ["gate", "gate__condominium", "direction", "is_active"]
    search_fields = ["name", "device_id"]


class KioskViewSet(ScopedModelViewSet):
    queryset = m.Kiosk.objects.all()
    serializer_class = s.KioskSerializer
    staff_read_roles = (ADMIN,)
    filterset_fields = ["condominium", "gate", "is_active"]

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
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
    queryset = m.Visitor.objects.all()
    serializer_class = s.VisitorSerializer
    staff_write_roles = ALL_STAFF
    filterset_fields = ["condominium", "is_blacklisted"]
    search_fields = ["full_name", "phone", "id_partial", "company"]

    def perform_create(self, serializer):
        self.check_write(serializer.validated_data)
        serializer.save(created_by=self.request.user)


class InvitationViewSet(ScopedModelViewSet):
    queryset = m.Invitation.objects.select_related("host", "unit").prefetch_related("gates")
    serializer_class = s.InvitationSerializer
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
    """People (residents and staff) of the condominiums the caller administers.

    Condo admins can manage only people who belong exclusively to their own condominiums;
    anyone also attached elsewhere, and superusers, are left to the platform administrator.
    """

    serializer_class = s.ManagedUserSerializer
    filterset_fields = ["is_active"]
    search_fields = ["username", "first_name", "last_name", "email", "phone"]

    def get_queryset(self):
        qs = m.User.objects.prefetch_related("residencies__unit__block", "staff_assignments") \
            .order_by("first_name", "last_name", "username")
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        user = self.request.user
        if not user.is_superuser:
            condos = staff_condo_ids(user, (ADMIN,))
            qs = qs.filter(Q(residencies__unit__condominium__in=condos) | Q(staff_assignments__condominium__in=condos))
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
        condos = staff_condo_ids(user, (ADMIN,))
        theirs = set(target.residencies.values_list("unit__condominium_id", flat=True)) | \
            set(target.staff_assignments.values_list("condominium_id", flat=True))
        if not theirs or not theirs <= condos:
            raise PermissionDenied("This person also belongs to another condominium; ask the platform administrator.")

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_superuser:
            data = serializer.validated_data
            condo_id = data["residency"]["unit"].condominium_id if data.get("residency") else data["staff"]["condominium"].pk
            if condo_id not in staff_condo_ids(user, (ADMIN,)):
                raise PermissionDenied("You can only add people to condominiums you administer.")
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
