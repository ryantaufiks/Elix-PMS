from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import amenity_views, auth_views, billing_views, feed_views, kiosk_views, report_views, views

router = DefaultRouter()
router.register("condominiums", views.CondominiumViewSet)
router.register("blocks", views.BlockViewSet)
router.register("units", views.UnitViewSet)
router.register("staff-assignments", views.StaffAssignmentViewSet)
router.register("residencies", views.ResidencyViewSet)
router.register("resident-documents", views.ResidentDocumentViewSet)
router.register("backups", views.BackupViewSet)
router.register("email-logs", views.EmailLogViewSet)
router.register("plans", billing_views.PlanViewSet)
router.register("assistant-modules", views.AssistantModuleViewSet)
router.register("assistant-maps", views.AssistantMapViewSet)
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
router.register("facilities", amenity_views.FacilityViewSet)
router.register("bookings", amenity_views.BookingViewSet)
router.register("parking-permits", amenity_views.ParkingPermitViewSet)
router.register("feedback", amenity_views.FeedbackViewSet)

urlpatterns = [
    path("health/", views.health, name="health"),
    path("auth/token/", auth_views.LoginView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", auth_views.RefreshView.as_view(), name="token-refresh"),
    path("auth/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("system-settings/", views.SystemSettingsView.as_view(), name="system-settings"),
    path("system-settings/test-livekit/", views.test_livekit, name="system-settings-test-livekit"),
    path("system-settings/test-fcm/", views.test_fcm, name="system-settings-test-fcm"),
    path("system-settings/test-email/", views.test_email, name="system-settings-test-email"),
    path("subscriptions/<int:condominium>/", billing_views.SubscriptionView.as_view(), name="subscription"),
    path("modules/", billing_views.ModuleCatalogueView.as_view(), name="module-catalogue"),
    path("usage/", billing_views.UsageReportView.as_view(), name="usage-report"),
    path("assistant-settings/", views.AssistantSettingsView.as_view(), name="assistant-settings"),
    path("assistant-settings/test/", views.AssistantTestView.as_view(), name="assistant-test"),
    path("dashboard/summary/", views.DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("payment-settings/", amenity_views.PaymentSettingsView.as_view(), name="payment-settings"),
    path("payments/hitpay/webhook/", amenity_views.HitPayWebhookView.as_view(), name="hitpay-webhook"),
    path("payments/hitpay/return/", amenity_views.HitPayReturnView.as_view(), name="hitpay-return"),
    path("reports/", report_views.ReportCatalogView.as_view(), name="report-catalog"),
    path("reports/<slug:key>/", report_views.ReportView.as_view(), name="report"),
    path("notifications/", feed_views.NotificationsView.as_view(), name="notifications"),
    path("weather/", feed_views.WeatherView.as_view(), name="weather"),
    path("kiosk/me/", kiosk_views.KioskMeView.as_view(), name="kiosk-me"),
    path("kiosk/assistant/", kiosk_views.KioskAssistantView.as_view(), name="kiosk-assistant"),
    path("kiosk/assistant/sessions/", kiosk_views.KioskAssistantStartView.as_view(), name="kiosk-assistant-start"),
    path("kiosk/assistant/sessions/<int:pk>/turns/", kiosk_views.KioskAssistantTurnView.as_view(), name="kiosk-assistant-turn"),
    path("kiosk/assistant/sessions/<int:pk>/end/", kiosk_views.KioskAssistantEndView.as_view(), name="kiosk-assistant-end"),
    path("kiosk/assistant/speech/<str:key>/", kiosk_views.assistant_speech, name="kiosk-assistant-speech"),
    path("kiosk/assistant/maps/<int:pk>/", kiosk_views.KioskAssistantMapView.as_view(), name="kiosk-assistant-map"),
    path("kiosk/weather/", kiosk_views.KioskWeatherView.as_view(), name="kiosk-weather"),
    path("kiosk/directory/", kiosk_views.DirectoryView.as_view(), name="kiosk-directory"),
    path("kiosk/calls/", kiosk_views.StartCallView.as_view(), name="kiosk-call-start"),
    path("kiosk/calls/<int:pk>/", kiosk_views.KioskCallView.as_view(), name="kiosk-call"),
    path("kiosk/visitors/lookup/", kiosk_views.VisitorLookupView.as_view(), name="kiosk-visitor-lookup"),
    path("kiosk/checkin/lookup/", kiosk_views.QrLookupView.as_view(), name="kiosk-checkin-lookup"),
    path("kiosk/checkin/", kiosk_views.QrCheckInView.as_view(), name="kiosk-checkin"),
    path("kiosk/walk-ins/", kiosk_views.WalkInView.as_view(), name="kiosk-walk-in"),
    path("kiosk/checkout/", kiosk_views.WalkInCheckOutView.as_view(), name="kiosk-checkout"),
    path("kiosk/walk-ins/checkout/", kiosk_views.WalkInCheckOutView.as_view(), name="kiosk-walk-in-checkout"),
    path("public/invitations/<str:token>/", views.visitor_pass, name="visitor-pass"),
    path("public/invitations/<str:token>/qr/", views.visitor_pass_qr, name="visitor-pass-qr"),
    path("kiosk/calls/<int:pk>/hangup/", kiosk_views.KioskHangupView.as_view(), name="kiosk-call-hangup"),
    path("kiosk/calls/<int:pk>/pass/", kiosk_views.KioskCallPassView.as_view(), name="kiosk-call-pass"),
    path("", include(router.urls)),
]
