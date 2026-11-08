"""The resident's notification feed and the weather at a site."""
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models as m
from . import notifications, weather
from . import serializers as s
from .scoping import resident_condo_ids, staff_condo_ids


class NotificationsView(APIView):
    """New activity at the resident's units over the last 30 days, newest first (``?page=``, ``?page_size=`` up to 50)."""

    @extend_schema(parameters=[OpenApiParameter("page", int), OpenApiParameter("page_size", int)],
                   responses=s.NotificationPageSerializer)
    def get(self, request):
        try:
            number = max(1, int(request.query_params.get("page", 1)))
            size = min(50, max(1, int(request.query_params.get("page_size", 20))))
        except ValueError:
            raise ValidationError({"page": "Whole numbers only."})
        total, rows = notifications.page(request.user, number, size)
        return Response({"count": total, "results": s.NotificationSerializer(rows, many=True).data})


def weather_response(condo):
    now = weather.current(condo)
    if now is None:
        return Response({"detail": "Weather is unavailable right now."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    response = Response(s.WeatherSerializer(now).data)
    response["Cache-Control"] = "private, max-age=300"
    return response


class WeatherView(APIView):
    """Temperature, humidity and the 2-hour outlook at a site (NEA via data.gov.sg), for its staff and residents."""

    @extend_schema(parameters=[OpenApiParameter("condominium", int, required=True)],
                   responses={200: s.WeatherSerializer, 503: OpenApiResponse(description="data.gov.sg unreachable")})
    def get(self, request):
        try:
            condo_id = int(request.query_params.get("condominium", ""))
        except ValueError:
            raise ValidationError({"condominium": "Required."})
        user = request.user
        if not (user.is_superuser or condo_id in staff_condo_ids(user) or condo_id in resident_condo_ids(user)):
            raise PermissionDenied()
        condo = m.Condominium.objects.filter(pk=condo_id).first()
        if condo is None:
            raise PermissionDenied()
        return weather_response(condo)
