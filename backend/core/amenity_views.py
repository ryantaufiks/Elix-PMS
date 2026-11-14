"""Resident services: facilities and bookings (with HitPay payment), feedback, and remote gate opening."""
import logging
from datetime import timedelta
from io import BytesIO

import qrcode
from django.db.models import Avg, Count, Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.utils.html import escape
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from . import bookings, entitlements, parking, payments
from . import models as m
from . import serializers as s
from .realtime import broadcast
from .scoping import ADMIN, ALL_STAFF, MANAGEMENT, resident_condo_ids, resident_unit_ids, staff_condo_ids
from .views import ScopedModelViewSet, ScopedReadOnlyViewSet

log = logging.getLogger(__name__)

RETURN_PATH = "/v1/payments/hitpay/return/"
WEBHOOK_PATH = "/v1/payments/hitpay/webhook/"


def is_staff_of(user, condo_id, roles=ALL_STAFF):
    return user.is_superuser or condo_id in staff_condo_ids(user, roles)


def residents_unit(user, unit=None, condo_id=None):
    """The unit a resident acts for: the one given (if theirs) or their only one (in ``condo_id``)."""
    units = m.Unit.objects.filter(pk__in=resident_unit_ids(user))
    if condo_id:
        units = units.filter(condominium_id=condo_id)
    if unit is not None:
        if not units.filter(pk=unit.pk).exists():
            raise PermissionDenied("You can only act for your own unit.")
        return unit
    units = list(units[:2])
    if not units:
        raise PermissionDenied("Only residents can do this.")
    if len(units) > 1:
        raise ValidationError({"unit": "You live in several units: choose one."})
    return units[0]


