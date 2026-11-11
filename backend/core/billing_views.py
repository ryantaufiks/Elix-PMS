"""Plans and subscriptions: the platform admin sells modules per site; site admins see what they have."""
import csv
import io
from datetime import date, timedelta

from django.db import transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import entitlements, subscriptions, usage
from . import models as m
from .scoping import ADMIN, ALL_STAFF, staff_condo_ids
from .serializers import ModelCleanSerializer


class PlanSerializer(ModelCleanSerializer):
    subscriptions = serializers.IntegerField(source="subscriptions.count", read_only=True)

    class Meta:
        model = m.Plan
        fields = ["id", "code", "name", "description", "modules", "limits", "overage_rates", "currency", "sort_order",
                  "is_public", "is_active", "subscriptions", "updated_at"]


class SubscriptionEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = m.SubscriptionEvent
        fields = ["id", "at", "actor_name", "summary"]

    def get_actor_name(self, obj) -> str:
        return (obj.actor.get_full_name() or obj.actor.get_username()) if obj.actor else "System"


class SubscriptionSerializer(ModelCleanSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    condominium_name = serializers.CharField(source="condominium.name", read_only=True)
    modules = serializers.ListField(source="condominium.modules", child=serializers.CharField(), read_only=True)
    limits = serializers.SerializerMethodField()
    usage = serializers.SerializerMethodField()

    class Meta:
        model = m.Subscription
        fields = ["condominium", "condominium_name", "plan", "plan_name", "addons", "disabled_modules", "limit_overrides",
                  "status", "trial_ends_on", "period_ends_on", "grace_ends_on", "billing_name", "billing_email", "notes",
                  "modules", "limits", "usage", "updated_at"]
        read_only_fields = ["condominium"]

    def get_limits(self, obj) -> dict:
        return entitlements.limits(obj.condominium)

    def get_usage(self, obj) -> dict:
        return entitlements.usage(obj.condominium)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        plan = attrs.get("plan", self.instance.plan if self.instance else None)
        addons = attrs.get("addons", self.instance.addons if self.instance else [])
        if plan is not None and (missing := entitlements.missing_requirements(set(plan.modules) | set(addons) | {"core"})):
            raise serializers.ValidationError({"addons": missing})
        return attrs


def describe_changes(before: m.Subscription, after: m.Subscription) -> str:
    """One line for the subscription's history, e.g. 'Plan Standard -> Premium; status Trial -> Active'."""
    names = lambda keys: ", ".join(entitlements.MODULES[k].name for k in keys) or "none"  # noqa: E731
    parts = []
    if before.plan_id != after.plan_id:
        parts.append(f"plan {before.plan.name} -> {after.plan.name}")
    if before.status != after.status:
        parts.append(f"status {before.get_status_display()} -> {after.get_status_display()}")
    for field, label in (("addons", "add-ons"), ("disabled_modules", "switched off")):
        if set(getattr(before, field)) != set(getattr(after, field)):
            parts.append(f"{label}: {names(getattr(after, field))}")
    if before.limit_overrides != after.limit_overrides:
        parts.append("limits changed")
    for field, label in (("trial_ends_on", "trial ends"), ("period_ends_on", "paid until"), ("grace_ends_on", "grace until")):
        if getattr(before, field) != getattr(after, field):
            value = getattr(after, field)
            parts.append(f"{label} {value:%d %b %Y}" if value else f"{label} cleared")
    if (before.billing_name, before.billing_email, before.notes) != (after.billing_name, after.billing_email, after.notes):
        parts.append("billing details or notes changed")
    text = "; ".join(parts)
    return (text[:1].upper() + text[1:] + ".") if text else ""


class PlanViewSet(viewsets.ModelViewSet):
    """Plans. Everyone signed in can read them (for "Available in ..." hints); the platform admin edits."""

    queryset = m.Plan.objects.all()
    serializer_class = PlanSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if self.request.user.is_superuser else qs.filter(is_active=True, is_public=True)

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.user.is_superuser:
            raise PermissionDenied("Only the platform administrator manages plans.")

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise serializers.ValidationError({"detail": "Sites are on this plan: move them first, or mark it inactive."})


class SubscriptionView(generics.RetrieveUpdateAPIView):
    """A site's subscription. Site admins read it (without internal notes); the platform admin changes it."""

    serializer_class = SubscriptionSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        condo_id = self.kwargs["condominium"]
        user = self.request.user
        if not user.is_superuser and condo_id not in staff_condo_ids(user, (ADMIN,)):
            raise PermissionDenied("Only the site admin can see the site's plan.")
        if self.request.method == "PATCH" and not user.is_superuser:
            raise PermissionDenied("Only the platform administrator changes subscriptions.")
        condo = generics.get_object_or_404(m.Condominium, pk=condo_id)
        return getattr(condo, "subscription", None) or entitlements.start_subscription(condo, actor=user)

    def retrieve(self, request, *args, **kwargs):
        sub = self.get_object()
        data = self.get_serializer(sub).data
        if request.user.is_superuser:
            data["events"] = SubscriptionEventSerializer(sub.events.select_related("actor")[:50], many=True).data
        else:
            data.pop("notes")
        return Response(data)

    def perform_update(self, serializer):
        before = m.Subscription.objects.select_related("plan").get(pk=serializer.instance.pk)
        status_now = serializer.validated_data.get("status", before.status)
        extra = {}
        if status_now == m.Subscription.Status.GRACE and not serializer.validated_data.get("grace_ends_on", before.grace_ends_on):
            extra["grace_ends_on"] = timezone.localdate() + timedelta(days=subscriptions.GRACE_DAYS)
        elif status_now in (m.Subscription.Status.ACTIVE, m.Subscription.Status.TRIAL):
            extra["grace_ends_on"] = None
        with transaction.atomic():
            sub = serializer.save(**extra)
            if summary := describe_changes(before, sub):
                m.SubscriptionEvent.objects.create(subscription=sub, actor=self.request.user, summary=summary[:500])
        subscriptions.on_status_change(sub, before.status, self.request.user)

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return self.retrieve(request)


class ModuleCatalogueView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        """Every module and limit, with the first plan that includes each module (for "Available in" hints)."""
        if not request.user.is_superuser and not staff_condo_ids(request.user, ALL_STAFF):
            raise PermissionDenied("For staff only.")
        plans = list(m.Plan.objects.filter(is_active=True, is_public=True))
        return Response({
            "modules": [{"key": x.key, "name": x.name, "description": x.description, "requires": list(x.requires),
                         "available": x.available, "upsell_plan": entitlements.upsell_plan(x.key, plans)}
                        for x in entitlements.MODULES.values()],
            "limits": [{"key": x.key, "name": x.name, "unit": x.unit, "enforced": x.enforced, "metered": x.metered}
                       for x in entitlements.LIMITS.values()],
        }, status=status.HTTP_200_OK)


USAGE_COLUMNS = [
    ("site", "Site"), ("code", "Code"), ("plan", "Plan"), ("status", "Status"),
    ("intercom_minutes", "Intercom minutes"), ("intercom_minutes_allowed", "Included"),
    ("intercom_minutes_overage", "Over"), ("intercom_minutes_amount", "Intercom overage amount"),
    ("ai_conversations", "AI conversations"), ("ai_conversations_allowed", "Included"),
    ("ai_conversations_overage", "Over"), ("ai_conversations_amount", "AI overage amount"),
    ("ai_conversations_own_key", "AI conversations (own key)"), ("ai_tokens_in", "AI input tokens"),
    ("ai_tokens_out", "AI output tokens"), ("ai_cost_usd", "AI cost estimate (USD)"),
    ("overage_amount", "Overage total"), ("currency", "Currency"),
]


class UsageReportView(APIView):
    """Monthly usage and overage per site, for invoicing (platform administrator only)."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("Only the platform administrator sees usage across sites.")
        raw = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            month = date.fromisoformat(f"{raw}-01")
        except ValueError:
            raise serializers.ValidationError({"month": "Use YYYY-MM."})
        sites = m.Condominium.objects.select_related("subscription__plan").order_by("name")
        rows = usage.report(month, sites)
        if request.query_params.get("export") == "csv":
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow([label for _, label in USAGE_COLUMNS])
            for row in rows:
                writer.writerow(["" if row.get(key) is None else row.get(key) for key, _ in USAGE_COLUMNS])
            response = HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="elix-usage-{month:%Y-%m}.csv"'
            return response
        return Response({"month": f"{month:%Y-%m}", "rows": rows})
