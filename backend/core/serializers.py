from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from . import models as m


class ModelCleanSerializer(serializers.ModelSerializer):
    """Runs the model's clean() so API writes obey the same rules as the admin.

    ``secret_fields`` are write-only; responses carry ``has_<field>`` instead,
    and sending a blank value on update keeps the stored secret.
    """

    secret_fields = ()

    def get_extra_kwargs(self):
        extra = super().get_extra_kwargs()
        for name in self.secret_fields:
            extra.setdefault(name, {}).update(write_only=True, required=False, allow_blank=True)
        return extra

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for name in self.secret_fields:
            data[f"has_{name}"] = bool(getattr(instance, name))
        return data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None:
            for name in self.secret_fields:
                if attrs.get(name) == "":
                    attrs.pop(name)

        model = self.Meta.model
        concrete = {f.name for f in model._meta.concrete_fields}
        candidate = model(**{f.attname: getattr(self.instance, f.attname) for f in model._meta.concrete_fields}) \
            if self.instance is not None else model()
        for key, value in attrs.items():
            if key in concrete:
                setattr(candidate, key, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
        # clean() may normalise or derive values (plates, condominium from unit).
        for key in (concrete & set(attrs)) | self.derived_fields:
            if getattr(candidate, model._meta.get_field(key).attname) is not None:
                attrs[key] = getattr(candidate, key)
        return attrs

    derived_fields = set()


# --- Tenancy -----------------------------------------------------------------

class CondominiumSerializer(ModelCleanSerializer):
    class Meta:
        model = m.Condominium
        fields = [
            "id", "name", "code", "address", "postal_code", "timezone", "contact_phone", "is_active", "lpr_enabled",
            "invitation_max_days", "intercom_ring_timeout_seconds", "face_verification_enabled",
            "visitor_data_retention_days", "kiosk_visitor_form", "kiosk_photo_required", "visitor_privacy_notice",
            "created_at", "updated_at",
        ]


class BlockSerializer(ModelCleanSerializer):
    class Meta:
        model = m.Block
        fields = ["id", "condominium", "name"]


class UnitSerializer(ModelCleanSerializer):
    label = serializers.CharField(read_only=True)
    display_name = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = m.Unit
        fields = ["id", "condominium", "block", "floor", "unit_number", "label", "display_name", "is_active"]


# --- Users -------------------------------------------------------------------

class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.User
        fields = ["id", "username", "first_name", "last_name", "email", "phone"]


class StaffAssignmentSerializer(ModelCleanSerializer):
    user_detail = UserSummarySerializer(source="user", read_only=True)

    class Meta:
        model = m.StaffAssignment
        fields = ["id", "user", "user_detail", "condominium", "role", "created_at"]


class ResidencySerializer(ModelCleanSerializer):
    user_detail = UserSummarySerializer(source="user", read_only=True)
    condominium = serializers.IntegerField(source="unit.condominium_id", read_only=True)
    unit_display = serializers.CharField(source="unit.__str__", read_only=True)

    class Meta:
        model = m.Residency
        fields = [
            "id", "user", "user_detail", "unit", "unit_display", "condominium", "resident_type", "is_primary_contact",
            "receives_intercom_calls", "start_date", "end_date", "is_active",
        ]


class MeSerializer(serializers.ModelSerializer):
    staff_assignments = StaffAssignmentSerializer(many=True, read_only=True)
    residencies = ResidencySerializer(many=True, read_only=True)

    class Meta:
        model = m.User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone", "is_superuser",
            "staff_assignments", "residencies",
        ]
        read_only_fields = ["username", "is_superuser"]


class VehicleSerializer(ModelCleanSerializer):
    derived_fields = {"condominium"}
    unit_display = serializers.CharField(source="unit.__str__", read_only=True)

    class Meta:
        model = m.Vehicle
        fields = ["id", "condominium", "unit", "unit_display", "plate_number", "make", "model", "colour", "is_active", "notes"]
        read_only_fields = ["condominium"]


# --- Devices -----------------------------------------------------------------

