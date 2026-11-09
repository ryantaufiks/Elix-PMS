import json
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
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
            "visitor_data_retention_days", "kiosk_visitor_form", "kiosk_photo_required", "kiosk_walk_in", "kiosk_walk_in_photo", "kiosk_checkout", "kiosk_face_checkout",
            "visitor_privacy_notice",
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
    condominium_name = serializers.CharField(source="unit.condominium.name", read_only=True)
    unit_display = serializers.CharField(source="unit.__str__", read_only=True)

    class Meta:
        model = m.Residency
        fields = [
            "id", "user", "user_detail", "unit", "unit_display", "condominium", "condominium_name", "resident_type",
            "is_primary_contact", "receives_intercom_calls", "start_date", "end_date", "is_active",
        ]


DOCUMENT_TYPES = {b"%PDF-": ".pdf", b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png"}
DOCUMENT_MAX_BYTES = 8 * 1024 * 1024  # The gateway accepts 10 MB per request.


class ResidentDocumentSerializer(serializers.ModelSerializer):
    """A resident's document. The file is uploaded once and downloaded from ``…/{id}/download/``."""

    file = serializers.FileField(write_only=True)
    condominium = serializers.IntegerField(source="residency.unit.condominium_id", read_only=True)
    unit_display = serializers.CharField(source="residency.unit.__str__", read_only=True)
    resident_name = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = m.ResidentDocument
        fields = ["id", "residency", "condominium", "unit_display", "resident_name", "kind", "title", "file",
                  "file_name", "size", "uploaded_by_name", "created_at"]
        read_only_fields = ["file_name", "size", "created_at"]

    def get_resident_name(self, obj) -> str:
        user = obj.residency.user
        return user.get_full_name() or user.get_username()

    def get_uploaded_by_name(self, obj) -> str:
        return (obj.uploaded_by.get_full_name() or obj.uploaded_by.get_username()) if obj.uploaded_by else ""

    def validate_file(self, upload):
        if upload.size > DOCUMENT_MAX_BYTES:
            raise serializers.ValidationError("The file is larger than 8 MB.")
        head = upload.read(8)
        upload.seek(0)
        # Judge the file by its content, not its name: only PDF, JPEG and PNG are kept.
        suffix = next((ext for magic, ext in DOCUMENT_TYPES.items() if head.startswith(magic)), None)
        if suffix is None:
            raise serializers.ValidationError("Upload a PDF, JPG or PNG file.")
        upload.document_suffix = suffix
        return upload

    def validate(self, attrs):
        if self.instance is not None and "residency" in attrs and attrs["residency"] != self.instance.residency:
            raise serializers.ValidationError({"residency": "A document cannot be moved to another resident."})
        upload = attrs.get("file")
        if upload is not None:
            attrs["file_name"] = upload.name[-255:]
            attrs["size"] = upload.size
            upload.name = f"document{upload.document_suffix}"
        return attrs


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
            "lpr_auto_open_residents", "lpr_auto_open_invited", "resident_remote_open",
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
        fields = ["id", "condominium", "gate", "name", "is_active", "prints_slips", "token_hint", "last_seen_at", "app_version"]
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


@extend_schema_field({"type": "array", "items": {"type": "number"}, "minItems": 128, "maxItems": 128, "nullable": True})
class FaceDescriptorField(serializers.Field):
    """A face template from the kiosk browser: 128 numbers, as a JSON array or (multipart) a JSON string."""

    def to_internal_value(self, data):
        from .visits import valid_face

        if isinstance(data, str):
            try:
                data = json.loads(data) if data.strip() else None
            except ValueError:
                raise serializers.ValidationError("Not a face template.")
        if data is None:
            return None
        face = valid_face(data)
        if face is None:
            raise serializers.ValidationError("A face template is 128 numbers.")
        return face

    def to_representation(self, value):
        return value


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
    face_descriptor = FaceDescriptorField(required=False, allow_null=True, default=None,
                                          help_text="Face template of the snapshot, for face check-out (site setting).")


class WalkInRegisterSerializer(StartCallSerializer):
    purpose = serializers.ChoiceField(choices=m.VisitPurpose.choices)


VISIT_STATES = ["on_site", "checked_out", "expired"]


class VisitSerializer(ModelCleanSerializer):
    """A visit as security sees it. Only the name, company and notes can be edited."""

    unit_display = serializers.CharField(source="unit.__str__", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    kiosk_name = serializers.CharField(source="kiosk.name", read_only=True, default="")
    gate_name = serializers.CharField(source="gate.name", read_only=True, default="")
    state = serializers.ChoiceField(choices=VISIT_STATES, read_only=True)
    has_snapshot = serializers.SerializerMethodField()
    visitor_phone = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    checked_out_by_name = serializers.SerializerMethodField()
    visitor_blocked = serializers.BooleanField(source="visitor.is_blacklisted", read_only=True, default=False)

    class Meta:
        model = m.Visit
        fields = [
            "id", "condominium", "unit", "unit_display", "source", "source_display", "kiosk", "kiosk_name", "gate",
            "gate_name", "invitation", "intercom_call", "visitor", "visitor_name", "visitor_phone", "visitor_blocked", "purpose", "company",
            "vehicle_plate", "notes", "has_snapshot", "pass_number", "pin", "issued_on", "valid_until", "state",
            "checked_out_at", "checked_out_by", "checked_out_by_name", "created_by", "created_by_name", "created_at",
        ]
        read_only_fields = sorted(set(fields) - {"visitor_name", "company", "notes"})

    def get_has_snapshot(self, obj) -> bool:
        return obj.photo() is not None

    def get_visitor_phone(self, obj) -> str:
        return str(obj.visitor.phone) if obj.visitor and obj.visitor.phone else ""

    def get_created_by_name(self, obj) -> str:
        return (obj.created_by.get_full_name() or obj.created_by.get_username()) if obj.created_by else ""

    def get_checked_out_by_name(self, obj) -> str:
        return (obj.checked_out_by.get_full_name() or obj.checked_out_by.get_username()) if obj.checked_out_by else ""


class StaffVisitCreateSerializer(serializers.Serializer):
    """A walk-in registered by security at the guardhouse."""

    unit = serializers.PrimaryKeyRelatedField(queryset=m.Unit.objects.filter(is_active=True))
    visitor_name = serializers.CharField(max_length=150)
    purpose = serializers.ChoiceField(choices=m.VisitPurpose.choices)
    company = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    visitor_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    visitor_id_partial = serializers.CharField(max_length=8, required=False, allow_blank=True, default="",
                                               help_text="Last 3 digits and letter of the NRIC/FIN only.")
    vehicle_plate = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    snapshot = serializers.ImageField(required=False)
    consent = serializers.BooleanField(help_text="The visitor was shown the privacy notice and agreed.")

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("The visitor must agree to the privacy notice.")
        return value


class VisitIdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=500)


class BulkCheckOutResultSerializer(serializers.Serializer):
    checked_out = serializers.IntegerField()


class VisitSlipSerializer(serializers.ModelSerializer):
    """What goes on the printed slip (or the kiosk screen)."""

    condominium_name = serializers.CharField(source="condominium.name")
    unit_display = serializers.CharField(source="unit.__str__")
    purpose_display = serializers.CharField(source="get_purpose_display")
    state = serializers.ChoiceField(choices=VISIT_STATES)
    qr = serializers.SerializerMethodField(help_text="PNG data URI of the check-out QR code.")

    class Meta:
        model = m.Visit
        fields = ["pass_number", "pin", "visitor_name", "purpose", "purpose_display", "company", "vehicle_plate", "unit_display",
                  "condominium_name", "created_at", "valid_until", "state", "checked_out_at", "qr"]

    def get_qr(self, obj) -> str:
        from .visits import qr_data_uri

        return qr_data_uri(obj)


class KioskCheckOutSerializer(serializers.Serializer):
    """The QR on the pass (or the invitation QR), its 4-digit PIN, or the visitor's face template."""

    code = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    pin = serializers.RegexField(r"^\d{4}$", required=False, allow_blank=True, default="")
    face = FaceDescriptorField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if not attrs["code"].strip() and not attrs["pin"] and not attrs["face"]:
            raise serializers.ValidationError("Scan the QR code, enter the PIN or look at the camera.")
        return attrs


class WalkInCheckOutResultSerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=["checked_out", "already_checked_out"])
    walk_in = VisitSlipSerializer()


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
    walk_in = serializers.BooleanField(source="condominium.kiosk_walk_in")
    walk_in_photo = serializers.BooleanField(source="condominium.kiosk_walk_in_photo")
    checkout = serializers.BooleanField(source="condominium.kiosk_checkout")
    face_checkout = serializers.SerializerMethodField()

    class Meta:
        model = m.Kiosk
        fields = ["id", "name", "condominium", "condominium_name", "gate", "gate_name", "ring_timeout_seconds",
                  "visitor_form", "photo_required", "privacy_notice", "walk_in", "walk_in_photo", "checkout", "face_checkout", "prints_slips"]

    def get_face_checkout(self, obj) -> bool:
        return obj.condominium.kiosk_checkout and obj.condominium.kiosk_face_checkout


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
    secret_fields = ("livekit_api_secret", "fcm_service_account_json", "openai_api_key")
    livekit_configured = serializers.SerializerMethodField()
    fcm_configured = serializers.SerializerMethodField()
    openai_configured = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()

    class Meta:
        model = m.SystemSettings
        fields = [
            "livekit_url", "livekit_api_key", "livekit_api_secret", "livekit_token_ttl_seconds",
            "intercom_unlock_window_seconds", "fcm_service_account_json", "relay_http_timeout",
            "lpr_debounce_seconds", "openai_api_key", "assistant_mode", "assistant_chat_model", "assistant_transcribe_model",
            "assistant_tts_model", "assistant_realtime_model", "assistant_voice", "assistant_max_session_seconds",
            "assistant_daily_sessions", "livekit_configured", "fcm_configured", "openai_configured", "sources", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def get_livekit_configured(self, obj) -> bool:
        from . import config
        return all(config.source(n) for n in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))

    def get_openai_configured(self, obj) -> bool:
        from . import config
        return bool(config.get("OPENAI_API_KEY"))

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
    face_descriptor = FaceDescriptorField(required=False, allow_null=True, default=None)


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


