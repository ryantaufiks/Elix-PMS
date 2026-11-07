from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

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

urlpatterns = [
    path("health/", views.health, name="health"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
