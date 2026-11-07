from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect
from django.utils.html import format_html

import json

from . import access, config, livekit, push, relays
from . import models as m


class SecretInput(forms.PasswordInput):
    """Never renders the stored secret; shows whether one is saved instead."""

    def __init__(self, attrs=None):
        super().__init__(attrs={"autocomplete": "new-password", "size": 60, **(attrs or {})}, render_value=False)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if value:
            context["widget"]["attrs"]["placeholder"] = "•••••••• saved - leave blank to keep"
        return context


class SecretFieldsAdminMixin:
    """Renders ``secret_fields`` with SecretInput; a blank submission keeps the stored value."""

    secret_fields = ()
    secret_widgets = {}  # field name -> widget class, default SecretInput

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        secret_fields, secret_widgets = self.secret_fields, self.secret_widgets

        class SecretForm(form_class):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                for name in secret_fields:
                    if name in self.fields:
                        self.fields[name].widget = secret_widgets.get(name, SecretInput)()
                        self.fields[name].required = False

            def clean(self):
                data = super().clean()
                for name in secret_fields:
                    if name in data and not data[name] and self.instance.pk:
                        data[name] = getattr(self.instance, name)
                return data

        return SecretForm


class SecretTextarea(forms.Textarea):
    """Multi-line SecretInput (for pasted JSON keys): never renders the stored value."""

    def __init__(self, attrs=None):
        super().__init__(attrs={"rows": 4, "cols": 80, "autocomplete": "off", **(attrs or {})})

    def format_value(self, value):
        return ""

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if value:
            context["widget"]["attrs"]["placeholder"] = "•••••••• saved - leave blank to keep"
        return context


# --- System ------------------------------------------------------------------

