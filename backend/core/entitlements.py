"""Modules and limits each site has bought.

The catalogue lives here (the checks are in code); plans and subscriptions in the database. A site's
effective modules are stored on ``Condominium.modules`` whenever its subscription or plan changes, so
every check, including database filters, reads one column.
"""
from dataclasses import dataclass

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException


@dataclass(frozen=True)
class Module:
    key: str
    name: str
    description: str
    requires: tuple = ()
    available: bool = True  # False: on the roadmap; can be sold ahead but does nothing yet.
    keeps_access: bool = False  # Stays on while suspended: physical access must never stop.


MODULES = {m.key: m for m in (
    Module("core", "Core", "Visitor dashboard with overstay alerts, visitor list, access log, staff invitations, open "
           "gates, residents, vehicle passes with start and end dates, kiosk in four languages (walk-in, invitation "
           "QR, check-out), cloud relays, on-screen reports.", keeps_access=True),
    Module("resident_app", "Resident app", "Android app: invitations, vehicles, activity, notifications, swipe to "
           "open, documents, feedback."),
    Module("intercom", "Video intercom", "Visitors video call a unit, or the guardhouse, from the kiosk; residents and "
           "guards open the gate from the call.", requires=("resident_app",)),
    Module("facilities", "Facilities & payments", "Facility booking and season parking paid with HitPay; kiosk "
           "check-in with the booking QR, today's schedule and no-shows.", requires=("resident_app",)),
    Module("lpr", "LPR", "Licence-plate cameras: residents' and invited vehicles enter automatically.",
           keeps_access=True),
    Module("face_kiosk", "Face check (kiosk)", "Face verification for invitations and face check-out at the kiosk."),
    Module("ai_concierge", "AI concierge", "Voice assistant on the kiosk (Elixa): directions, help registering, and "
           "calling the guardhouse."),
    Module("advanced_reports", "Advanced reports", "Insights (busiest times, visits and stay by category), export to "
           "Excel and CSV, and print / PDF."),
    Module("local_devices", "On-site devices", "Secure link to devices at the site; local Shelly and eWeLink.",
           available=False, keeps_access=True),
    Module("lpr_camera_list", "LPR whitelist on camera", "Plates synced to the cameras: gates work while offline.",
           requires=("lpr", "local_devices"), available=False, keeps_access=True),
    Module("face_terminal", "Face terminals", "Residents' faces on access terminals.", requires=("local_devices",),
           available=False, keeps_access=True),
)}


@dataclass(frozen=True)
class Limit:
    key: str
    name: str
    unit: str = ""
    enforced: bool = True  # False: shown, enforced in a later release.
    metered: bool = False  # Monthly allowance: use past it keeps working and is billed as overage.


LIMITS = {x.key: x for x in (
    Limit("units", "Units"),
    Limit("kiosks", "Kiosks"),
    Limit("gates", "Gates"),
    Limit("lpr_cameras", "LPR cameras"),
    Limit("staff_accounts", "Staff accounts"),
    Limit("face_terminals", "Face terminals", enforced=False),
    Limit("intercom_minutes", "Video intercom", "minutes / month", enforced=False, metered=True),
    Limit("ai_conversations", "AI conversations", "per month", enforced=False, metered=True),
    Limit("storage_gb", "Storage", "GB", enforced=False),
)}


