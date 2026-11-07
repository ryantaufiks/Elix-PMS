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
            "id", "name", "code", "address", "postal_code", "timezone", "contact_phone", "is_active",
            "invitation_max_days", "intercom_ring_timeout_seconds", "face_verification_enabled",
            "visitor_data_retention_days", "created_at", "updated_at",
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

    class Meta:
        model = m.Residency
        fields = [
            "id", "user", "user_detail", "unit", "condominium", "resident_type", "is_primary_contact",
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

    class Meta:
        model = m.Vehicle
        fields = ["id", "condominium", "unit", "plate_number", "make", "model", "colour", "is_active", "notes"]
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

    class Meta:
        model = m.LprCamera
        fields = [
            "id", "gate", "name", "device_id", "direction", "ip_address", "is_active",
            "webhook_username", "webhook_password", "api_username", "api_password", "last_seen_at",
        ]
        read_only_fields = ["last_seen_at"]

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
            "id", "condominium", "full_name", "phone", "id_partial", "company", "face_photo", "face_consent_at",
            "is_blacklisted", "blacklist_reason", "created_by", "created_at",
        ]
        read_only_fields = ["created_by"]


class InvitationSerializer(ModelCleanSerializer):
    derived_fields = {"condominium", "vehicle_plate"}
    share_url = serializers.CharField(read_only=True)
    host_detail = UserSummarySerializer(source="host", read_only=True)

    class Meta:
        model = m.Invitation
        fields = [
            "id", "condominium", "unit", "host", "host_detail", "visitor", "visitor_name", "visitor_phone",
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

    class Meta:
        model = m.IntercomCall
        fields = [
            "id", "condominium", "unit", "unit_display", "kiosk", "kiosk_name", "gate", "status", "is_open",
            "visitor_name", "has_snapshot", "answered_by", "answered_at", "decided_by", "decided_at", "ended_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_has_snapshot(self, obj) -> bool:
        return bool(obj.visitor_snapshot)


class LiveKitConnectionSerializer(serializers.Serializer):
    url = serializers.CharField()
    room = serializers.CharField()
    token = serializers.CharField()


class CallWithConnectionSerializer(serializers.Serializer):
    call = IntercomCallSerializer()
    livekit = LiveKitConnectionSerializer()


class StartCallSerializer(serializers.Serializer):
    unit = serializers.PrimaryKeyRelatedField(queryset=m.Unit.objects.filter(is_active=True))
    visitor_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    snapshot = serializers.ImageField(required=False)


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

    class Meta:
        model = m.Kiosk
        fields = ["id", "name", "condominium", "condominium_name", "gate", "gate_name", "ring_timeout_seconds"]


class PushDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.PushDevice
        fields = ["id", "platform", "token", "app_version", "created_at", "last_used_at"]
        read_only_fields = ["created_at", "last_used_at"]
        extra_kwargs = {"token": {"validators": []}}


class AccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.AccessLog
        fields = [
            "id", "condominium", "gate", "occurred_at", "method", "result", "reason", "plate_number", "unit",
            "vehicle", "invitation", "visitor", "intercom_call", "camera", "relay", "actor", "snapshot",
        ]
        read_only_fields = fields
