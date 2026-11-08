from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import kiosk_views, views

router = DefaultRouter()
router.register("condominiums", views.CondominiumViewSet)
router.register("blocks", views.BlockViewSet)
router.register("units", views.UnitViewSet)
router.register("staff-assignments", views.StaffAssignmentViewSet)
router.register("residencies", views.ResidencyViewSet)
router.register("vehicles", views.VehicleViewSet)
router.register("integration-accounts", views.IntegrationAccountViewSet)
router.register("gates", views.AccessGateViewSet)
router.register("relays", views.RelayControllerViewSet)
router.register("cameras", views.LprCameraViewSet)
router.register("kiosks", views.KioskViewSet)
router.register("visitors", views.VisitorViewSet)
router.register("invitations", views.InvitationViewSet)
router.register("intercom-calls", views.IntercomCallViewSet)
router.register("visits", views.VisitViewSet)
router.register("access-logs", views.AccessLogViewSet)
router.register("push-devices", views.PushDeviceViewSet, basename="push-device")
router.register("users", views.ManagedUserViewSet, basename="user")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("system-settings/", views.SystemSettingsView.as_view(), name="system-settings"),
    path("system-settings/test-livekit/", views.test_livekit, name="system-settings-test-livekit"),
    path("system-settings/test-fcm/", views.test_fcm, name="system-settings-test-fcm"),
    path("dashboard/summary/", views.DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("kiosk/me/", kiosk_views.KioskMeView.as_view(), name="kiosk-me"),
    path("kiosk/directory/", kiosk_views.DirectoryView.as_view(), name="kiosk-directory"),
    path("kiosk/calls/", kiosk_views.StartCallView.as_view(), name="kiosk-call-start"),
    path("kiosk/calls/<int:pk>/", kiosk_views.KioskCallView.as_view(), name="kiosk-call"),
    path("kiosk/visitors/lookup/", kiosk_views.VisitorLookupView.as_view(), name="kiosk-visitor-lookup"),
    path("kiosk/checkin/lookup/", kiosk_views.QrLookupView.as_view(), name="kiosk-checkin-lookup"),
    path("kiosk/checkin/", kiosk_views.QrCheckInView.as_view(), name="kiosk-checkin"),
    path("kiosk/walk-ins/", kiosk_views.WalkInView.as_view(), name="kiosk-walk-in"),
    path("kiosk/walk-ins/checkout/", kiosk_views.WalkInCheckOutView.as_view(), name="kiosk-walk-in-checkout"),
    path("public/invitations/<str:token>/", views.visitor_pass, name="visitor-pass"),
    path("public/invitations/<str:token>/qr/", views.visitor_pass_qr, name="visitor-pass-qr"),
    path("kiosk/calls/<int:pk>/hangup/", kiosk_views.KioskHangupView.as_view(), name="kiosk-call-hangup"),
    path("", include(router.urls)),
]