class FacilityViewSet(ScopedModelViewSet):
    """Bookable facilities. Site admins configure them; residents see the active ones of their condominium."""

    module = "facilities"
    setup = True

    queryset = m.Facility.objects.select_related("condominium")
    serializer_class = s.FacilitySerializer
    resident_condo_read = True
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["condominium", "is_active"]
    search_fields = ["name", "location"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser:  # Residents (not staff) only see what they can book.
            qs = qs.filter(Q(is_active=True) | Q(condominium__in=staff_condo_ids(user, ALL_STAFF)))
        return qs

    def perform_destroy(self, instance):
        self.check_write(instance)
        if instance.bookings.exists():
            raise ValidationError({"detail": "This facility has bookings: deactivate it instead of deleting it."})
        instance.delete()

    @extend_schema(parameters=[OpenApiParameter("date", str, required=True, description="YYYY-MM-DD")],
                   responses=s.AvailabilitySerializer)
    @action(detail=True)
    def availability(self, request, pk=None):
        """The facility's slots on a day, with how many bookings each still takes."""
        facility = self.get_object()
        try:
            day = bookings.to_date(request.query_params.get("date"))
        except bookings.BookingError as exc:
            raise ValidationError({"date": str(exc)})
        first, last = bookings.bookable_days(facility)
        slots = bookings.availability(facility, day)
        if not first <= day <= last:  # Shown, but not bookable yet (or any more).
            slots = [{**slot, "available": False, "left": 0} for slot in slots]
        return Response(s.AvailabilitySerializer({
            "date": day, "open": bool(bookings.slots_of(facility, day)),
            "bookable_from": first, "bookable_until": last, "slots": slots,
        }).data)

    @extend_schema(responses={(200, "image/jpeg"): OpenApiResponse(description="Facility photo")})
    @action(detail=True)
    def photo(self, request, pk=None):
        facility = self.get_object()
        if not facility.image:
            raise NotFound("No photo.")
        response = FileResponse(facility.image.open("rb"))
        response["Cache-Control"] = "private, max-age=3600"
        return response


class BookingViewSet(mixins.CreateModelMixin, ScopedReadOnlyViewSet):
    """Facility bookings. Residents book for their unit and see its bookings; staff see the condominium's.

    ``?upcoming=1`` keeps bookings not yet over; ``?date_from=`` / ``?date_to=`` filter by day (YYYY-MM-DD)."""

    module = "facilities"

    queryset = m.Booking.objects.select_related("facility", "unit__block", "user")
    serializer_class = s.BookingSerializer
    resident_unit_path = "unit"
    filterset_fields = ["condominium", "facility", "unit", "status", "payment_status"]
    search_fields = ["facility__name", "notes", "user__first_name", "user__last_name", "unit__unit_number"]
    ordering_fields = ["starts_at", "created_at"]

    @extend_schema(parameters=[
        OpenApiParameter("upcoming", bool), OpenApiParameter("date_from", str), OpenApiParameter("date_to", str),
        OpenApiParameter("no_show", bool),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("upcoming") in ("1", "true"):
            qs = qs.filter(ends_at__gt=timezone.now()).order_by("starts_at")
        if params.get("date_from"):
            qs = qs.filter(starts_at__date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(starts_at__date__lte=params["date_to"])
        if params.get("no_show") in ("1", "true"):
            qs = qs.filter(no_show_at__isnull=False)
        return qs

    def _urls(self, booking):
        return (self.request.build_absolute_uri(f"{RETURN_PATH}?booking={booking.pk}"),
                self.request.build_absolute_uri(WEBHOOK_PATH))

    def _created(self, booking, code=status.HTTP_201_CREATED):
        url = ""
        if booking.status == m.Booking.Status.PENDING_PAYMENT:
            redirect_url, webhook_url = self._urls(booking)
            try:
                url = bookings.start_payment(booking, redirect_url=redirect_url, webhook_url=webhook_url)
            except bookings.BookingError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        booking.refresh_from_db()
        return Response({"booking": s.BookingSerializer(booking).data, "payment_url": url,
                         "return_url_prefix": self.request.build_absolute_uri(RETURN_PATH)}, status=code)

    @extend_schema(request=s.BookingCreateSerializer, responses={201: s.BookingCreatedSerializer})
    def create(self, request, *args, **kwargs):
        """Book a facility for your unit. Free bookings are confirmed at once; for paid ones open ``payment_url``
        (HitPay) — the booking is confirmed when the payment completes, and released if it is not paid in time."""
        body = s.BookingCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        facility = data["facility"]
        entitlements.require(facility.condominium, "facilities")
        unit = residents_unit(request.user, data.get("unit"), facility.condominium_id)
        try:
            booking = bookings.book(facility, unit, request.user, data["starts_at"], data["slots"],
                                    guests=data["guests"], notes=data["notes"])
        except bookings.BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return self._created(booking)

    def _own_or_staff(self, booking, roles=ALL_STAFF):
        user = self.request.user
        staff = is_staff_of(user, booking.condominium_id, roles)
        if not staff and booking.unit_id not in resident_unit_ids(user):
            raise PermissionDenied()
        return staff

    @extend_schema(methods=["POST"], request=s.GuestPassRequestSerializer, responses=s.GuestPassSerializer)
    @extend_schema(methods=["GET"], responses=s.GuestPassSerializer)
    @action(detail=True, methods=["get", "post"])
    def guests(self, request, pk=None):
        """Invite guests to a confirmed booking: one QR for up to ``guests`` entries (30 minutes before the start
        until the end) to share, and car plates for the barrier. GET shows the current pass (404 if none)."""
        booking = self.get_object()
        self._own_or_staff(booking, MANAGEMENT)
        if request.method == "GET":
            shared = booking.guest_invitations.filter(status=m.Invitation.Status.ACTIVE, vehicle_plate="").first()
            if shared is None:
                raise NotFound("No guest pass yet.")
            cars = list(booking.guest_invitations.filter(status=m.Invitation.Status.ACTIVE).exclude(vehicle_plate="")
                        .values_list("vehicle_plate", flat=True))
        else:
            body = s.GuestPassRequestSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            try:
                shared, car_passes = bookings.guest_pass(booking, request.user, body.validated_data["plates"])
            except bookings.BookingError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
            cars = [c.vehicle_plate for c in car_passes]
        return Response(s.GuestPassSerializer({
            "invitation": shared.pk, "share_url": shared.share_url, "entries": shared.max_entries,
            "entries_left": max(0, shared.max_entries - shared.entry_count), "valid_from": shared.valid_from,
            "valid_until": shared.valid_until, "plates": cars,
        }).data)

    @extend_schema(responses={(200, "image/png"): OpenApiResponse(description="QR code PNG")})
    @action(detail=True, methods=["get"])
    def qr(self, request, pk=None):
        """The booking's check-in QR (PNG), shown in the app and scanned at the kiosk's Facilities."""
        booking = self.get_object()
        buffer = BytesIO()
        qrcode.make(booking.qr_payload, box_size=10, border=2).save(buffer)
        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(request=None, responses=s.BookingCreatedSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """The payment link of a booking still awaiting payment (to resume paying)."""
        booking = self.get_object()
        self._own_or_staff(booking)
        booking = bookings.refresh_payment(booking)
        if booking.status != m.Booking.Status.PENDING_PAYMENT:
            return Response({"detail": f"This booking is {booking.get_status_display().lower()}."}, status=status.HTTP_409_CONFLICT)
        return self._created(booking, status.HTTP_200_OK)

    @extend_schema(request=None, responses=s.BookingSerializer)
    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        """Check the payment with HitPay now (the app calls this when the payment page closes)."""
        booking = self.get_object()
        self._own_or_staff(booking)
        return Response(s.BookingSerializer(bookings.refresh_payment(booking)).data)

    @extend_schema(request=s.CancelSerializer, responses=s.BookingSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a booking: residents up to the facility's cut-off, site admins and staff any time.
        Paid bookings are refunded by the management (then marked refunded)."""
        booking = self.get_object()
        staff = self._own_or_staff(booking, MANAGEMENT)
        body = s.CancelSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            booking = bookings.cancel(booking, request.user, staff=staff, reason=body.validated_data["reason"])
        except bookings.BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(s.BookingSerializer(booking).data)

    @extend_schema(request=None, responses=s.BookingSerializer)
    @action(detail=True, methods=["post"])
    def refunded(self, request, pk=None):
        """Record that the management refunded the payment (done in the HitPay dashboard)."""
        booking = self.get_object()
        if not is_staff_of(request.user, booking.condominium_id, MANAGEMENT):
            raise PermissionDenied("Only site admins and staff can record refunds.")
        try:
            booking = bookings.mark_refunded(booking)
        except bookings.BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(s.BookingSerializer(booking).data)


class PaymentSettingsView(generics.RetrieveUpdateAPIView):
    """The condominium's HitPay account (site admins). Secrets are write-only."""

    serializer_class = s.PaymentSettingsSerializer

    @extend_schema(parameters=[OpenApiParameter("condominium", int, required=True)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(parameters=[OpenApiParameter("condominium", int, required=True)])
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(parameters=[OpenApiParameter("condominium", int, required=True)])
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def get_object(self):
        try:
            condo_id = int(self.request.query_params.get("condominium", ""))
        except ValueError:
            raise ValidationError({"condominium": "Required."})
        if not is_staff_of(self.request.user, condo_id, (ADMIN,)):
            raise PermissionDenied("Only site admins can see payment settings.")
        condo = generics.get_object_or_404(m.Condominium, pk=condo_id)
        entitlements.require(condo, "facilities")
        return m.PaymentSettings.objects.get_or_create(condominium=condo)[0]


class ParkingPermitViewSet(mixins.CreateModelMixin, ScopedReadOnlyViewSet):
    """Season parking bought online. Residents buy for a plate of their unit and see their unit's purchases;
    staff see the condominium's. Paid purchases start or extend the plate's Season parking pass."""

    queryset = m.ParkingPermit.objects.select_related("unit__block", "user")
    serializer_class = s.ParkingPermitSerializer
    resident_unit_path = "unit"
    filterset_fields = ["condominium", "unit", "status"]
    search_fields = ["plate_number", "holder_name", "unit__unit_number"]
    ordering_fields = ["created_at", "ends_on"]

    def _check(self, condo_id, unit_id=None):
        user = self.request.user
        if user.is_superuser or condo_id in staff_condo_ids(user, MANAGEMENT):
            return
        if unit_id is not None and unit_id in resident_unit_ids(user):
            return
        raise PermissionDenied()

    def _created(self, permit, code=status.HTTP_201_CREATED):
        try:
            url = parking.start_payment(
                permit, redirect_url=self.request.build_absolute_uri(f"{RETURN_PATH}?permit={permit.pk}"),
                webhook_url=self.request.build_absolute_uri(WEBHOOK_PATH))
        except parking.ParkingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        permit.refresh_from_db()
        return Response({"permit": s.ParkingPermitSerializer(permit).data, "payment_url": url,
                         "return_url_prefix": self.request.build_absolute_uri(RETURN_PATH)}, status=code)

    @extend_schema(request=s.ParkingPurchaseSerializer, responses={201: s.ParkingPermitCreatedSerializer})
    def create(self, request, *args, **kwargs):
        """Buy season parking for a plate: open ``payment_url`` (HitPay); the pass starts once it is paid."""
        body = s.ParkingPurchaseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        unit = body.validated_data["unit"]
        self._check(unit.condominium_id, unit.pk)
        try:
            permit = parking.buy(unit, request.user, body.validated_data["plate_number"], body.validated_data["months"],
                                 body.validated_data["holder_name"])
        except parking.ParkingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return self._created(permit)

    @extend_schema(request=None, responses=s.ParkingPermitCreatedSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """The payment link of a purchase still awaiting payment."""
        permit = parking.refresh_payment(self.get_object())
        if permit.status != m.ParkingPermit.Status.PENDING_PAYMENT:
            return Response({"detail": f"This purchase is {permit.get_status_display().lower()}."}, status=status.HTTP_409_CONFLICT)
        return self._created(permit, status.HTTP_200_OK)

    @extend_schema(request=None, responses=s.ParkingPermitSerializer)
    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        """Check the payment with HitPay now (the app calls this when the payment page closes)."""
        return Response(s.ParkingPermitSerializer(parking.refresh_payment(self.get_object())).data)

    @extend_schema(parameters=[OpenApiParameter("condominium", int, required=True)], responses=s.ParkingOfferSerializer)
    @action(detail=False)
    def offer(self, request):
        """Whether the site sells season parking, the monthly fee and the lots left."""
        try:
            condo_id = int(request.query_params.get("condominium", ""))
        except ValueError:
            raise ValidationError({"condominium": "Required."})
        user = request.user
        if not (user.is_superuser or condo_id in staff_condo_ids(user) or condo_id in resident_condo_ids(user)):
            raise PermissionDenied()
        condo = generics.get_object_or_404(m.Condominium, pk=condo_id)
        return Response(s.ParkingOfferSerializer(parking.offer(condo)).data)


class HitPayThrottle(AnonRateThrottle):
    scope = "payment_callback"


def _booking_from(data):
    reference = data.get("payment_request_id") or data.get("id") or ""
    booking = m.Booking.objects.filter(payment_reference=reference).first() if reference else None
    number = str(data.get("reference_number") or "")
    if booking is None and number.startswith("booking-") and number[8:].isdigit():
        booking = m.Booking.objects.filter(pk=int(number[8:])).first()
    return booking


class HitPayWebhookView(APIView):
    """HitPay's server-to-server notification. Signed with the condominium's salt; the payment is still
    confirmed only by reading its status from HitPay."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [HitPayThrottle]
    parser_classes = [FormParser, MultiPartParser, JSONParser]

    @extend_schema(request=None, responses={200: OpenApiResponse(description="Received")})
    def post(self, request):
        raw = request.body
        data = request.data.dict() if hasattr(request.data, "dict") else dict(request.data)
        payload = data.get("payment_request") if isinstance(data.get("payment_request"), dict) else data
        booking = _booking_from(payload)
        permit = parking.from_reference(payload) if booking is None else None
        record = booking or permit
        if record is None:
            return Response({"received": True})
        settings = m.PaymentSettings.objects.filter(condominium_id=record.condominium_id).first()
        if settings is None:
            return Response({"received": True})
        signature = request.headers.get("Hitpay-Signature", "")
        signed = (payments.valid_json_webhook(settings, raw, signature) if signature
                  else payments.valid_form_webhook(settings, data))
        if not signed:  # Also when the site has no salt yet: an unsigned webhook is never acted on.
            return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)
        if booking is not None:
            bookings.refresh_payment(booking)
        else:
            parking.refresh_payment(permit)
        return Response({"received": True})


RETURN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0b1b3f;
font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#0b1b3f}}.card{{background:#fff;border-radius:20px;
padding:32px 28px;max-width:360px;margin:16px;text-align:center}}.icon{{font-size:44px;line-height:1;color:{color}}}
h1{{font-size:22px;margin:14px 0 6px}}p{{color:#5b6478;margin:0}}</style></head>
<body><div class="card"><div class="icon">{icon}</div><h1>{title}</h1><p>{detail}</p></div></body></html>"""


class HitPayReturnView(APIView):
    """Where HitPay sends the resident after paying. The app closes its payment page on this URL."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [HitPayThrottle]

    @extend_schema(parameters=[OpenApiParameter("booking", int), OpenApiParameter("permit", int)],
                   responses={(200, "text/html"): OpenApiResponse()})
    def get(self, request):
        if str(request.query_params.get("permit", "")).isdigit():
            return self._permit(int(request.query_params["permit"]))
        booking = m.Booking.objects.filter(pk=request.query_params.get("booking") or 0).first() \
            if str(request.query_params.get("booking", "")).isdigit() else None
        if booking is not None:
            booking = bookings.refresh_payment(booking)
        if booking is not None and booking.status == m.Booking.Status.CONFIRMED:
            page = {"icon": "✓", "color": "#059669", "title": "Booking confirmed",
                    "detail": f"{booking.facility.name}, {timezone.localtime(booking.starts_at):%a %d %b, %H:%M}. "
                              "You can return to the Elix app."}
        elif booking is not None and booking.status == m.Booking.Status.PENDING_PAYMENT:
            page = {"icon": "…", "color": "#d97706", "title": "Payment processing",
                    "detail": "We are waiting for the payment to complete. Your booking will update in the Elix app."}
        else:
            page = {"icon": "✕", "color": "#be123c", "title": "Payment not completed",
                    "detail": "Your booking was not confirmed. Please try again from the Elix app."}
        return self._page(page)

    def _permit(self, pk):
        permit = m.ParkingPermit.objects.filter(pk=pk).first()
        if permit is not None:
            permit = parking.refresh_payment(permit)
        if permit is not None and permit.status == m.ParkingPermit.Status.PAID:
            page = {"icon": "✓", "color": "#059669", "title": "Season parking paid",
                    "detail": f"{permit.plate_number} parks until {permit.ends_on:%d %b %Y}. You can return to the Elix app."}
        elif permit is not None and permit.status == m.ParkingPermit.Status.PENDING_PAYMENT:
            page = {"icon": "…", "color": "#d97706", "title": "Payment processing",
                    "detail": "We are waiting for the payment to complete. Your pass will update in the Elix app."}
        else:
            page = {"icon": "✕", "color": "#be123c", "title": "Payment not completed",
                    "detail": "Season parking was not bought. Please try again from the Elix app."}
        return self._page(page)

    @staticmethod
    def _page(page):
        html = RETURN_PAGE.format(**{k: escape(v) if k != "icon" else v for k, v in page.items()})
        response = HttpResponse(html)
        response["Cache-Control"] = "no-store"
        return response


class FeedbackViewSet(mixins.CreateModelMixin, ScopedReadOnlyViewSet):
    """Residents rate the estate's services; the management replies. Residents see their own feedback."""

    queryset = m.Feedback.objects.select_related("unit__block", "user", "replied_by")
    serializer_class = s.FeedbackSerializer
    filterset_fields = ["condominium", "category", "status", "rating"]
    search_fields = ["comment", "reply", "user__first_name", "user__last_name", "unit__unit_number"]
    ordering_fields = ["created_at", "rating"]

    module = "resident_app"  # Feedback comes from the resident app.

    def get_queryset(self):
        qs = self.queryset.filter(condominium__modules__contains=[self.module])
        user = self.request.user
        if user.is_superuser:
            return qs
        return qs.filter(Q(condominium__in=staff_condo_ids(user, ALL_STAFF)) | Q(user=user))

    @extend_schema(request=s.FeedbackCreateSerializer, responses={201: s.FeedbackSerializer})
    def create(self, request, *args, **kwargs):
        body = s.FeedbackCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        unit = residents_unit(request.user, data.get("unit"))
        recent = m.Feedback.objects.filter(user=request.user, created_at__gte=timezone.now() - timedelta(hours=1)).count()
        if recent >= 5:
            return Response({"detail": "Thank you! You have sent a lot of feedback recently; please try again later."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        feedback = m.Feedback.objects.create(condominium_id=unit.condominium_id, unit=unit, user=request.user,
                                             rating=data["rating"], category=data["category"], comment=data["comment"])
        row = s.FeedbackSerializer(feedback).data
        try:
            broadcast(feedback.condominium_id, None, "feedback", row)  # Staff only: residents are not in condo groups.
        except Exception:  # Redis trouble must not lose the feedback.
            log.exception("Failed to broadcast feedback %s", feedback.pk)
        return Response(row, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.FeedbackReplySerializer, responses=s.FeedbackSerializer)
    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        """Reply to the resident and/or change the status (site admins and staff)."""
        feedback = self.get_object()
        if not is_staff_of(request.user, feedback.condominium_id, MANAGEMENT):
            raise PermissionDenied("Only site admins and staff can reply to feedback.")
        body = s.FeedbackReplySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        fields = ["updated_at"]
        if "reply" in data and data["reply"] != feedback.reply:
            feedback.reply, feedback.replied_by, feedback.replied_at = data["reply"], request.user, timezone.now()
            fields += ["reply", "replied_by", "replied_at"]
            if "status" not in data and feedback.status == m.Feedback.Status.NEW:
                data["status"] = m.Feedback.Status.IN_PROGRESS
        if "status" in data:
            feedback.status = data["status"]
            fields.append("status")
        feedback.save(update_fields=fields)
        return Response(s.FeedbackSerializer(feedback).data)

    @extend_schema(parameters=[OpenApiParameter("condominium", int)], responses=s.FeedbackSummarySerializer)
    @action(detail=False)
    def summary(self, request):
        """Average rating and how many of each star, for the filtered feedback."""
        qs = self.filter_queryset(self.get_queryset())
        stats = qs.aggregate(count=Count("id"), average=Avg("rating"),
                             open=Count("id", filter=~Q(status=m.Feedback.Status.RESOLVED)))
        by_rating = {str(r): 0 for r in range(1, 6)}
        for rating, n in qs.order_by().values_list("rating").annotate(n=Count("id")):
            by_rating[str(rating)] = n
        average = round(stats["average"], 2) if stats["average"] is not None else None
        return Response({"count": stats["count"], "average": average, "by_rating": by_rating, "open": stats["open"]})