@admin.register(m.SystemSettings)
class SystemSettingsAdmin(SecretFieldsAdminMixin, admin.ModelAdmin):
    """Single settings page; blank fields fall back to .env. Save buttons include connection tests."""

    secret_fields = ("livekit_api_secret", "fcm_service_account_json")
    secret_widgets = {"fcm_service_account_json": SecretTextarea}
    change_form_template = "admin/core/systemsettings/change_form.html"
    readonly_fields = ("livekit_status", "fcm_status")
    fieldsets = (
        ("LiveKit video intercom", {
            "description": "From LiveKit Cloud > Settings > Keys. Blank fields use LIVEKIT_* from .env.",
            "fields": ("livekit_status", "livekit_url", "livekit_api_key", "livekit_api_secret",
                       "livekit_token_ttl_seconds", "intercom_unlock_window_seconds"),
        }),
        ("Push notifications (Firebase)", {
            "description": "Blank uses FCM_SERVICE_ACCOUNT_FILE from .env. Without either, only open apps ring.",
            "fields": ("fcm_status", "fcm_service_account_json"),
        }),
        ("Gate relays & LPR", {"fields": ("relay_http_timeout", "lpr_debounce_seconds")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        m.SystemSettings.load().save()
        return redirect("admin:core_systemsettings_change", 1)

    @admin.display(description="Status")
    def livekit_status(self, obj):
        sources = {name: config.source(name) for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")}
        if not all(sources.values()):
            return "Not configured - kiosk calls are refused until URL, key and secret are set."
        return "Configured (" + ", ".join(f"{k.split('_', 1)[1].lower().replace('_', ' ')}: {v}"
                                          for k, v in sources.items()) + ")"

    @admin.display(description="Status")
    def fcm_status(self, obj):
        if config.source("FCM_SERVICE_ACCOUNT_JSON"):
            return "Configured (admin)"
        return "Configured (.env file)" if push.is_enabled() else "Not configured"

    def response_change(self, request, obj):
        if "_test_livekit" in request.POST:
            try:
                rooms = livekit.list_rooms()
                self.message_user(request, f"LiveKit OK - {len(rooms)} active room(s).", messages.SUCCESS)
            except Exception as exc:
                self.message_user(request, f"LiveKit test failed: {exc}", messages.ERROR)
            return redirect(request.path)
        if "_test_fcm" in request.POST:
            try:
                _, project_id = push._access_token()
                self.message_user(request, f"Firebase OK - project {project_id}.", messages.SUCCESS)
            except Exception as exc:
                self.message_user(request, f"Firebase test failed: {exc.__class__.__name__}: {exc}", messages.ERROR)
            return redirect(request.path)
        return super().response_change(request, obj)


# --- Tenancy -----------------------------------------------------------------

class BlockInline(admin.TabularInline):
    model = m.Block
    extra = 0


@admin.register(m.Condominium)
class CondominiumAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "postal_code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "postal_code")
    prepopulated_fields = {"code": ("name",)}
    inlines = [BlockInline]
    fieldsets = (
        (None, {"fields": ("name", "code", "address", "postal_code", "timezone", "contact_phone", "is_active")}),
        ("Integrations", {"fields": ("lpr_enabled",)}),
        ("Visitor policy", {"fields": (
            "invitation_max_days", "intercom_ring_timeout_seconds", "face_verification_enabled",
            "visitor_data_retention_days",
        )}),
    )


@admin.register(m.Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("__str__", "condominium", "block", "is_active")
    list_filter = ("condominium", "block", "is_active")
    search_fields = ("unit_number", "floor", "block__name")
    list_select_related = ("condominium", "block")


# --- Users -------------------------------------------------------------------

class StaffAssignmentInline(admin.TabularInline):
    model = m.StaffAssignment
    extra = 0


class ResidencyInline(admin.TabularInline):
    model = m.Residency
    extra = 0
    autocomplete_fields = ("unit",)


@admin.register(m.User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "phone", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "phone")
    fieldsets = BaseUserAdmin.fieldsets + (("Contact", {"fields": ("phone",)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("Contact", {"fields": ("email", "phone")}),)
    inlines = [StaffAssignmentInline, ResidencyInline]


@admin.register(m.Residency)
class ResidencyAdmin(admin.ModelAdmin):
    list_display = ("user", "unit", "resident_type", "is_primary_contact", "is_active")
    list_filter = ("unit__condominium", "resident_type", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "unit__unit_number")
    autocomplete_fields = ("user", "unit")


@admin.register(m.Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate_number", "unit", "condominium", "make", "model", "is_active")
    list_filter = ("condominium", "is_active")
    search_fields = ("plate_number", "make", "model")
    autocomplete_fields = ("unit",)


# --- Devices & integrations --------------------------------------------------

@admin.register(m.IntegrationAccount)
class IntegrationAccountAdmin(SecretFieldsAdminMixin, admin.ModelAdmin):
    secret_fields = (
        "ewelink_app_secret", "ewelink_password", "ewelink_access_token", "ewelink_refresh_token", "shelly_auth_key",
    )
    list_display = ("label", "provider", "condominium", "is_active")
    list_filter = ("provider", "condominium", "is_active")
    search_fields = ("label",)
    fieldsets = (
        (None, {"fields": ("condominium", "provider", "label", "is_active", "notes")}),
        ("eWeLink (Sonoff)", {
            "description": "Fill in only when provider is eWeLink. App ID/Secret come from dev.ewelink.cc.",
            "fields": (
                "ewelink_region", "ewelink_app_id", "ewelink_app_secret", "ewelink_account", "ewelink_password",
                "ewelink_access_token", "ewelink_refresh_token", "ewelink_token_expires_at",
            ),
        }),
        ("Shelly Cloud", {
            "description": "Fill in only when provider is Shelly.",
            "fields": ("shelly_server_uri", "shelly_auth_key"),
        }),
    )


class RelayInline(admin.StackedInline):
    model = m.RelayController
    extra = 0
    show_change_link = True
    fields = ("name", "provider", "control_mode", "account", "cloud_device_id", "channel", "is_active")


class CameraInline(admin.TabularInline):
    model = m.LprCamera
    extra = 0
    show_change_link = True
    fields = ("name", "device_id", "direction", "ip_address", "is_active")


@admin.register(m.AccessGate)
class AccessGateAdmin(admin.ModelAdmin):
    list_display = ("name", "condominium", "gate_type", "direction", "is_active")
    list_filter = ("condominium", "gate_type", "is_active")
    search_fields = ("name",)
    inlines = [RelayInline, CameraInline]
    actions = ["open_now"]

    @admin.action(description="Open selected gates now (logged as manual)")
    def open_now(self, request, queryset):
        for gate in queryset.filter(is_active=True):
            access.grant(gate, m.AccessLog.Method.MANUAL, actor=request.user, reason="Opened from Django admin")
            self.message_user(request, f"'{gate}': opening queued - see Access logs for the result.")


@admin.register(m.RelayController)
class RelayControllerAdmin(SecretFieldsAdminMixin, admin.ModelAdmin):
    secret_fields = ("local_password", "local_device_key")
    list_display = ("name", "gate", "provider", "control_mode", "local_ip", "is_active", "last_triggered_at")
    list_filter = ("provider", "control_mode", "gate__condominium", "is_active")
    search_fields = ("name", "cloud_device_id", "local_ip")
    readonly_fields = ("last_triggered_at", "last_error")
    actions = ["test_pulse", "check_status"]
    fieldsets = (
        (None, {"fields": ("gate", "name", "provider", "control_mode", "pulse_seconds", "is_active")}),
        ("Cloud", {"fields": ("account", "cloud_device_id", "channel")}),
        ("Local LAN (optional)", {"fields": ("local_ip", "local_port", "local_username", "local_password", "local_device_key")}),
        ("Status", {"fields": ("last_triggered_at", "last_error")}),
    )

    def _run(self, request, queryset, action, verb):
        for relay in queryset.select_related("account"):
            try:
                result = getattr(relays, action)(relay)
            except relays.RelayError as exc:
                self.message_user(request, f"{relay}: {verb} failed - {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{relay}: {verb} OK via {result.via} - {result.detail}", messages.SUCCESS)

    @admin.action(description="Test: pulse relay now (opens the gate, not logged)")
    def test_pulse(self, request, queryset):
        self._run(request, queryset, "pulse", "pulse")

    @admin.action(description="Check relay status")
    def check_status(self, request, queryset):
        self._run(request, queryset, "status", "status")


class LprCameraForm(forms.ModelForm):
    webhook_password = forms.CharField(
        required=False, widget=SecretInput(),
        help_text="Basic Auth password for the camera's HTTP Post. Leave blank to keep the current one.",
    )

    class Meta:
        model = m.LprCamera
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if not data.get("webhook_password") and not self.instance.webhook_password_hash:
            self.add_error("webhook_password", "Set a webhook password.")
        return data

    def save(self, commit=True):
        if self.cleaned_data.get("webhook_password"):
            self.instance.set_webhook_password(self.cleaned_data["webhook_password"])
        return super().save(commit)


@admin.register(m.LprCamera)
class LprCameraAdmin(SecretFieldsAdminMixin, admin.ModelAdmin):
    form = LprCameraForm
    secret_fields = ("api_password",)
    list_display = ("name", "device_id", "gate", "direction", "ip_address", "is_active", "last_seen_at")
    list_filter = ("gate__condominium", "direction", "is_active")
    search_fields = ("name", "device_id", "ip_address")
    readonly_fields = ("last_seen_at", "last_payload_pretty")
    fieldsets = (
        (None, {"fields": ("gate", "name", "device_id", "direction", "ip_address", "is_active")}),
        ("Webhook", {
            "description": "Camera HTTP Post URL: https://&lt;your domain&gt;/v1/lpr-webhook/ with these credentials.",
            "fields": ("webhook_username", "webhook_password", "plate_field"),
        }),
        ("Camera HTTP API (optional)", {"fields": ("api_username", "api_password")}),
        ("Status", {"fields": ("last_seen_at", "last_payload_pretty")}),
    )

    @admin.display(description="Last payload")
    def last_payload_pretty(self, obj):
        if not obj.last_payload:
            return "Nothing received yet."
        return format_html("<pre style='max-height:400px;overflow:auto'>{}</pre>", json.dumps(obj.last_payload, indent=2))


@admin.register(m.Kiosk)
class KioskAdmin(admin.ModelAdmin):
    list_display = ("name", "condominium", "gate", "token_hint", "is_active", "last_seen_at")
    list_filter = ("condominium", "is_active")
    readonly_fields = ("token_hint", "last_seen_at", "app_version")
    actions = ["regenerate_token"]

    def save_model(self, request, obj, form, change):
        raw = None if change else obj.issue_token()
        super().save_model(request, obj, form, change)
        if raw:
            self._show_token(request, obj, raw)

    @admin.action(description="Regenerate device token")
    def regenerate_token(self, request, queryset):
        for kiosk in queryset:
            raw = kiosk.issue_token()
            kiosk.save(update_fields=["token_hint", "token_hash", "updated_at"])
            self._show_token(request, kiosk, raw)

    def _show_token(self, request, kiosk, raw):
        self.message_user(
            request, f"Device token for '{kiosk}': {raw} - copy it now, it will not be shown again.", messages.WARNING
        )


# --- Visitors & access -------------------------------------------------------

@admin.register(m.Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "condominium", "phone", "id_partial", "is_blacklisted", "created_at")
    list_filter = ("condominium", "is_blacklisted")
    search_fields = ("full_name", "phone", "id_partial")


@admin.register(m.Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("visitor_name", "unit", "purpose", "valid_from", "valid_until", "status", "entry_count")
    list_filter = ("condominium", "status", "purpose")
    search_fields = ("visitor_name", "visitor_phone", "vehicle_plate", "token")
    autocomplete_fields = ("unit", "host", "visitor")
    readonly_fields = ("token", "entry_count", "cancelled_at", "share_url")
    filter_horizontal = ("gates",)


@admin.register(m.IntercomCall)
class IntercomCallAdmin(admin.ModelAdmin):
    list_display = ("created_at", "unit", "kiosk", "status", "answered_by", "decided_by", "ended_at")
    list_filter = ("condominium", "status")
    search_fields = ("room_name", "visitor_name")
    readonly_fields = [f.name for f in m.IntercomCall._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(m.PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "app_version", "last_used_at", "created_at")
    list_filter = ("platform",)
    search_fields = ("user__username",)


@admin.register(m.AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "condominium", "gate", "method", "result", "plate_number", "unit", "reason")
    list_filter = ("condominium", "method", "result", "gate")
    search_fields = ("plate_number", "reason")
    date_hierarchy = "occurred_at"

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
