"""Which condominiums and units a user may see, by role."""
from .models import Residency, StaffAssignment

ADMIN = StaffAssignment.Role.ADMIN
SECURITY = StaffAssignment.Role.SECURITY
ALL_STAFF = (ADMIN, SECURITY)


def staff_condo_ids(user, roles=ALL_STAFF) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(
        StaffAssignment.objects.filter(user=user, role__in=roles, condominium__is_active=True)
        .values_list("condominium_id", flat=True)
    )


def _active_residencies(user):
    return Residency.objects.filter(user=user, is_active=True, unit__is_active=True)


def resident_unit_ids(user) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(_active_residencies(user).values_list("unit_id", flat=True))


def resident_condo_ids(user) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(_active_residencies(user).values_list("unit__condominium_id", flat=True))
