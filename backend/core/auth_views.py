"""Sign-in and sign-out: rate-limited logins, revocable sessions (refresh-token blacklist)."""
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView


def client_ip(request) -> str:
    """The visitor's address: the gateway replaces X-Forwarded-For with Cloudflare's client IP."""
    return (request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "").split(",")[0].strip()


def over_limit(scope: str, ident: str, limit: int, seconds: int) -> bool:
    """Counts one hit for ``ident`` in a fixed window; True once more than ``limit`` hits were counted."""
    key = f"limit:{scope}:{ident}"
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key) > limit
    except ValueError:  # Expired between add and incr.
        cache.set(key, 1, seconds)
        return False


class LoginIpThrottle(AnonRateThrottle):
    scope = "login"


class LoginUserThrottle(SimpleRateThrottle):
    """Per account, so spreading guesses over many addresses does not help."""

    scope = "login_user"

    def get_cache_key(self, request, view):
        username = str(request.data.get("username", "")).strip().lower()
        return self.cache_format % {"scope": self.scope, "ident": username} if username else None


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginIpThrottle, LoginUserThrottle]


class RefreshView(TokenRefreshView):
    throttle_classes = [LoginIpThrottle]


class LogoutView(TokenBlacklistView):
    """Sign out: the refresh token can no longer be used (the access token expires on its own)."""


def revoke_sessions(user):
    """Sign the user out everywhere, e.g. after a password change or when the account is disabled."""
    for token in OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False):
        BlacklistedToken.objects.get_or_create(token=token)


def rate_limited_admin_login(login_view):
    """Django admin sign-in: at most 10 attempts per minute per address and per username."""

    @wraps(login_view)
    def view(request, *args, **kwargs):
        if request.method == "POST":
            username = request.POST.get("username", "").strip().lower()
            if over_limit("admin-login-ip", client_ip(request), 10, 60) or \
                    (username and over_limit("admin-login-user", username, 10, 60)):
                return HttpResponse("Too many sign-in attempts. Please wait a minute.", status=429, content_type="text/plain")
        return login_view(request, *args, **kwargs)

    return view
