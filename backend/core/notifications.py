"""The resident's notification feed, built from what already happened at their units (nothing extra is stored).

One event is one notification: a visitor's arrival is the visit, not also the gate opening and the call
that let them in, so gate entries linked to a call or an invitation are left out.
"""
from datetime import timedelta

from django.utils import timezone

from . import models as m
from .scoping import resident_unit_ids

DAYS = 30
METHODS = {"lpr": "Number plate", "qr": "QR code", "intercom": "Intercom", "app": "Elix app", "manual": "Security", "walk_in": "Walk-in"}
BOOKING = {
    m.Booking.Status.CONFIRMED: ("booking_confirmed", "Booking confirmed"),
    m.Booking.Status.CANCELLED: ("booking_cancelled", "Booking cancelled"),
    m.Booking.Status.EXPIRED: ("booking_expired", "Booking payment expired"),
}


def _who(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def _sources(user, since):
    """(queryset, timestamp field, row -> notification) for every kind of event."""
    units = resident_unit_ids(user)
    visits = m.Visit.objects.filter(unit__in=units).select_related("unit__block")
    gates = (m.AccessLog.objects.filter(unit__in=units, intercom_call__isnull=True, invitation__isnull=True)
             .select_related("gate", "actor"))
    bookings = m.Booking.objects.filter(unit__in=units).select_related("facility")

    def arrived(v):
        return "visit_in", f"{v.visitor_name or 'A visitor'} arrived", f"Pass {v.pass_number} · {v.get_source_display()}", v.created_at

    def left(v):
        return "visit_out", f"{v.visitor_name or 'Your visitor'} left", f"Pass {v.pass_number}", v.checked_out_at

    def gate(a):
        how = " · ".join(s for s in (METHODS.get(a.method, a.method), a.plate_number, _who(a.actor)) if s)
        if a.result == m.AccessLog.Result.GRANTED:
            return "gate_open", f"{a.gate.name if a.gate else 'Gate'} opened", how, a.occurred_at
        return "gate_denied", f"Entry refused at {a.gate.name if a.gate else 'the gate'}", " · ".join(s for s in (how, a.reason) if s), a.occurred_at

    def missed(c):
        return "call_missed", "Missed visitor call", " · ".join(s for s in (c.visitor_name, c.kiosk.name if c.kiosk else "") if s), c.created_at

    def booking(b):
        kind, title = BOOKING[b.status]
        return kind, title, f"{b.facility.name} · {timezone.localtime(b.starts_at):%a %d %b, %H:%M}", b.updated_at

    def replied(f):
        return "feedback_reply", "The management replied to your feedback", f.reply[:140], f.replied_at

    return [
        ("visit_in", visits.filter(created_at__gte=since), "created_at", arrived),
        ("visit_out", visits.filter(checked_out_at__gte=since), "checked_out_at", left),
        ("gate", gates.filter(occurred_at__gte=since), "occurred_at", gate),
        ("call", m.IntercomCall.objects.filter(unit__in=units, status=m.IntercomCall.Status.MISSED, created_at__gte=since)
         .select_related("kiosk"), "created_at", missed),
        ("booking", bookings.filter(status__in=BOOKING, updated_at__gte=since), "updated_at", booking),
        ("feedback", m.Feedback.objects.filter(user=user, replied_at__gte=since), "replied_at", replied),
    ]


def page(user, number, size):
    """(total, notifications on page ``number``), newest first, over the last 30 days."""
    since = timezone.now() - timedelta(days=DAYS)
    sources = _sources(user, since)
    wanted = number * size
    total, rows = 0, []
    for name, qs, field, build in sources:
        total += qs.count()
        for row in qs.order_by(f"-{field}")[:wanted]:
            kind, title, body, at = build(row)
            rows.append({"id": f"{name}:{row.pk}", "kind": kind, "title": title, "body": body, "at": at})
    rows.sort(key=lambda n: n["at"], reverse=True)
    return total, rows[wanted - size:wanted]
