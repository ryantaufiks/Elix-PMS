from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.auth_views import rate_limited_admin_login
from core.lpr import lpr_webhook

admin.site.site_header = "Elix VMS Administration"
admin.site.site_title = "Elix VMS"
admin.site.site_url = "/"  # "View site" opens the dashboard (served by the gateway)
admin.site.login = rate_limited_admin_login(admin.site.login)

urlpatterns = [
    path("v1/admin/", admin.site.urls),
    path("v1/lpr-webhook/", lpr_webhook, name="lpr-webhook"),
    path("v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("v1/", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