# --- Facilities, bookings, payments, feedback ---------------------------------------------------------

class FacilitySerializer(ModelCleanSerializer):
    has_image = serializers.SerializerMethodField()
    is_paid = serializers.BooleanField(read_only=True)

    class Meta:
        model = m.Facility
        fields = [
            "id", "condominium", "name", "description", "location", "icon", "image", "has_image", "capacity",
            "opens_at", "closes_at", "open_days", "slot_minutes", "max_slots_per_booking", "concurrent_bookings",
            "price_per_slot", "deposit", "is_paid", "advance_days", "max_upcoming_per_unit", "cancel_hours", "rules",
            "is_active", "created_at",
        ]
        extra_kwargs = {"image": {"write_only": True, "required": False}}

    def get_has_image(self, obj) -> bool:
        return bool(obj.image)


class SlotSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    available = serializers.BooleanField()
    left = serializers.IntegerField()


class AvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    open = serializers.BooleanField()
    bookable_from = serializers.DateField()
    bookable_until = serializers.DateField()
    slots = SlotSerializer(many=True)


class BookingSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    facility_icon = serializers.CharField(source="facility.icon", read_only=True)
    unit_display = serializers.CharField(source="unit.__str__", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    booked_by = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = m.Booking
        fields = [
            "id", "condominium", "facility", "facility_name", "facility_icon", "unit", "unit_display", "booked_by",
            "starts_at", "ends_at", "slots", "guests", "notes", "status", "status_display", "amount", "deposit",
            "currency", "payment_status", "payment_status_display", "payment_url", "payment_expires_at", "paid_at",
            "cancelled_at", "cancel_reason", "can_cancel", "created_at",
        ]
        read_only_fields = fields

    def get_booked_by(self, obj) -> str:
        return (obj.user.get_full_name() or obj.user.get_username()) if obj.user else ""

    def get_can_cancel(self, obj) -> bool:
        """Whether the resident can still cancel it themselves."""
        return (obj.status in m.Booking.ACTIVE_STATUSES
                and obj.starts_at - timezone.now() >= timedelta(hours=obj.facility.cancel_hours))


class BookingCreateSerializer(serializers.Serializer):
    facility = serializers.PrimaryKeyRelatedField(queryset=m.Facility.objects.all())
    unit = serializers.PrimaryKeyRelatedField(queryset=m.Unit.objects.all(), required=False,
                                              help_text="Needed only when the resident lives in several units.")
    starts_at = serializers.DateTimeField()
    slots = serializers.IntegerField(min_value=1, default=1)
    guests = serializers.IntegerField(min_value=1, default=1)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class BookingCreatedSerializer(serializers.Serializer):
    booking = BookingSerializer()
    payment_url = serializers.CharField(allow_blank=True)
    return_url_prefix = serializers.CharField(help_text="The app closes the payment page when it reaches this URL.")


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PaymentSettingsSerializer(ModelCleanSerializer):
    secret_fields = ("hitpay_api_key", "hitpay_salt")
    webhook_url = serializers.SerializerMethodField()

    class Meta:
        model = m.PaymentSettings
        fields = ["condominium", "enabled", "sandbox", "hitpay_api_key", "hitpay_salt", "currency", "payment_minutes",
                  "webhook_url", "updated_at"]
        read_only_fields = ["condominium", "updated_at"]

    def get_webhook_url(self, obj) -> str:
        request = self.context.get("request")
        return request.build_absolute_uri("/v1/payments/hitpay/webhook/") if request else "/v1/payments/hitpay/webhook/"


class FeedbackSerializer(ModelCleanSerializer):
    unit_display = serializers.CharField(source="unit.__str__", read_only=True, default="")
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    resident_name = serializers.SerializerMethodField()
    replied_by_name = serializers.SerializerMethodField()

    class Meta:
        model = m.Feedback
        fields = [
            "id", "condominium", "unit", "unit_display", "resident_name", "rating", "category", "category_display",
            "comment", "status", "status_display", "reply", "replied_by_name", "replied_at", "created_at",
        ]
        read_only_fields = ["condominium", "unit", "status", "reply", "replied_at", "created_at"]

    def get_resident_name(self, obj) -> str:
        return (obj.user.get_full_name() or obj.user.get_username()) if obj.user else ""

    def get_replied_by_name(self, obj) -> str:
        return (obj.replied_by.get_full_name() or obj.replied_by.get_username()) if obj.replied_by else ""


class FeedbackCreateSerializer(serializers.Serializer):
    unit = serializers.PrimaryKeyRelatedField(queryset=m.Unit.objects.all(), required=False)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    category = serializers.ChoiceField(choices=m.Feedback.Category.choices, default=m.Feedback.Category.OTHER)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class FeedbackReplySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=m.Feedback.Status.choices, required=False)
    reply = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class FeedbackSummarySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True)
    by_rating = serializers.DictField(child=serializers.IntegerField())
    open = serializers.IntegerField()


