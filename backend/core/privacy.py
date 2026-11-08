"""PDPA: retention-based purging of visitor personal data, and erasure on request.

After a condominium's ``visitor_data_retention_days``:
- intercom calls lose the visitor's name, company and photo (the call record itself stays);
- access-log entries lose camera snapshots and raw camera payloads, and visitor plates
  (registered resident vehicles keep theirs);
- ended invitations lose the visitor's name, phone and plate;
- walk-in passes lose the visitor's name, company and photo (the pass number and times stay);
- visitor records not seen since are deleted, except blacklisted ones (kept for security).
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AccessLog, Condominium, IntercomCall, Invitation, Visitor, WalkInPass

REMOVED = "(removed)"


class _Purge:
    """Applies (or, in a dry run, only counts) each step."""

    def __init__(self, dry_run):
        self.dry_run = dry_run

    def files(self, queryset, field):
        rows = queryset.exclude(**{field: ""})
        if self.dry_run:
            return rows.count()
        count = 0
        for obj in rows.only("pk", field).iterator():
            getattr(obj, field).delete(save=False)
            count += 1
        rows.update(**{field: ""})
        return count

    def update(self, queryset, **values):
        return queryset.count() if self.dry_run else queryset.update(**values)

    def delete(self, queryset):
        if self.dry_run:
            return queryset.count()
        self.files(queryset, "face_photo")
        return queryset.delete()[1].get("core.Visitor", 0)

    def calls(self, calls):
        return {
            "call_photos": self.files(calls, "visitor_snapshot"),
            "calls": self.update(calls.exclude(visitor_name="", visitor_company="", visitor__isnull=True),
                                 visitor_name="", visitor_company="", visitor=None),
        }

    def walk_ins(self, passes):
        return {
            "walk_in_photos": self.files(passes, "visitor_snapshot"),
            "walk_ins": self.update(passes.exclude(visitor_name=REMOVED), visitor_name=REMOVED, company="", visitor=None),
        }


def purge_condominium(condo, now=None, dry_run=False):
    p = _Purge(dry_run)
    cutoff = (now or timezone.now()) - timedelta(days=condo.visitor_data_retention_days)
    with transaction.atomic():
        counts = p.calls(IntercomCall.objects.filter(condominium=condo, created_at__lt=cutoff))
        counts.update(p.walk_ins(WalkInPass.objects.filter(condominium=condo, created_at__lt=cutoff)))
        logs = AccessLog.objects.filter(condominium=condo, occurred_at__lt=cutoff)
        counts["log_photos"] = p.files(logs, "snapshot")
        counts["log_payloads"] = p.update(logs.exclude(raw_payload={}), raw_payload={})
        counts["visitor_plates"] = p.update(logs.filter(vehicle__isnull=True).exclude(plate_number=""), plate_number="")
        counts["invitations"] = p.update(
            Invitation.objects.filter(condominium=condo, valid_until__lt=cutoff).exclude(visitor_name=REMOVED),
            visitor_name=REMOVED, visitor_phone="", vehicle_plate="", notes="", visitor=None)
        counts["visitors"] = p.delete(Visitor.objects.filter(condominium=condo, is_blacklisted=False).filter(
            Q(last_visit_at__lt=cutoff) | Q(last_visit_at__isnull=True, created_at__lt=cutoff)))
    return counts


def purge_all(now=None, dry_run=False):
    return {condo.code: purge_condominium(condo, now, dry_run) for condo in Condominium.objects.all()}


@transaction.atomic
def erase_visitor(visitor):
    """A visitor asked to be forgotten: remove their photos and details everywhere, then the record."""
    p = _Purge(dry_run=False)
    p.calls(IntercomCall.objects.filter(visitor=visitor))
    p.walk_ins(WalkInPass.objects.filter(visitor=visitor))
    p.files(AccessLog.objects.filter(visitor=visitor), "snapshot")
    visitor.invitations.update(visitor_name=REMOVED, visitor_phone="", visitor=None)
    if visitor.face_photo:
        visitor.face_photo.delete(save=False)
    visitor.delete()
