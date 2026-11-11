"""What each site has bought: a plan, add-ons and the subscription's status (see ``core.entitlements``)."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .base import TimeStampedModel
from .tenancy import Condominium


class Plan(TimeStampedModel):
    """A package of modules with limits, e.g. Basic, Standard, Premium. Prices live in the contract."""

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=255, blank=True)
    modules = models.JSONField(default=list, blank=True, help_text="Module keys included (core is always on).")
    limits = models.JSONField(default=dict, blank=True, help_text="Limit key -> number; missing means unlimited.")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Lower comes first in lists and upsell hints.")
    is_public = models.BooleanField(default=True, help_text="Offered to customers (internal plans are hidden in upsell hints).")
    is_active = models.BooleanField(default=True, help_text="Can be given to new subscriptions.")

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        from core import entitlements

        errors = {}
        if bad := entitlements.unknown_modules(self.modules):
            errors["modules"] = f"Unknown module(s): {', '.join(bad)}."
        elif missing := entitlements.missing_requirements(set(self.modules) | {"core"}):
            errors["modules"] = missing
        if bad := entitlements.bad_limits(self.limits):
            errors["limits"] = bad
        if errors:
            raise ValidationError(errors)


class Subscription(TimeStampedModel):
    """A site's plan, extra modules, modules switched off by the platform admin, and where it stands."""

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        GRACE = "grace", "Grace period"
        SUSPENDED = "suspended", "Suspended"
        CANCELLED = "cancelled", "Cancelled"

    condominium = models.OneToOneField(Condominium, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    addons = models.JSONField(default=list, blank=True, help_text="Modules bought on top of the plan.")
    disabled_modules = models.JSONField(
        default=list, blank=True, help_text="Modules the platform admin has switched off for this site.")
    limit_overrides = models.JSONField(default=dict, blank=True, help_text="Limits that differ from the plan's.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIAL)
    trial_ends_on = models.DateField(null=True, blank=True)
    period_ends_on = models.DateField(null=True, blank=True, help_text="End of the paid period.")
    billing_name = models.CharField("Billing contact", max_length=120, blank=True)
    billing_email = models.EmailField("Billing email", blank=True)
    notes = models.TextField(blank=True, help_text="Internal: contract, invoice numbers, special terms.")

    class Meta:
        ordering = ["condominium__name"]

    def __str__(self):
        return f"{self.condominium} - {self.plan} ({self.get_status_display()})"

    def clean(self):
        from core import entitlements

        errors = {}
        for field in ("addons", "disabled_modules"):
            if bad := entitlements.unknown_modules(getattr(self, field)):
                errors[field] = f"Unknown module(s): {', '.join(bad)}."
        if "core" in self.disabled_modules:
            errors["disabled_modules"] = "Core cannot be switched off."
        if bad := entitlements.bad_limits(self.limit_overrides):
            errors["limit_overrides"] = bad
        if errors:
            raise ValidationError(errors)


class SubscriptionEvent(models.Model):
    """Who changed a subscription, when and how (shown on the site's Subscription tab)."""

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    summary = models.CharField(max_length=500)

    class Meta:
        ordering = ["-at"]
