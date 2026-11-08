"""Remembering returning visitors at a kiosk, without letting the kiosk be used to look people up.

A visitor identifies with their mobile number or the last 4 characters of their NRIC/FIN. The kiosk
only ever sees a masked name ("B*** T***") plus a short-lived signed reference to the record, so
typing someone else's number does not reveal who they are.
"""
import re

import phonenumbers
from django.core import signing
from django.utils import timezone

from .models import Visitor

ID_PARTIAL_RE = re.compile(r"^\d{3}[A-Z]$")
_SALT = "kiosk-visitor"
REF_MAX_AGE = 15 * 60


class InvalidIdentity(ValueError):
    pass


def normalize_phone(raw):
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        number = phonenumbers.parse(raw, "SG")
    except phonenumbers.NumberParseException as exc:
        raise InvalidIdentity("Enter a valid mobile number.") from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidIdentity("Enter a valid mobile number.")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def normalize_id_partial(raw):
    value = (raw or "").strip().upper().replace(" ", "")
    if value and not ID_PARTIAL_RE.match(value):
        raise InvalidIdentity("Enter the last 3 digits and the letter of your NRIC/FIN, e.g. 567A.")
    return value


def mask_name(name):
    return " ".join(f"{word[0]}***" for word in (name or "").split() if word) or "***"


def find_returning(condominium_id, phone="", id_partial=""):
    """The visitor matching a mobile number, or a partial NRIC/FIN that only one visitor has."""
    qs = Visitor.objects.filter(condominium_id=condominium_id)
    if phone:
        return qs.filter(phone=phone).order_by("-last_visit_at", "-created_at").first()
    if id_partial:
        matches = list(qs.filter(id_partial=id_partial)[:2])
        return matches[0] if len(matches) == 1 else None
    return None


def make_ref(kiosk, visitor):
    return signing.dumps({"v": visitor.pk, "k": kiosk.pk}, salt=_SALT, compress=True)


def visitor_from_ref(kiosk, ref):
    try:
        data = signing.loads(ref, salt=_SALT, max_age=REF_MAX_AGE)
    except signing.BadSignature:
        return None
    if data.get("k") != kiosk.pk:
        return None
    return Visitor.objects.filter(pk=data.get("v"), condominium_id=kiosk.condominium_id).first()


def record_visit(kiosk=None, *, condominium_id=None, ref="", name="", phone="", id_partial="", company="",
                 consent=False):
    """Create or update the visitor record for a visit at a kiosk (or, with ``condominium_id``, the
    guardhouse). Returns the Visitor (or None if nothing to record)."""
    now = timezone.now()
    condominium_id = condominium_id or kiosk.condominium_id
    visitor = visitor_from_ref(kiosk, ref) if ref and kiosk else None
    if visitor is None and (phone or id_partial):
        visitor = find_returning(condominium_id, phone, id_partial)
        if visitor is not None and name and visitor.full_name.lower() != name.lower():
            visitor = None  # Same number, different person (e.g. a shared company phone): keep records apart.
    if visitor is None:
        if not name:
            return None
        visitor = Visitor(condominium_id=condominium_id, full_name=name)
    if name and not visitor.pk:
        visitor.full_name = name
    if phone:
        visitor.phone = phone
    if id_partial:
        visitor.id_partial = id_partial
    if company:
        visitor.company = company
    if consent:
        visitor.face_consent_at = now
    visitor.last_visit_at = now
    visitor.save()
    return visitor