class IntegrationAccountSerializer(ModelCleanSerializer):
    secret_fields = (
        "ewelink_app_secret", "ewelink_password", "ewelink_access_token", "ewelink_refresh_token", "shelly_auth_key",
    )

    class Meta:
        model = m.IntegrationAccount
        fields = [
            "id", "condominium", "provider", "label", "is_active", "notes",
            "ewelink_region", "ewelink_app_id", "ewelink_app_secret", "ewelink_account", "ewelink_password",
            "ewelink_access_token", "ewelink_refresh_token", "ewelink_token_expires_at",
            "shelly_server_uri", "shelly_auth_key",
        ]


class AccessGateSerializer(ModelCleanSerializer):
    class Meta:
        model = m.AccessGate
        fields = [
            "id", "condominium", "name", "gate_type", "direction", "is_active",
            "lpr_auto_open_residents", "lpr_auto_open_invited",
        ]


class RelayControllerSerializer(ModelCleanSerializer):
    secret_fields = ("local_password", "local_device_key")

    class Meta:
        model = m.RelayController
        fields = [
            "id", "gate", "name", "provider", "control_mode", "is_active", "account", "cloud_device_id", "channel",
            "local_ip", "local_port", "local_username", "local_password", "local_device_key", "pulse_seconds",
            "last_triggered_at", "last_error",
        ]
        read_only_fields = ["last_triggered_at", "last_error"]


class LprCameraSerializer(ModelCleanSerializer):
    secret_fields = ("api_password",)
    webhook_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    webhook_url = serializers.SerializerMethodField()
    has_webhook_password = serializers.SerializerMethodField()

    class Meta:
        model = m.LprCamera
        fields = [
            "id", "gate", "name", "device_id", "direction", "ip_address", "is_active",
            "webhook_username", "webhook_password", "has_webhook_password", "webhook_url", "plate_field",
            "api_username", "api_password", "last_seen_at", "last_payload",
        ]
        read_only_fields = ["last_seen_at", "last_payload"]

    def get_webhook_url(self, obj) -> str:
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/v1/lpr-webhook/"

    def get_has_webhook_password(self, obj) -> bool:
        return bool(obj.webhook_password_hash)

    def validate(self, attrs):
        if self.instance is None and not attrs.get("webhook_password"):
            raise serializers.ValidationError({"webhook_password": "Required when adding a camera."})
        return super().validate(attrs)

    def _apply_password(self, instance, password):
        if password:
            instance.set_webhook_password(password)
            instance.save(update_fields=["webhook_password_hash", "updated_at"])
        return instance

    def create(self, validated_data):
        password = validated_data.pop("webhook_password", "")
        return self._apply_password(super().create(validated_data), password)

    def update(self, instance, validated_data):
        password = validated_data.pop("webhook_password", "")
        return self._apply_password(super().update(instance, validated_data), password)


class KioskSerializer(ModelCleanSerializer):
    class Meta:
        model = m.Kiosk
        fields = ["id", "condominium", "gate", "name", "is_active", "token_hint", "last_seen_at", "app_version"]
        read_only_fields = ["token_hint", "last_seen_at", "app_version"]


# --- Visitors & access -------------------------------------------------------

class VisitorSerializer(ModelCleanSerializer):
    class Meta:
        model = m.Visitor
        fields = [
            "id", "condominium", "full_name", "phone", "id_partial", "company", "face_consent_at", "last_visit_at",
            "is_blacklisted", "blacklist_reason", "created_by", "created_at",
        ]
        read_only_fields = ["created_by", "face_consent_at", "last_visit_at"]