# --- Resident feed & weather ---------------------------------------------------

class NotificationSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField(help_text="visit_in, visit_out, gate_open, gate_denied, call_missed, booking_confirmed, "
                                           "booking_cancelled, booking_expired or feedback_reply")
    title = serializers.CharField()
    body = serializers.CharField()
    at = serializers.DateTimeField()


class NotificationPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = NotificationSerializer(many=True)


class WeatherSerializer(serializers.Serializer):
    temperature = serializers.FloatField(allow_null=True, help_text="°C at the nearest NEA station")
    humidity = serializers.FloatField(allow_null=True, help_text="Relative humidity, %")
    forecast = serializers.CharField(help_text="2-hour outlook, e.g. Partly Cloudy (Day), Thundery Showers")
    area = serializers.CharField()
    station = serializers.CharField()
    valid = serializers.CharField(help_text="Period of the outlook, e.g. 10.30 pm to 12.30 am")
    updated_at = serializers.DateTimeField()


class BackupDownloadSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = m.BackupDownload
        fields = ["user_name", "ip", "at"]

    def get_user_name(self, obj) -> str:
        return (obj.user.get_full_name() or obj.user.get_username()) if obj.user else ""


class BackupSerializer(serializers.ModelSerializer):
    condominium_name = serializers.CharField(source="condominium.name", read_only=True, default="")
    created_by_name = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    downloads = BackupDownloadSerializer(many=True, read_only=True)

    class Meta:
        model = m.Backup
        fields = ["id", "kind", "condominium", "condominium_name", "status", "file_name", "size", "error", "automatic",
                  "created_by_name", "created_at", "finished_at", "expires_at", "downloads"]
        read_only_fields = ["status", "size", "error", "automatic", "created_at", "finished_at", "expires_at"]

    def get_created_by_name(self, obj) -> str:
        return (obj.created_by.get_full_name() or obj.created_by.get_username()) if obj.created_by else ""

    def get_file_name(self, obj) -> str:
        return obj.file.name if obj.file else ""

    def validate(self, attrs):
        if attrs["kind"] == m.Backup.Kind.SITE and not attrs.get("condominium"):
            raise serializers.ValidationError({"condominium": "Choose the site to export."})
        if attrs["kind"] == m.Backup.Kind.PLATFORM:
            attrs["condominium"] = None
        return attrs