class ModuleLocked(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "module_locked"

    def __init__(self, module):
        self.module = module
        name = MODULES[module].name if module in MODULES else module
        super().__init__({"detail": f"{name} is not included in this site's plan.", "code": "module_locked",
                          "module": module})


class SiteSuspended(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "site_suspended"

    def __init__(self):
        super().__init__({"detail": "This site's subscription is suspended: setup is locked until it is renewed. "
                                    "Contact Elix.", "code": "site_suspended"})


class LimitReached(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "limit_reached"

    def __init__(self, key, allowed):
        name = LIMITS[key].name.lower()
        super().__init__({"detail": f"This site's plan allows {allowed} {name}. Contact Elix to add more.",
                          "code": "limit_reached", "limit": key, "allowed": allowed})


# --- Validation helpers (models' clean) --------------------------------------------------------------

def unknown_modules(keys) -> list:
    return [k for k in (keys or []) if k not in MODULES] if isinstance(keys, list) else ["(not a list)"]


def missing_requirements(keys: set) -> str:
    problems = [f"{MODULES[k].name} needs {', '.join(MODULES[r].name for r in MODULES[k].requires if r not in keys)}"
                for k in sorted(keys) if k in MODULES and any(r not in keys for r in MODULES[k].requires)]
    return "; ".join(problems) + "." if problems else ""


def bad_limits(limits) -> str:
    if not isinstance(limits, dict):
        return "Limits must be an object of limit -> number."
    for key, value in limits.items():
        if key not in LIMITS:
            return f"Unknown limit: {key}."
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            return f"{LIMITS[key].name}: a whole number of 0 or more, or empty for unlimited."
    return ""


def bad_rates(rates) -> str:
    if not isinstance(rates, dict):
        return "Rates must be an object of limit -> price."
    for key, value in rates.items():
        if key not in LIMITS or not LIMITS[key].metered:
            return f"{key} is not a metered limit."
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return f"{LIMITS[key].name}: a price of 0 or more."
    return ""


# --- Effective modules ---------------------------------------------------------------------------------

def effective_modules(subscription) -> list:
    """Plan + add-ons - switched off, without modules whose requirements are gone; while suspended or
    cancelled only what keeps physical access working."""
    keys = ({"core"} | set(subscription.plan.modules) | set(subscription.addons)) - set(subscription.disabled_modules)
    keys.add("core")
    if subscription.status == subscription.Status.SUSPENDED:  # Gates keep working; reports can still be exported.
        keys = {k for k in keys if MODULES[k].keeps_access or k == "advanced_reports"}
    elif subscription.status == subscription.Status.CANCELLED:
        keys = {k for k in keys if MODULES[k].keeps_access}
    while True:  # Drop modules whose requirements are not (or no longer) there, transitively.
        kept = {k for k in keys if k in MODULES and all(r in keys for r in MODULES[k].requires)}
        if kept == keys:
            return [k for k in MODULES if k in keys]
        keys = kept


def refresh(condo) -> list:
    """Recompute and store a site's effective modules (after any subscription or plan change)."""
    from .models import Condominium

    sub = getattr(condo, "subscription", None)
    modules = effective_modules(sub) if sub else ["core"]
    if modules != condo.modules:
        Condominium.objects.filter(pk=condo.pk).update(modules=modules)
        condo.modules = modules
    return modules


def refresh_plan(plan):
    from .models import Condominium

    for condo in Condominium.objects.filter(subscription__plan=plan).select_related("subscription__plan"):
        refresh(condo)


def has(condo, module) -> bool:
    return module in (condo.modules or [])


def require(condo, module):
    if not has(condo, module):
        raise ModuleLocked(module)


LOCKED_STATUSES = ("suspended", "cancelled")


def setup_locked(condo) -> bool:
    """Suspended and cancelled sites keep running but their setup cannot change (platform admin excepted)."""
    sub = getattr(condo, "subscription", None)
    return sub is not None and sub.status in LOCKED_STATUSES


# --- Limits ------------------------------------------------------------------------------------------

def limits(condo) -> dict:
    """Limit key -> number (None: unlimited)."""
    sub = getattr(condo, "subscription", None)
    if sub is None:
        return {}
    return {**sub.plan.limits, **sub.limit_overrides}


def usage(condo) -> dict:
    """Current counts for the enforced limits."""
    from .models import AccessGate, Kiosk, LprCamera, StaffAssignment, Unit

    from . import usage as metering

    return {
        **metering.this_month(condo),
        "units": Unit.objects.filter(condominium=condo, is_active=True, is_office=False).count(),
        "kiosks": Kiosk.objects.filter(condominium=condo).count(),
        "gates": AccessGate.objects.filter(condominium=condo).count(),
        "lpr_cameras": LprCamera.objects.filter(gate__condominium=condo).count(),
        "staff_accounts": StaffAssignment.objects.filter(condominium=condo).values("user").distinct().count(),
    }


def check_limit(condo, key, adding=1):
    """Refuse to add ``adding`` more of ``key`` past the plan's limit (existing records are never touched)."""
    allowed = limits(condo).get(key)
    if allowed is None or not LIMITS[key].enforced:
        return
    if usage(condo)[key] + adding > allowed:
        raise LimitReached(key, allowed)


# --- New sites -----------------------------------------------------------------------------------------

# The starting plans (created by migration 0018; also here for empty test databases).
DEFAULT_PLANS = [
    ("basic", "Basic", "Kiosk and management dashboard.", ["core"], 10, True),
    ("standard", "Standard", "Adds the resident app, video intercom, facilities and advanced reports.",
     ["core", "resident_app", "intercom", "facilities", "advanced_reports"], 20, True),
    ("premium", "Premium", "Adds LPR, face check at the kiosk and the AI concierge.",
     ["core", "resident_app", "intercom", "facilities", "advanced_reports", "lpr", "face_kiosk", "ai_concierge"], 30, True),
    ("full", "Full", "Internal: every module, for sites that ran before plans existed.", list(MODULES), 90, False),
]


def ensure_default_plans():
    from .models import Plan

    for code, name, description, modules, order, public in DEFAULT_PLANS:
        Plan.objects.get_or_create(code=code, defaults={"name": name, "description": description, "modules": modules,
                                                        "sort_order": order, "is_public": public})


DEFAULT_PLAN = "standard"
TRIAL_DAYS = 30


def start_subscription(condo, plan=None, actor=None):
    """A new site starts a trial on ``plan`` (default Standard)."""
    from datetime import timedelta

    from .models import Plan, Subscription, SubscriptionEvent

    plan = plan or Plan.objects.filter(code=DEFAULT_PLAN).first() or Plan.objects.order_by("sort_order").first()
    if plan is None:
        return None
    sub, created = Subscription.objects.get_or_create(condominium=condo, defaults={
        "plan": plan, "status": Subscription.Status.TRIAL,
        "trial_ends_on": timezone.localdate() + timedelta(days=TRIAL_DAYS)})
    if created:
        SubscriptionEvent.objects.create(subscription=sub, actor=actor,
                                         summary=f"Trial started on {plan.name} until {sub.trial_ends_on:%d %b %Y}.")
    refresh(condo)
    return sub


def upsell_plan(module, plans) -> str:
    """Name of the first public plan that includes ``module``, for "Available in Standard" hints."""
    for plan in plans:
        if plan.is_public and plan.is_active and module in plan.modules:
            return plan.name
    return ""

