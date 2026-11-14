"""Consolidated reports for staff: a daily summary, visits, access, vehicles, intercom and invitations.

Each report answers ``/v1/reports/<key>/`` with the KPIs, breakdowns and daily trend for the chosen
sites and period, plus the detail rows (paged as JSON, or every row as an Excel/CSV download). Staff
report on their own site; superusers can combine several or all sites.

Search is "smart": free words match any text column, and ``key:value`` tokens target one field,
e.g. ``unit:05-12 plate:SGX1234 status:denied "Ace Aircon"``.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncDate
from django.utils import timezone

from . import models as m
from .validators import normalize_plate

MAX_DAYS = 366
EXPORT_MAX_ROWS = 50_000
PRINT_MAX_ROWS = 5_000


class ReportError(Exception):
    pass


# --- Query helpers -----------------------------------------------------------------------------------

TOKEN = re.compile(r'(\w+):(?:"([^"]*)"|(\S+))|"([^"]*)"|(\S+)')


def parse_search(text):
    """``unit:05-12 "Ace Aircon" grab`` -> ([("unit", "05-12")], ["Ace Aircon", "grab"])."""
    tokens, words = [], []
    for key, quoted_value, value, quoted_word, word in TOKEN.findall(text or ""):
        if key:
            tokens.append((key.lower(), quoted_value or value))
        elif quoted_word or word:
            words.append(quoted_word or word)
    return tokens, words


def unit_q(prefix, value):
    """Match a unit written as ``#05-12``, ``05-12`` or ``12`` (house number)."""
    value = value.strip().lstrip("#")
    if "-" in value:
        floor, number = value.split("-", 1)
        return Q(**{f"{prefix}floor__iexact": floor, f"{prefix}unit_number__iexact": number}) | \
            Q(**{f"{prefix}floor__iexact": floor.lstrip("0") or "0", f"{prefix}unit_number__iexact": number})
    return Q(**{f"{prefix}unit_number__iexact": value})


def any_of(*lookups):
    """A token matcher: the value contained in any of these fields."""
    return lambda value: Q(*[Q(**{f"{lookup}__icontains": value}) for lookup in lookups], _connector=Q.OR)


def choice(field_name, choices):
    """A token matcher for a choice field: accepts the value or (a prefix of) its label."""
    def match(value):
        value = value.lower()
        hits = [key for key, label in choices if key == value or label.lower().startswith(value) or key.startswith(value)]
        return Q(**{f"{field_name}__in": hits}) if hits else Q(pk__in=[])
    return match


def plate(field_name):
    return lambda value: Q(**{f"{field_name}__icontains": normalize_plate(value)})


def person(prefix):
    return any_of(f"{prefix}__username", f"{prefix}__first_name", f"{prefix}__last_name")


def local(dt):
    return timezone.localtime(dt) if dt else None


def duration_text(delta):
    if delta is None:
        return ""
    minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def unit_text(unit):
    return str(unit) if unit else ""