# --- Kiosk AI assistant ------------------------------------------------------------------------------

class KioskAssistantMapSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class KioskAssistantSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    name = serializers.CharField()
    greeting = serializers.CharField(allow_blank=True)
    mode = serializers.CharField()
    max_session_seconds = serializers.IntegerField()
    maps = KioskAssistantMapSerializer(many=True)


class KioskAssistantStartSerializer(serializers.Serializer):
    session = serializers.IntegerField()
    mode = serializers.CharField()
    greeting = serializers.CharField(allow_blank=True)
    greeting_audio = serializers.CharField(allow_blank=True, help_text="Base64 MP3 (speech-to-text mode).")
    client_secret = serializers.CharField(allow_blank=True, help_text="One-minute OpenAI client secret (realtime mode).")


class KioskAssistantTurnSerializer(serializers.Serializer):
    audio = serializers.FileField(required=False, help_text="What the visitor said (WebM/Opus, up to 2 MB).")
    text = serializers.CharField(required=False, allow_blank=True, max_length=1000, help_text="Typed instead of spoken.")
    history = serializers.JSONField(required=False, binary=True, help_text="Recent turns: [{role, content}].")

    def validate_audio(self, value):
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Recording too long.")
        return value

    def validate(self, attrs):
        if not attrs.get("audio") and not attrs.get("text", "").strip():
            raise serializers.ValidationError("Send audio or text.")
        return attrs


