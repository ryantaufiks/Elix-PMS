"""Kiosk tablets authenticate with ``Authorization: Kiosk <device token>`` (issued in Admin/API)."""
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions, permissions

from .models import Kiosk


def kiosk_from_token(raw):
    if not raw or not raw.startswith(Kiosk.TOKEN_PREFIX):
        return None
    return (Kiosk.objects.select_related("condominium", "gate")
            .filter(token_hash=Kiosk.hash_token(raw), is_active=True, condominium__is_active=True).first())


class KioskTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Kiosk"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode(errors="ignore")
        if not header.startswith(f"{self.keyword} "):
            return None
        kiosk = kiosk_from_token(header[len(self.keyword) + 1:].strip())
        if kiosk is None:
            raise exceptions.AuthenticationFailed("Invalid or disabled kiosk token.")
        updates = {"last_seen_at": timezone.now()}
        if version := request.headers.get("X-App-Version", "")[:30]:
            updates["app_version"] = version
        Kiosk.objects.filter(pk=kiosk.pk).update(**updates)
        return AnonymousUser(), kiosk

    def authenticate_header(self, request):
        return self.keyword


class IsKiosk(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, Kiosk)


class KioskTokenScheme(OpenApiAuthenticationExtension):
    target_class = KioskTokenAuthentication
    name = "kioskToken"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "Authorization",
                "description": "`Kiosk <device token>` - issued when the kiosk is created in Admin."}
