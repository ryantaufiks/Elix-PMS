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
router.register("access-logs", views.AccessLogViewSet)
router.register("push-devices", views.PushDeviceViewSet, basename="push-device")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("dashboard/summary/", views.DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("kiosk/me/", kiosk_views.KioskMeView.as_view(), name="kiosk-me"),
    path("kiosk/directory/", kiosk_views.DirectoryView.as_view(), name="kiosk-directory"),
    path("kiosk/calls/", kiosk_views.StartCallView.as_view(), name="kiosk-call-start"),
    path("kiosk/calls/<int:pk>/", kiosk_views.KioskCallView.as_view(), name="kiosk-call"),
    path("kiosk/calls/<int:pk>/hangup/", kiosk_views.KioskHangupView.as_view(), name="kiosk-call-hangup"),
    path("", include(router.urls)),
]