class KioskAssistantReplySerializer(serializers.Serializer):
    heard = serializers.CharField(allow_blank=True)
    reply = serializers.CharField(allow_blank=True)
    audio = serializers.CharField(allow_blank=True, help_text="Base64 MP3 of the reply.")
    actions = serializers.ListField(child=serializers.DictField())


class AssistantSettingsSerializer(ModelCleanSerializer):
    secret_fields = ("openai_api_key",)

    class Meta:
        model = m.AssistantSettings
        fields = ["condominium", "enabled", "name", "greeting", "languages", "instructions", "openai_api_key", "updated_at"]
        read_only_fields = ["condominium", "updated_at"]


class AssistantModuleSerializer(ModelCleanSerializer):
    class Meta:
        model = m.AssistantModule
        fields = ["id", "condominium", "title", "content", "order", "is_active"]


class AssistantMapSerializer(ModelCleanSerializer):
    image = serializers.ImageField(write_only=True, required=False)
    has_image = serializers.SerializerMethodField()

    class Meta:
        model = m.AssistantMap
        fields = ["id", "condominium", "name", "description", "image", "has_image", "order", "is_active"]

    def get_has_image(self, obj) -> bool:
        return bool(obj.image)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("image"):
            raise serializers.ValidationError({"image": "Upload the map image."})
        return attrs


class AssistantTestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=1000)
    history = serializers.JSONField(required=False, write_only=True)
    reply = serializers.CharField(read_only=True)
    actions = serializers.ListField(child=serializers.DictField(), read_only=True)
