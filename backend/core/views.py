from io import BytesIO

import qrcode
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import access
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
    filterset_fields = ["condominium", "block", "floor", "is_active"]
    search_fields = ["unit_number", "floor", "block__name"]


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
    search_fields = ["user__first_name", "user__last_name", "user__username", "unit__unit_number"]


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


class IntercomCallViewSet(ScopedReadOnlyViewSet):
    queryset = m.IntercomCall.objects.all()
    serializer_class = s.IntercomCallSerializer
    resident_unit_path = "unit"
    filterset_fields = ["condominium", "unit", "status", "kiosk"]


class AccessLogViewSet(ScopedReadOnlyViewSet):
    queryset = m.AccessLog.objects.all()
    serializer_class = s.AccessLogSerializer
    resident_unit_path = "unit"
    filterset_fields = {
        "condominium": ["exact"], "gate": ["exact"], "method": ["exact"], "result": ["exact"],
        "unit": ["exact"], "plate_number": ["exact"], "occurred_at": ["gte", "lte"],
    }
    search_fields = ["plate_number", "reason"]
