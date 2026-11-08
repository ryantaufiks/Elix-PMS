"""Walk-in visitors: register at the kiosk, get a slip with a daily pass number, scan it to check out."""
import base64
import io
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import qrcode
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Condominium, WalkInPass
from .realtime import broadcast


def local_day(condo, at=None):
    """The condominium's local date at ``at``, and the moment that day ends."""
    tz = ZoneInfo(condo.timezone or "Asia/Singapore")
    day = (at or timezone.now()).astimezone(tz).date()
    return day, datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz) - timedelta(seconds=1)


@transaction.atomic
def issue(kiosk, unit, purpose, name, company="", visitor=None, snapshot=None):
    condo = Condominium.objects.select_for_update().get(pk=kiosk.condominium_id)  # Serialises numbering.
    day, end = local_day(condo)
    prefix = WalkInPass.PREFIXES[purpose]
    last = (WalkInPass.objects.filter(condominium=condo, issued_on=day, pass_number__startswith=prefix)
            .aggregate(n=Max("sequence"))["n"] or 0)
    walk_in = WalkInPass(condominium=condo, unit=unit, kiosk=kiosk, visitor=visitor, visitor_name=name,
                         purpose=purpose, company=company, issued_on=day, sequence=last + 1,
                         pass_number=f"{prefix}{last + 1:03d}", valid_until=end)
    if snapshot is not None:
        walk_in.visitor_snapshot.save(f"walkin-{kiosk.pk}.jpg", snapshot, save=False)
    walk_in.save()
    _notify(walk_in)
    return walk_in


def find(condominium_id, code, lock=False):
    """The pass for what was scanned (the slip QR or the bare token), or None."""
    code = (code or "").strip()
    if not code.startswith(WalkInPass.QR_PREFIX):
        return None
    qs = WalkInPass.objects.select_related("unit__block")
    if lock:
        qs = qs.select_for_update(of=("self",))
    return qs.filter(condominium_id=condominium_id, token=code[len(WalkInPass.QR_PREFIX):]).first()


def is_walk_in_code(code):
    return (code or "").strip().startswith(WalkInPass.QR_PREFIX)


def check_out(walk_in, user=None):
    """Record the visitor leaving. Returns False if they had already checked out."""
    if walk_in.checked_out_at:
        return False
    walk_in.checked_out_at = timezone.now()
    walk_in.checked_out_by = user
    walk_in.save(update_fields=["checked_out_at", "checked_out_by", "updated_at"])
    _notify(walk_in)
    return True


def qr_data_uri(walk_in):
    buffer = io.BytesIO()
    qrcode.make(walk_in.qr_payload, box_size=8, border=2).save(buffer)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _notify(walk_in):
    def send():
        import logging

        from .serializers import WalkInPassSerializer

        try:
            broadcast(walk_in.condominium_id, None, "walk_in", WalkInPassSerializer(walk_in).data)
        except Exception:  # Redis trouble must not break registration.
            logging.getLogger(__name__).exception("Failed to broadcast walk-in %s", walk_in.pk)

    transaction.on_commit(send)