def name_of(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def counts(qs, field_name, labels=None, limit=None):
    """[{label, value}] of ``qs`` grouped by ``field_name``, biggest first."""
    rows = qs.order_by().values(field_name).annotate(n=Count("pk")).order_by("-n")
    if limit:
        rows = rows[:limit]
    out = []
    for row in rows:
        key = row[field_name]
        label = labels.get(key, key) if labels else key
        out.append({"label": str(label) if label not in (None, "") else "—", "value": row["n"]})
    return out


def units(qs, prefix="unit", limit=10):
    rows = (qs.order_by().exclude(**{f"{prefix}__isnull": True})
            .values(f"{prefix}__block__name", f"{prefix}__floor", f"{prefix}__unit_number")
            .annotate(n=Count("pk")).order_by("-n")[:limit])
    out = []
    for row in rows:
        floor, number, block = row[f"{prefix}__floor"], row[f"{prefix}__unit_number"], row[f"{prefix}__block__name"]
        label = f"#{floor}-{number}" if floor else number
        out.append({"label": f"{block} {label}" if block else label, "value": row["n"]})
    return out


def hours(qs, field_name, limit=6):
    rows = (qs.order_by().annotate(h=ExtractHour(field_name, tzinfo=timezone.get_current_timezone()))
            .values("h").annotate(n=Count("pk")).order_by("-n")[:limit])
    return [{"label": f"{row['h']:02d}:00–{row['h']:02d}:59", "value": row["n"]} for row in rows]


def daily(qs, field_name, series):
    """{date: {series_key: n}} for the trend chart. ``series`` maps key -> Q filter (or None = all)."""
    out = {}
    for key, condition in series.items():
        rows = qs.order_by()
        if condition is not None:
            rows = rows.filter(condition)
        rows = rows.annotate(d=TruncDate(field_name, tzinfo=timezone.get_current_timezone())).values("d").annotate(n=Count("pk"))
        for row in rows:
            out.setdefault(row["d"], {})[key] = row["n"]
    return out


# Visit purposes as the three groups the guardhouse thinks in (also the dashboard's).
PURPOSE_GROUPS = {
    "guests": ("Guests", ("guest", "other")),
    "deliveries": ("Deliveries", ("delivery", "food", "pickup")),
    "contractors": ("Contractors", ("contractor",)),
}


def heatmap(qs, field_name):
    """Arrivals by weekday (Monday first) and local hour: 7 rows of 24 counts, for staffing the shifts."""
    grid = [[0] * 24 for _ in range(7)]
    tz = timezone.get_current_timezone()
    rows = (qs.order_by().annotate(wd=ExtractIsoWeekDay(field_name, tzinfo=tz), h=ExtractHour(field_name, tzinfo=tz))
            .values_list("wd", "h").annotate(n=Count("pk")))
    for weekday, hour, n in rows:
        grid[weekday - 1][hour] = n
    return grid


def stay_by_purpose(qs):
    """Average stay in minutes of visitors who checked out, per purpose group."""
    out = []
    stay = ExpressionWrapper(F("checked_out_at") - F("created_at"), output_field=DurationField())
    for key, (label, purposes) in PURPOSE_GROUPS.items():
        row = qs.filter(checked_out_at__isnull=False, purpose__in=purposes).aggregate(a=Avg(stay), n=Count("pk"))
        if row["n"]:
            out.append({"key": key, "label": label, "minutes": round(row["a"].total_seconds() / 60), "visits": row["n"]})
    return out


def purpose_trend(qs, period):
    """Visits per day split by purpose group, every day of the period."""
    first, last = period
    per_day = daily(qs, "created_at", {key: Q(purpose__in=purposes) for key, (_, purposes) in PURPOSE_GROUPS.items()})
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return {
        "series": [{"key": key, "label": label} for key, (label, _) in PURPOSE_GROUPS.items()],
        "points": [{"date": d.isoformat(), **{key: per_day.get(d, {}).get(key, 0) for key in PURPOSE_GROUPS}} for d in days],
    }


def kpi(key, label, value, kind="number"):
    return {"key": key, "label": label, "value": value, "kind": kind}


def percent(part, whole):
    return round(100 * part / whole, 1) if whole else None


# --- Report definitions ------------------------------------------------------------------------------

@dataclass
class Column:
    key: str
    label: str
    value: Callable
    kind: str = "text"  # text | datetime | number | badge
    width: int = 16


@dataclass
class Filter:
    name: str
    label: str
    options: list
    q: Callable  # value -> Q


@dataclass
class Report:
    key: str
    title: str
    description: str
    icon: str
    date_field: str
    columns: list
    filters: list = field(default_factory=list)
    tokens: dict = field(default_factory=dict)  # name -> (help, value -> Q)
    search_fields: tuple = ()
    landscape: bool = True

    def queryset(self, condo_ids):
        raise NotImplementedError

    def summary(self, qs, period):
        raise NotImplementedError

    def trend_series(self):
        raise NotImplementedError

    def filtered(self, condo_ids, start, end, params, search):
        qs = self.queryset(condo_ids).filter(**{f"{self.date_field}__gte": start, f"{self.date_field}__lt": end})
        for flt in self.filters:
            value = params.get(flt.name)
            if value:
                qs = qs.filter(flt.q(value))
        tokens, words = parse_search(search)
        unknown = []
        for key, value in tokens:
            if key in self.tokens and value:
                qs = qs.filter(self.tokens[key][1](value))
            else:
                unknown.append(f"{key}:{value}")
        for word in words + unknown:
            qs = qs.filter(Q(*[Q(**{f"{f}__icontains": word}) for f in self.search_fields], _connector=Q.OR))
        return qs.distinct() if tokens or words else qs

    def rows(self, qs, multi_site):
        cols = [c for c in self.columns if multi_site or c.key != "site"]
        return cols, ([c.value(obj) for c in cols] for obj in qs)

    def catalog(self):
        return {
            "key": self.key, "title": self.title, "description": self.description, "icon": self.icon,
            "landscape": self.landscape,
            "filters": [{"name": f.name, "label": f.label, "options": [{"value": v, "label": lbl} for v, lbl in f.options]}
                        for f in self.filters],
            "tokens": [{"key": k, "help": help_} for k, (help_, _) in self.tokens.items()],
        }


def site(obj):
    return obj.condominium.name


VISIT_STATE = {"on_site": "On site", "checked_out": "Checked out", "expired": "Not checked out"}


class VisitsReport(Report):
    def queryset(self, condo_ids):
        return m.Visit.objects.filter(condominium_id__in=condo_ids).select_related(
            "condominium", "unit__block", "gate", "kiosk", "created_by", "checked_out_by").order_by("-created_at")

    def trend_series(self):
        return [{"key": "visits", "label": "Visits"}, {"key": "not_out", "label": "Not checked out"}]

    def summary(self, qs, period):
        now = timezone.now()
        out = qs.filter(checked_out_at__isnull=False)
        total = qs.count()
        avg = out.aggregate(a=Avg(ExpressionWrapper(F("checked_out_at") - F("created_at"), output_field=DurationField())))["a"]
        on_site = qs.filter(checked_out_at__isnull=True, valid_until__gte=now).count()
        not_out = qs.filter(checked_out_at__isnull=True, valid_until__lt=now).count()
        return {
            "kpis": [
                kpi("total", "Total visits", total),
                kpi("checked_out", "Checked out", out.count()),
                kpi("on_site", "Still on site", on_site),
                kpi("not_out", "Not checked out", not_out),
                kpi("avg_duration", "Average stay", duration_text(avg), "text"),
                kpi("visitors", "Identified visitors", qs.exclude(visitor=None).values("visitor").distinct().count()),
            ],
            "breakdowns": [
                {"key": "purpose", "title": "By category", "rows": counts(qs, "purpose", dict(m.VisitPurpose.choices))},
                {"key": "source", "title": "By entry", "rows": counts(qs, "source", dict(m.Visit.Source.choices))},
                {"key": "units", "title": "Most visited units", "rows": units(qs)},
                {"key": "hours", "title": "Busiest hours", "rows": hours(qs, "created_at")},
            ],
            "trend": daily(qs, "created_at", {"visits": None, "not_out": Q(checked_out_at__isnull=True, valid_until__lt=now)}),
            "insights": {
                "heatmap": heatmap(qs, "created_at"),
                "stay_by_purpose": stay_by_purpose(qs),
                "purpose_trend": purpose_trend(qs, period),
            },
        }


def visit_state(visit):
    return VISIT_STATE[visit.state]


VISITS = VisitsReport(
    key="visits", title="Visitor report", icon="clipboard", date_field="created_at",
    description="Every visit with check-in and check-out time, stay, category, unit and how they came in.",
    columns=[
        Column("site", "Site", site, width=20),
        Column("pass", "Pass", lambda v: v.pass_number, width=8),
        Column("visitor", "Visitor", lambda v: v.visitor_name, width=22),
        Column("purpose", "Category", lambda v: v.get_purpose_display(), width=14),
        Column("company", "Company", lambda v: v.company, width=18),
        Column("plate", "Vehicle", lambda v: v.vehicle_plate, width=11),
        Column("unit", "Unit", lambda v: unit_text(v.unit), width=14),
        Column("source", "Entry", lambda v: v.get_source_display(), width=16),
        Column("check_in", "Check-in", lambda v: local(v.created_at), "datetime", 17),
        Column("check_out", "Check-out", lambda v: local(v.checked_out_at), "datetime", 17),
        Column("stay", "Stay", lambda v: duration_text(v.checked_out_at - v.created_at) if v.checked_out_at else "", width=9),
        Column("checked_out_by", "Checked out by", lambda v: name_of(v.checked_out_by) or ("Self / exit camera" if v.checked_out_at else ""), width=16),
        Column("status", "Status", visit_state, "badge", 14),
        Column("notes", "Notes", lambda v: v.notes, width=28),
    ],
    filters=[
        Filter("purpose", "Category", m.VisitPurpose.choices, lambda v: Q(purpose=v)),
        Filter("source", "Entry", m.Visit.Source.choices, lambda v: Q(source=v)),
        Filter("state", "Status", list(VISIT_STATE.items()), lambda v: {
            "on_site": Q(checked_out_at__isnull=True, valid_until__gte=timezone.now()),
            "checked_out": Q(checked_out_at__isnull=False),
            "expired": Q(checked_out_at__isnull=True, valid_until__lt=timezone.now()),
        }.get(v, Q())),
    ],
    tokens={
        "pass": ("Pass number, e.g. pass:V012", lambda v: Q(pass_number__iexact=v)),
        "name": ("Visitor name", any_of("visitor_name")),
        "unit": ("Unit, e.g. unit:05-12", lambda v: unit_q("unit__", v)),
        "block": ("Block name", any_of("unit__block__name")),
        "plate": ("Vehicle plate", plate("vehicle_plate")),
        "company": ("Company", any_of("company")),
        "category": ("visitor, contractor, delivery, food…", choice("purpose", m.VisitPurpose.choices)),
        "entry": ("kiosk, staff, invitation, intercom", choice("source", m.Visit.Source.choices)),
        "by": ("Staff who registered or checked out", lambda v: person("created_by")(v) | person("checked_out_by")(v)),
        "notes": ("Security notes", any_of("notes")),
    },
    search_fields=("pass_number", "visitor_name", "company", "vehicle_plate", "notes", "unit__unit_number", "unit__block__name"),
)


class AccessReport(Report):
    lpr_only = False

    def queryset(self, condo_ids):
        qs = m.AccessLog.objects.filter(condominium_id__in=condo_ids).select_related(
            "condominium", "gate", "unit__block", "actor", "visitor", "invitation", "vehicle__unit__block", "camera")
        return qs.order_by("-occurred_at")

    def trend_series(self):
        return [{"key": "granted", "label": "Granted"}, {"key": "denied", "label": "Denied"}, {"key": "error", "label": "Error"}]

    def summary(self, qs, period):
        total = qs.count()
        by_result = dict(qs.order_by().values_list("result").annotate(n=Count("pk")))
        granted = by_result.get("granted", 0)
        return {
            "kpis": [
                kpi("total", "Access events", total),
                kpi("granted", "Granted", granted),
                kpi("denied", "Denied", by_result.get("denied", 0)),
                kpi("error", "Errors", by_result.get("error", 0)),
                kpi("rate", "Grant rate", percent(granted, total), "percent"),
                kpi("plates", "Distinct plates", qs.exclude(plate_number="").values("plate_number").distinct().count()),
            ],
            "breakdowns": [
                {"key": "method", "title": "By method", "rows": counts(qs, "method", dict(m.AccessLog.Method.choices))},
                {"key": "gate", "title": "By gate", "rows": counts(qs, "gate__name")},
                {"key": "reasons", "title": "Top denial reasons", "rows": counts(qs.exclude(result="granted"), "reason", limit=8)},
                {"key": "hours", "title": "Busiest hours", "rows": hours(qs, "occurred_at")},
            ],
            "trend": daily(qs, "occurred_at", {"granted": Q(result="granted"), "denied": Q(result="denied"), "error": Q(result="error")}),
        }


def who(log):
    if log.visitor_id:
        return log.visitor.full_name
    if log.invitation_id:
        return log.invitation.visitor_name
    return ""


ACCESS = AccessReport(
    key="access", title="Access report", icon="list", date_field="occurred_at",
    description="Every gate decision: who or what came in, how, at which gate, and why anything was refused.",
    columns=[
        Column("site", "Site", site, width=20),
        Column("time", "Time", lambda log: local(log.occurred_at), "datetime", 17),
        Column("gate", "Gate", lambda log: log.gate.name if log.gate_id else "", width=16),
        Column("method", "Method", lambda log: log.get_method_display(), width=18),
        Column("result", "Result", lambda log: log.get_result_display(), "badge", 10),
        Column("reason", "Reason", lambda log: log.reason, width=30),
        Column("plate", "Plate", lambda log: log.plate_number, width=11),
        Column("unit", "Unit", lambda log: unit_text(log.unit), width=14),
        Column("visitor", "Visitor", who, width=20),
        Column("by", "Opened by", lambda log: name_of(log.actor), width=16),
    ],
    filters=[
        Filter("result", "Result", m.AccessLog.Result.choices, lambda v: Q(result=v)),
        Filter("method", "Method", m.AccessLog.Method.choices, lambda v: Q(method=v)),
    ],
    tokens={
        "gate": ("Gate name", any_of("gate__name")),
        "method": ("lpr, qr, intercom, app, manual, walk", choice("method", m.AccessLog.Method.choices)),
        "status": ("granted, denied, error", choice("result", m.AccessLog.Result.choices)),
        "plate": ("Vehicle plate", plate("plate_number")),
        "unit": ("Unit, e.g. unit:05-12", lambda v: unit_q("unit__", v)),
        "block": ("Block name", any_of("unit__block__name")),
        "reason": ("Reason text", any_of("reason")),
        "by": ("Staff or resident who opened", person("actor")),
        "name": ("Visitor name", any_of("visitor__full_name", "invitation__visitor_name")),
    },
    search_fields=("reason", "plate_number", "gate__name", "visitor__full_name", "invitation__visitor_name",
                   "actor__username", "actor__first_name", "actor__last_name", "unit__unit_number"),
)


VEHICLE_KIND = {"resident": "Resident", "visitor": "Visitor (invited)", "unknown": "Unknown"}


def vehicle_kind(log):
    return "resident" if log.vehicle_id else "visitor" if log.invitation_id else "unknown"


class VehicleReport(AccessReport):
    def queryset(self, condo_ids):
        return super().queryset(condo_ids).exclude(plate_number="")

    def trend_series(self):
        return [{"key": "resident", "label": "Resident"}, {"key": "visitor", "label": "Visitor"}, {"key": "unknown", "label": "Unknown"}]

    def summary(self, qs, period):
        resident, visitor = Q(vehicle__isnull=False), Q(vehicle__isnull=True, invitation__isnull=False)
        unknown = Q(vehicle__isnull=True, invitation__isnull=True)
        by_kind = [{"label": VEHICLE_KIND[k], "value": qs.filter(q).count()} for k, q in
                   (("resident", resident), ("visitor", visitor), ("unknown", unknown))]
        return {
            "kpis": [
                kpi("total", "Plate reads", qs.count()),
                kpi("plates", "Distinct plates", qs.values("plate_number").distinct().count()),
                kpi("resident", "Resident", by_kind[0]["value"]),
                kpi("visitor", "Invited visitors", by_kind[1]["value"]),
                kpi("unknown", "Unknown", by_kind[2]["value"]),
                kpi("denied", "Denied", qs.exclude(result="granted").count()),
            ],
            "breakdowns": [
                {"key": "kind", "title": "By vehicle", "rows": by_kind},
                {"key": "plates", "title": "Most frequent plates", "rows": counts(qs, "plate_number", limit=10)},
                {"key": "unknown", "title": "Unknown plates", "rows": counts(qs.filter(unknown), "plate_number", limit=10)},
                {"key": "gate", "title": "By gate", "rows": counts(qs, "gate__name")},
            ],
            "trend": daily(qs, "occurred_at", {"resident": resident, "visitor": visitor, "unknown": unknown}),
        }


VEHICLES = VehicleReport(
    key="vehicles", title="Vehicle report", icon="car", date_field="occurred_at",
    description="Licence-plate reads: resident, invited and unknown vehicles, entries and exits, refusals.",
    columns=[
        Column("site", "Site", site, width=20),
        Column("time", "Time", lambda log: local(log.occurred_at), "datetime", 17),
        Column("plate", "Plate", lambda log: log.plate_number, width=11),
        Column("kind", "Vehicle", lambda log: VEHICLE_KIND[vehicle_kind(log)], width=16),
        Column("owner", "Unit / visitor", lambda log: unit_text(log.vehicle.unit) if log.vehicle_id else (
            log.invitation.visitor_name if log.invitation_id else ""), width=20),
        Column("gate", "Gate", lambda log: log.gate.name if log.gate_id else "", width=16),
        Column("direction", "Direction", lambda log: log.camera.get_direction_display() if log.camera_id else "", width=11),
        Column("result", "Result", lambda log: log.get_result_display(), "badge", 10),
        Column("reason", "Reason", lambda log: log.reason, width=30),
    ],
    filters=[
        Filter("kind", "Vehicle", list(VEHICLE_KIND.items()), lambda v: {
            "resident": Q(vehicle__isnull=False), "visitor": Q(vehicle__isnull=True, invitation__isnull=False),
            "unknown": Q(vehicle__isnull=True, invitation__isnull=True)}.get(v, Q())),
        Filter("direction", "Direction", [("entry", "Entry"), ("exit", "Exit")], lambda v: Q(camera__direction=v)),
        Filter("result", "Result", m.AccessLog.Result.choices, lambda v: Q(result=v)),
    ],
    tokens={
        "plate": ("Vehicle plate", plate("plate_number")),
        "gate": ("Gate name", any_of("gate__name")),
        "status": ("granted, denied, error", choice("result", m.AccessLog.Result.choices)),
        "unit": ("Resident's unit, e.g. unit:05-12", lambda v: unit_q("vehicle__unit__", v) | unit_q("unit__", v)),
        "reason": ("Reason text", any_of("reason")),
    },
    search_fields=("plate_number", "reason", "gate__name", "invitation__visitor_name"),
)


class IntercomReport(Report):
    def queryset(self, condo_ids):
        return m.IntercomCall.objects.filter(condominium_id__in=condo_ids).select_related(
            "condominium", "unit__block", "kiosk", "answered_by", "decided_by").order_by("-created_at")

    def trend_series(self):
        return [{"key": "approved", "label": "Approved"}, {"key": "missed", "label": "Missed"}, {"key": "other", "label": "Other"}]

    def summary(self, qs, period):
        total = qs.count()
        by_status = dict(qs.order_by().values_list("status").annotate(n=Count("pk")))
        answered = qs.filter(answered_at__isnull=False)
        wait = answered.aggregate(a=Avg(ExpressionWrapper(F("answered_at") - F("created_at"), output_field=DurationField())))["a"]
        return {
            "kpis": [
                kpi("total", "Calls", total),
                kpi("approved", "Gate opened", by_status.get("approved", 0)),
                kpi("rejected", "Declined", by_status.get("rejected", 0)),
                kpi("missed", "Missed", by_status.get("missed", 0)),
                kpi("answer_rate", "Answer rate", percent(answered.count(), total), "percent"),
                kpi("wait", "Average time to answer", f"{round(wait.total_seconds())} s" if wait else "", "text"),
            ],
            "breakdowns": [
                {"key": "status", "title": "By outcome", "rows": counts(qs, "status", dict(m.IntercomCall.Status.choices))},
                {"key": "purpose", "title": "By category", "rows": counts(qs, "visitor_purpose", dict(m.VisitPurpose.choices))},
                {"key": "units", "title": "Most called units", "rows": units(qs)},
                {"key": "hours", "title": "Busiest hours", "rows": hours(qs, "created_at")},
            ],
            "trend": daily(qs, "created_at", {"approved": Q(status="approved"), "missed": Q(status="missed"),
                                              "other": ~Q(status__in=["approved", "missed"])}),
        }


INTERCOM = IntercomReport(
    key="intercom", title="Intercom report", icon="phone", date_field="created_at",
    description="Kiosk calls to residents: answered, opened, declined or missed, and how fast residents answer.",
    columns=[
        Column("site", "Site", site, width=20),
        Column("time", "Time", lambda c: local(c.created_at), "datetime", 17),
        Column("unit", "Unit", lambda c: unit_text(c.unit), width=14),
        Column("visitor", "Visitor", lambda c: c.visitor_name, width=20),
        Column("purpose", "Category", lambda c: c.get_visitor_purpose_display() if c.visitor_purpose else "", width=14),
        Column("company", "Company", lambda c: c.visitor_company, width=16),
        Column("kiosk", "Kiosk", lambda c: c.kiosk.name if c.kiosk_id else "", width=14),
        Column("status", "Outcome", lambda c: c.get_status_display(), "badge", 16),
        Column("answered_by", "Answered by", lambda c: name_of(c.answered_by), width=16),
        Column("wait", "Answered after", lambda c: f"{round((c.answered_at - c.created_at).total_seconds())} s" if c.answered_at else "", width=10),
    ],
    filters=[
        Filter("status", "Outcome", m.IntercomCall.Status.choices, lambda v: Q(status=v)),
        Filter("purpose", "Category", m.VisitPurpose.choices, lambda v: Q(visitor_purpose=v)),
    ],
    tokens={
        "unit": ("Unit, e.g. unit:05-12", lambda v: unit_q("unit__", v)),
        "block": ("Block name", any_of("unit__block__name")),
        "name": ("Visitor name", any_of("visitor_name")),
        "company": ("Company", any_of("visitor_company")),
        "status": ("approved, rejected, missed, cancelled…", choice("status", m.IntercomCall.Status.choices)),
        "kiosk": ("Kiosk name", any_of("kiosk__name")),
        "by": ("Resident or guard who answered", lambda v: person("answered_by")(v) | person("decided_by")(v)),
    },
    search_fields=("visitor_name", "visitor_company", "kiosk__name", "unit__unit_number", "unit__block__name"),
)


class InvitationReport(Report):
    def queryset(self, condo_ids):
        return m.Invitation.objects.filter(condominium_id__in=condo_ids).select_related(
            "condominium", "unit__block", "host").order_by("-created_at")

    def trend_series(self):
        return [{"key": "created", "label": "Created"}, {"key": "used", "label": "Used"}]

    def summary(self, qs, period):
        by_status = dict(qs.order_by().values_list("status").annotate(n=Count("pk")))
        used = qs.filter(entry_count__gt=0).count()
        total = qs.count()
        return {
            "kpis": [
                kpi("total", "Invitations", total),
                kpi("used", "Used", used),
                kpi("use_rate", "Use rate", percent(used, total), "percent"),
                kpi("active", "Active", by_status.get("active", 0)),
                kpi("expired", "Expired", by_status.get("expired", 0)),
                kpi("cancelled", "Cancelled", by_status.get("cancelled", 0)),
            ],
            "breakdowns": [
                {"key": "status", "title": "By status", "rows": counts(qs, "status", dict(m.Invitation.Status.choices))},
                {"key": "purpose", "title": "By category", "rows": counts(qs, "purpose", dict(m.VisitPurpose.choices))},
                {"key": "units", "title": "Most inviting units", "rows": units(qs)},
            ],
            "trend": daily(qs, "created_at", {"created": None, "used": Q(entry_count__gt=0)}),
        }


INVITATIONS = InvitationReport(
    key="invitations", title="Invitation report", icon="ticket", date_field="created_at",
    description="Invitations residents created: who was invited, validity, how many entries were used.",
    columns=[
        Column("site", "Site", site, width=20),
        Column("created", "Created", lambda i: local(i.created_at), "datetime", 17),
        Column("visitor", "Visitor", lambda i: i.visitor_name, width=20),
        Column("purpose", "Category", lambda i: i.get_purpose_display(), width=14),
        Column("unit", "Unit", lambda i: unit_text(i.unit), width=14),
        Column("host", "Host", lambda i: name_of(i.host), width=16),
        Column("valid_from", "Valid from", lambda i: local(i.valid_from), "datetime", 17),
        Column("valid_until", "Valid until", lambda i: local(i.valid_until), "datetime", 17),
        Column("entries", "Entries", lambda i: f"{i.entry_count}/{i.max_entries or '∞'}", width=8),
        Column("plate", "Vehicle", lambda i: i.vehicle_plate, width=11),
        Column("status", "Status", lambda i: i.get_status_display(), "badge", 11),
    ],
    filters=[
        Filter("status", "Status", m.Invitation.Status.choices, lambda v: Q(status=v)),
        Filter("purpose", "Category", m.VisitPurpose.choices, lambda v: Q(purpose=v)),
    ],
    tokens={
        "name": ("Visitor name", any_of("visitor_name")),
        "unit": ("Unit, e.g. unit:05-12", lambda v: unit_q("unit__", v)),
        "block": ("Block name", any_of("unit__block__name")),
        "host": ("Resident who invited", person("host")),
        "plate": ("Vehicle plate", plate("vehicle_plate")),
        "status": ("active, completed, cancelled, expired", choice("status", m.Invitation.Status.choices)),
        "category": ("visitor, contractor, delivery…", choice("purpose", m.VisitPurpose.choices)),
    },
    search_fields=("visitor_name", "visitor_phone", "vehicle_plate", "notes", "host__first_name", "host__last_name",
                   "unit__unit_number", "unit__block__name"),
)


@dataclass
class DayRow:
    """One site on one day, for the consolidated summary."""

    condominium: object
    day: date
    values: dict


SUMMARY_METRICS = [
    ("visits", "Visits"), ("walk_ins", "Walk-ins"), ("not_out", "Not checked out"), ("granted", "Entries granted"),
    ("denied", "Denied"), ("errors", "Errors"), ("calls", "Intercom calls"), ("missed", "Missed calls"),
    ("invitations", "Invitations"),
]


class SummaryReport(Report):
    """Not a queryset report: rows are built per site and day from every source."""

    def queryset(self, condo_ids):
        return m.Condominium.objects.filter(pk__in=condo_ids).order_by("name")

    def trend_series(self):
        return [{"key": "visits", "label": "Visits"}, {"key": "granted", "label": "Entries granted"}, {"key": "denied", "label": "Denied"}]

    def collect(self, condo_ids, start, end):
        now = timezone.now()
        tz = timezone.get_current_timezone()
        sources = {
            "visits": (m.Visit.objects, "created_at", Q()),
            "walk_ins": (m.Visit.objects, "created_at", Q(source__in=["kiosk", "staff"])),
            "not_out": (m.Visit.objects, "created_at", Q(checked_out_at__isnull=True, valid_until__lt=now)),
            "granted": (m.AccessLog.objects, "occurred_at", Q(result="granted")),
            "denied": (m.AccessLog.objects, "occurred_at", Q(result="denied")),
            "errors": (m.AccessLog.objects, "occurred_at", Q(result="error")),
            "calls": (m.IntercomCall.objects, "created_at", Q()),
            "missed": (m.IntercomCall.objects, "created_at", Q(status="missed")),
            "invitations": (m.Invitation.objects, "created_at", Q()),
        }
        data = {}
        for key, (manager, date_field, condition) in sources.items():
            rows = (manager.filter(condition, condominium_id__in=condo_ids,
                                   **{f"{date_field}__gte": start, f"{date_field}__lt": end})
                    .annotate(d=TruncDate(date_field, tzinfo=tz)).values("condominium_id", "d").annotate(n=Count("pk"))
                    .order_by())
            for row in rows:
                data.setdefault((row["condominium_id"], row["d"]), {})[key] = row["n"]
        return data

    def filtered(self, condo_ids, start, end, params, search):
        condos = {c.pk: c for c in self.queryset(condo_ids)}
        tokens, words = parse_search(search)
        needles = [w.lower() for w in words] + [v.lower() for k, v in tokens if k == "site"]
        if needles:
            condos = {pk: c for pk, c in condos.items() if all(n in c.name.lower() for n in needles)}
        data = self.collect(list(condos), start, end)
        rows = [DayRow(condos[pk], day, {k: values.get(k, 0) for k, _ in SUMMARY_METRICS})
                for (pk, day), values in data.items() if pk in condos]
        rows.sort(key=lambda r: (-r.day.toordinal(), r.condominium.name))
        return rows

    def summary(self, rows, period):
        totals = {k: sum(r.values[k] for r in rows) for k, _ in SUMMARY_METRICS}
        by_site = {}
        for r in rows:
            by_site[r.condominium.name] = by_site.get(r.condominium.name, 0) + r.values["visits"]
        trend = {}
        for r in rows:
            point = trend.setdefault(r.day, {})
            for key in ("visits", "granted", "denied"):
                point[key] = point.get(key, 0) + r.values[key]
        return {
            "kpis": [
                kpi("visits", "Visits", totals["visits"]),
                kpi("not_out", "Not checked out", totals["not_out"]),
                kpi("granted", "Entries granted", totals["granted"]),
                kpi("denied", "Denied", totals["denied"]),
                kpi("calls", "Intercom calls", totals["calls"]),
                kpi("invitations", "Invitations", totals["invitations"]),
            ],
            "breakdowns": [
                {"key": "totals", "title": "Period totals", "rows": [{"label": label, "value": totals[k]} for k, label in SUMMARY_METRICS]},
                *([{"key": "sites", "title": "Visits by site", "rows": sorted(
                    ({"label": k, "value": v} for k, v in by_site.items()), key=lambda r: -r["value"])}] if len(by_site) > 1 else []),
            ],
            "trend": trend,
        }


SUMMARY = SummaryReport(
    key="summary", title="Consolidated summary", icon="grid", date_field="",
    description="One line per site and day: visits, entries, refusals, intercom calls and invitations together.",
    columns=[
        Column("site", "Site", lambda r: r.condominium.name, width=22),
        Column("date", "Date", lambda r: r.day, "date", 12),
        *[Column(key, label, (lambda k: lambda r: r.values[k])(key), "number", 11) for key, label in SUMMARY_METRICS],
    ],
    tokens={"site": ("Site name", None)},
    landscape=True,
)

REPORTS = {r.key: r for r in (SUMMARY, VISITS, ACCESS, VEHICLES, INTERCOM, INVITATIONS)}


# --- Running a report --------------------------------------------------------------------------------

def period(params):
    """(first day, last day, start, end) in local time; defaults to the last 7 days."""
    today = timezone.localdate()
    try:
        last = date.fromisoformat(params.get("date_to")) if params.get("date_to") else today
        first = date.fromisoformat(params.get("date_from")) if params.get("date_from") else last - timedelta(days=6)
    except ValueError:
        raise ReportError("Dates must be YYYY-MM-DD.")
    if first > last:
        raise ReportError("The start date is after the end date.")
    if (last - first).days >= MAX_DAYS:
        raise ReportError(f"Choose a period of at most {MAX_DAYS} days.")
    tz = timezone.get_current_timezone()
    start = datetime.combine(first, time.min, tzinfo=tz)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    return first, last, start, end


def run(report, condos, params):
    first, last, start, end = period(params)
    condo_ids = [c.pk for c in condos]
    rows = report.filtered(condo_ids, start, end, params, params.get("q", ""))
    summary = report.summary(rows, (first, last))
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    series = report.trend_series()
    summary["trend"] = {
        "series": series,
        "points": [{"date": d.isoformat(), **{s["key"]: summary["trend"].get(d, {}).get(s["key"], 0) for s in series}} for d in days],
    }
    return rows, summary, (first, last)


def _cell(value, kind):
    if value is None:
        return ""
    if kind == "datetime":
        return value.isoformat()
    if kind == "date":
        return value.isoformat()
    return value


def json_rows(report, rows, multi_site):
    cols, values = report.rows(rows, multi_site)
    return ([{"key": c.key, "label": c.label, "kind": c.kind} for c in cols],
            [{c.key: _cell(v, c.kind) for c, v in zip(cols, row)} for row in values])


def described_filters(report, params):
    out = []
    for flt in report.filters:
        value = params.get(flt.name)
        if value:
            out.append({"label": flt.label, "value": dict(flt.options).get(value, value)})
    if params.get("q"):
        out.append({"label": "Search", "value": params["q"]})
    return out


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def defuse(value):
    """Text typed by visitors (e.g. a name of ``=HYPERLINK(...)``) must not run as a spreadsheet formula."""
    return f"'{value}" if isinstance(value, str) and value.startswith(FORMULA_START) else value


def _plain(value, kind):
    if value is None:
        return ""
    if kind == "datetime":
        return value.strftime("%d %b %Y %H:%M")
    if kind == "date":
        return value.strftime("%d %b %Y")
    return value


def to_csv(report, rows, multi_site):
    cols, values = report.rows(rows, multi_site)
    buffer = io.StringIO()
    buffer.write("﻿")  # Excel opens UTF-8 CSV correctly with a BOM.
    writer = csv.writer(buffer)
    writer.writerow([c.label for c in cols])
    for row in values:
        writer.writerow([defuse(_plain(v, c.kind)) for c, v in zip(cols, row)])
    return buffer.getvalue().encode("utf-8")


def to_xlsx(report, rows, summary, meta, multi_site):
    """A Summary sheet (title, period, filters, KPIs, breakdowns) and a Details sheet with every row."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import Cell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    navy, light = PatternFill("solid", fgColor="0B1B3F"), PatternFill("solid", fgColor="EEF2FA")
    white_bold, bold = Font(bold=True, color="FFFFFF"), Font(bold=True)
    wb = Workbook(write_only=True)

    sheet = wb.create_sheet("Summary")
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 18

    def cell(ws, value, font=None, fill=None, fmt=None, align=None):
        c = WriteOnlyCell(ws, value=value)
        if c.data_type == "f":  # openpyxl treats any text starting with "=" as a formula.
            c.data_type = "s"
        if font:
            c.font = font
        if fill:
            c.fill = fill
        if fmt:
            c.number_format = fmt
        if align:
            c.alignment = align
        return c

    def put(ws, values):
        """Every value goes through ``cell`` so text can never become a formula."""
        ws.append([v if isinstance(v, Cell) else cell(ws, v) for v in values])

    put(sheet, [cell(sheet, report.title, Font(bold=True, size=16, color="0B1B3F"))])
    put(sheet, [cell(sheet, "Site(s)", bold), ", ".join(meta["sites"])])
    put(sheet, [cell(sheet, "Period", bold), meta["period_label"]])
    put(sheet, [cell(sheet, "Generated", bold), f"{meta['generated_at']:%d %b %Y %H:%M} by {meta['generated_by']}"])
    for f in meta["filters"]:
        put(sheet, [cell(sheet, f["label"], bold), f["value"]])
    put(sheet, [])
    put(sheet, [cell(sheet, "Key figures", white_bold, navy), cell(sheet, "", white_bold, navy)])
    for k in summary["kpis"]:
        value = k["value"]
        if k["kind"] == "percent":
            value = "" if value is None else f"{value}%"
        put(sheet, [k["label"], cell(sheet, value, bold, align=Alignment(horizontal="right"))])
    for b in summary["breakdowns"]:
        if not b["rows"]:
            continue
        put(sheet, [])
        put(sheet, [cell(sheet, b["title"], white_bold, navy), cell(sheet, "Count", white_bold, navy, align=Alignment(horizontal="right"))])
        for r in b["rows"]:
            put(sheet, [r["label"], r["value"]])
    put(sheet, [])
    put(sheet, [cell(sheet, "Daily trend", white_bold, navy), *[cell(sheet, s["label"], white_bold, navy) for s in summary["trend"]["series"]]])
    for p in summary["trend"]["points"]:
        put(sheet, [cell(sheet, date.fromisoformat(p["date"]), fmt="dd mmm yyyy", align=Alignment(horizontal="left")),
                      *[p[s["key"]] for s in summary["trend"]["series"]]])

    details = wb.create_sheet("Details")
    cols, values = report.rows(rows, multi_site)
    for i, c in enumerate(cols, start=1):
        details.column_dimensions[get_column_letter(i)].width = c.width
    details.freeze_panes = "A2"
    details.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"
    put(details, [cell(details, c.label, white_bold, navy) for c in cols])
    formats = {"datetime": "dd mmm yyyy hh:mm", "date": "dd mmm yyyy"}
    for n, row in enumerate(values):
        fill = light if n % 2 else None
        out = []
        for c, v in zip(cols, row):
            if c.kind == "datetime" and v is not None:
                v = v.replace(tzinfo=None)
            out.append(cell(details, "" if v is None else v, fill=fill, fmt=formats.get(c.kind)))
        put(details, out)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