class InvitationSerializer(ModelCleanSerializer):
    derived_fields = {"condominium", "vehicle_plate"}
    share_url = serializers.CharField(read_only=True)
    unit_display = serializers.CharField(source="unit.__str__", read_only=True)
    host_detail = UserSummarySerializer(source="host", read_only=True)

    class Meta:
        model = m.Invitation
        fields = [
            "id", "condominium", "unit", "unit_display", "host", "host_detail", "visitor", "visitor_name", "visitor_phone",
            "purpose", "valid_from", "valid_until", "max_entries", "entry_count", "vehicle_plate", "require_face",
            "gates", "status", "notes", "share_url", "cancelled_at", "created_at",
        ]
        read_only_fields = ["condominium", "host", "entry_count", "status", "cancelled_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        condo_id = attrs.get("condominium").pk if attrs.get("condominium") else self.instance.condominium_id
        for gate in attrs.get("gates", []):
            if gate.condominium_id != condo_id:
                raise serializers.ValidationError({"gates": f"Gate '{gate}' belongs to a different condominium."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        return super().create(validated_data)


class ManualOpenSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class IntercomCallSerializer(serializers.ModelSerializer):
    unit_display = serializers.CharField(source="unit.__str__", read_only=True)
    kiosk_name = serializers.CharField(source="kiosk.name", read_only=True, default="")
    is_open = serializers.BooleanField(read_only=True)
    has_snapshot = serializers.SerializerMethodField()
    visitor_phone = serializers.SerializerMethodField()

    class Meta:
        model = m.IntercomCall
        fields = [
            "id", "condominium", "unit", "unit_display", "kiosk", "kiosk_name", "gate", "status", "is_open",
            "visitor_name", "visitor_purpose", "visitor_company", "visitor_phone", "has_snapshot", "answered_by", "answered_at", "decided_by", "decided_at", "ended_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_has_snapshot(self, obj) -> bool:
        return bool(obj.visitor_snapshot)

    def get_visitor_phone(self, obj) -> str:
        return str(obj.visitor.phone) if obj.visitor and obj.visitor.phone else ""


class LiveKitConnectionSerializer(serializers.Serializer):
    url = serializers.CharField()
    room = serializers.CharField()
    token = serializers.CharField()


class CallWithConnectionSerializer(serializers.Serializer):
    call = IntercomCallSerializer()
    livekit = LiveKitConnectionSerializer()


class StartCallSerializer(serializers.Serializer):
    unit = serializers.PrimaryKeyRelatedField(queryset=m.Unit.objects.filter(is_active=True))
    visitor_ref = serializers.CharField(required=False, allow_blank=True, default="",
                                        help_text="From /kiosk/visitors/lookup/ for a returning visitor.")
    visitor_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    visitor_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    visitor_id_partial = serializers.CharField(max_length=8, required=False, allow_blank=True, default="",
                                               help_text="Last 3 digits and letter of the NRIC/FIN only.")
    purpose = serializers.ChoiceField(choices=m.VisitPurpose.choices, required=False, allow_blank=True, default="")
    company = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    consent = serializers.BooleanField(required=False, default=False,
                                       help_text="The visitor accepted the privacy notice.")
    snapshot = serializers.ImageField(required=False)


class VisitorLookupSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    id_partial = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")


class VisitorLookupResultSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    blocked = serializers.BooleanField()
    ref = serializers.CharField(allow_blank=True)
    masked_name = serializers.CharField(allow_blank=True)
    company = serializers.CharField(allow_blank=True)
    purpose = serializers.CharField(allow_blank=True)


class DirectoryUnitSerializer(serializers.ModelSerializer):
    block = serializers.CharField(source="block.name", default="")
    label = serializers.CharField(read_only=True)

    class Meta:
        model = m.Unit
        fields = ["id", "block", "floor", "unit_number", "label"]


class KioskSelfSerializer(serializers.ModelSerializer):
    condominium_name = serializers.CharField(source="condominium.name")
    gate_name = serializers.CharField(source="gate.name", default="")
    ring_timeout_seconds = serializers.IntegerField(source="condominium.intercom_ring_timeout_seconds")
    visitor_form = serializers.BooleanField(source="condominium.kiosk_visitor_form")
    photo_required = serializers.BooleanField(source="condominium.kiosk_photo_required")
    privacy_notice = serializers.CharField(source="condominium.privacy_notice")

    class Meta:
        model = m.Kiosk
        fields = ["id", "name", "condominium", "condominium_name", "gate", "gate_name", "ring_timeout_seconds",
                  "visitor_form", "photo_required", "privacy_notice"]


class PushDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.PushDevice
        fields = ["id", "platform", "token", "app_version", "created_at", "last_used_at"]
        read_only_fields = ["created_at", "last_used_at"]
        extra_kwargs = {"token": {"validators": []}}


class AccessLogSerializer(serializers.ModelSerializer):
    gate_name = serializers.CharField(source="gate.name", read_only=True, default="")
    unit_display = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()
    visitor_name = serializers.SerializerMethodField()
    has_snapshot = serializers.SerializerMethodField()

    class Meta:
        model = m.AccessLog
        fields = [
            "id", "condominium", "gate", "gate_name", "occurred_at", "method", "result", "reason", "plate_number",
            "unit", "unit_display", "vehicle", "invitation", "visitor", "visitor_name", "intercom_call", "camera",
            "relay", "actor", "actor_name", "has_snapshot",
        ]
        read_only_fields = fields

    def get_unit_display(self, obj) -> str:
        # Not source="unit.__str__": None has __str__ too, so the default would never apply.
        return str(obj.unit) if obj.unit else ""

    def get_actor_name(self, obj) -> str:
        return (obj.actor.get_full_name() or obj.actor.get_username()) if obj.actor else ""

    def get_visitor_name(self, obj) -> str:
        for source in (obj.visitor and obj.visitor.full_name, obj.invitation and obj.invitation.visitor_name,
                       obj.intercom_call and obj.intercom_call.visitor_name):
            if source:
                return source
        return ""

    def get_has_snapshot(self, obj) -> bool:
        return bool(obj.snapshot)


class HourlyTrafficSerializer(serializers.Serializer):
    hour = serializers.IntegerField()
    granted = serializers.IntegerField()
    denied = serializers.IntegerField()
    error = serializers.IntegerField()


class GateHealthSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    gate_type = serializers.CharField()
    is_active = serializers.BooleanField()
    relays_total = serializers.IntegerField()
    relays_failing = serializers.IntegerField()


class DashboardSummarySerializer(serializers.Serializer):
    granted_today = serializers.IntegerField()
    denied_today = serializers.IntegerField()
    errors_today = serializers.IntegerField()
    invitations_today = serializers.IntegerField()
    open_calls = serializers.IntegerField()
    relays_total = serializers.IntegerField()
    relays_failing = serializers.IntegerField()
    cameras_total = serializers.IntegerField()
    cameras_offline = serializers.IntegerField()
    kiosks_total = serializers.IntegerField()
    kiosks_offline = serializers.IntegerField()
    lpr_enabled = serializers.BooleanField(allow_null=True)
    hourly = HourlyTrafficSerializer(many=True)
    by_method = serializers.DictField(child=serializers.IntegerField())
    gates = GateHealthSerializer(many=True)


# --- People management -------------------------------------------------------

class NewResidencySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Residency
        fields = ["unit", "resident_type", "is_primary_contact", "receives_intercom_calls"]


class NewStaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.StaffAssignment
        fields = ["condominium", "role"]


class ManagedUserSerializer(serializers.ModelSerializer):
    """A person managed from the dashboard. On create, attach them to a unit (``residency``) or a
    condominium (``staff``) in the same request so the new account is never orphaned."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8,
                                     style={"input_type": "password"})
    residency = NewResidencySerializer(write_only=True, required=False)
    staff = NewStaffSerializer(write_only=True, required=False)
    residencies = ResidencySerializer(many=True, read_only=True)
    staff_assignments = StaffAssignmentSerializer(many=True, read_only=True)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = m.User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone", "is_active", "is_superuser", "last_login",
            "date_joined", "password", "has_password", "residency", "staff", "residencies", "staff_assignments",
        ]
        read_only_fields = ["is_superuser", "last_login", "date_joined"]

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()

    def validate_password(self, value):
        if value:
            from django.contrib.auth.password_validation import validate_password
            try:
                validate_password(value, self.instance)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("residency") and not attrs.get("staff") \
                and not self.context["request"].user.is_superuser:
            raise serializers.ValidationError("Attach the person to a unit (resident) or to the condominium (staff).")
        if self.instance is not None and ("residency" in attrs or "staff" in attrs):
            raise serializers.ValidationError("Use the residencies and staff-assignments endpoints to change memberships.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        residency = validated_data.pop("residency", None)
        staff = validated_data.pop("staff", None)
        password = validated_data.pop("password", "")
        user = m.User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if residency:
            m.Residency.objects.create(user=user, **residency)
        if staff:
            m.StaffAssignment.objects.create(user=user, **staff)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, style={"input_type": "password"})

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(value, self.context.get("user"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value


class SystemSettingsSerializer(ModelCleanSerializer):
    secret_fields = ("livekit_api_secret", "fcm_service_account_json")
    livekit_configured = serializers.SerializerMethodField()
    fcm_configured = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()

    class Meta:
        model = m.SystemSettings
        fields = [
            "livekit_url", "livekit_api_key", "livekit_api_secret", "livekit_token_ttl_seconds",
            "intercom_unlock_window_seconds", "fcm_service_account_json", "relay_http_timeout",
            "lpr_debounce_seconds", "livekit_configured", "fcm_configured", "sources", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def get_livekit_configured(self, obj) -> bool:
        from . import config
        return all(config.source(n) for n in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))

    def get_fcm_configured(self, obj) -> bool:
        from . import push
        return push.is_enabled()

    def get_sources(self, obj) -> dict:
        """Where each value currently comes from: 'admin', '.env' or '' (unset)."""
        from . import config
        return {field: config.source(name) for name, field in config.FIELDS.items()}


class BulkUnitsSerializer(serializers.Serializer):
    condominium = serializers.PrimaryKeyRelatedField(queryset=m.Condominium.objects.all())
    block = serializers.PrimaryKeyRelatedField(queryset=m.Block.objects.all(), required=False, allow_null=True)
    floor_from = serializers.IntegerField(min_value=1, max_value=99)
    floor_to = serializers.IntegerField(min_value=1, max_value=99)
    units = serializers.CharField(help_text="Unit numbers on every floor: '01-08' and/or '01,02,05'.")

    def validate(self, attrs):
        if attrs["floor_to"] < attrs["floor_from"]:
            raise serializers.ValidationError({"floor_to": "Must be at or above the first floor."})
        if attrs.get("block") and attrs["block"].condominium_id != attrs["condominium"].pk:
            raise serializers.ValidationError({"block": "Block belongs to a different condominium."})
        numbers = []
        for part in attrs["units"].replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                start, _, end = part.partition("-")
                if not (start.isdigit() and end.isdigit()) or int(end) < int(start):
                    raise serializers.ValidationError({"units": f"Bad range '{part}'."})
                width = max(len(start), 2)
                numbers += [str(n).zfill(width) for n in range(int(start), int(end) + 1)]
            elif part.isalnum():
                numbers.append(part)
            else:
                raise serializers.ValidationError({"units": f"Bad unit number '{part}'."})
        numbers = list(dict.fromkeys(numbers))
        if not numbers:
            raise serializers.ValidationError({"units": "Give at least one unit number."})
        if len(numbers) * (attrs["floor_to"] - attrs["floor_from"] + 1) > 2000:
            raise serializers.ValidationError("At most 2000 units per request.")
        attrs["numbers"] = numbers
        return attrs


class RelayCommandResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    via = serializers.CharField(allow_blank=True)
    detail = serializers.CharField(allow_blank=True)


# --- QR check-in -------------------------------------------------------------

class QrCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=500, help_text="What the kiosk scanned: the share link or the token.")


class QrCheckInSerializer(QrCodeSerializer):
    plate = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    face_photo = serializers.ImageField(required=False)


class InvitationPassSerializer(serializers.ModelSerializer):
    """What a visitor (or a kiosk) may see about an invitation: no resident names beyond the host's first name."""

    condominium_name = serializers.CharField(source="condominium.name")
    condominium_address = serializers.CharField(source="condominium.address")
    unit_display = serializers.CharField(source="unit.__str__")
    host_first_name = serializers.SerializerMethodField()
    privacy_notice = serializers.CharField(source="condominium.privacy_notice")
    entries_left = serializers.SerializerMethodField()
    usable = serializers.SerializerMethodField()
    problem = serializers.SerializerMethodField()

    class Meta:
        model = m.Invitation
        fields = [
            "visitor_name", "purpose", "condominium_name", "condominium_address", "unit_display", "host_first_name",
            "valid_from", "valid_until", "status", "vehicle_plate", "require_face", "entries_left", "usable", "problem",
            "privacy_notice",
        ]

    def get_host_first_name(self, obj) -> str:
        return obj.host.first_name or ""

    def get_entries_left(self, obj) -> int | None:
        return None if not obj.max_entries else max(0, obj.max_entries - obj.entry_count)

    def get_usable(self, obj) -> bool:
        return obj.check_usable()[0]

    def get_problem(self, obj) -> str:
        return obj.check_usable()[1]


class QrCheckInResultSerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=["granted", "denied", "face_required"])
    reason = serializers.CharField(allow_blank=True)
    invitation = InvitationPassSerializer(allow_null=True)
