import re

from django.core.exceptions import ValidationError

# Singapore plates (SBA1234A, GBC123D, ...) plus Malaysian plates seen at the
# Causeway (JQB1234, WXY123). Deliberately lenient: LPR output is normalised first.
PLATE_RE = re.compile(r"^[A-Z]{1,4}\d{1,4}[A-Z]{0,2}$")
POSTAL_CODE_RE = re.compile(r"^\d{6}$")


def normalize_plate(value: str) -> str:
    """Uppercase and strip spaces/dashes: 'sba 1234-a' -> 'SBA1234A'."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def validate_plate(value: str):
    if not PLATE_RE.match(normalize_plate(value)):
        raise ValidationError("%(value)s is not a valid vehicle plate number.", params={"value": value})


def validate_sg_postal_code(value: str):
    if not POSTAL_CODE_RE.match(value):
        raise ValidationError("Singapore postal codes have 6 digits.")
