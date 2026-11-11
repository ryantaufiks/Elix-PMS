"""Which condominiums and units a user may see, by role."""
from .models import Residency, StaffAssignment

ADMIN = StaffAssignment.Role.ADMIN  # Site admin: everything at the site, including setup and staff accounts.
STAFF = StaffAssignment.Role.STAFF  # Management office: residents, bookings, feedback, gates and visitors.
SECURITY = StaffAssignment.Role.SECURITY  # Officer: gates and visitors.
MANAGEMENT = (ADMIN, STAFF)
ALL_STAFF = (ADMIN, STAFF, SECURITY)


def staff_condo_ids(user, roles=ALL_STAFF) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(
        StaffAssignment.objects.filter(user=user, role__in=roles, condominium__is_active=True)
        .values_list("condominium_id", flat=True)
    )


def _active_residencies(user):
    """Residencies that give access, i.e. at sites that use the resident app."""
    return Residency.objects.filter(user=user, is_active=True, unit__is_active=True,
                                    unit__condominium__modules__contains=["resident_app"])


def resident_unit_ids(user) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(_active_residencies(user).values_list("unit_id", flat=True))


def resident_condo_ids(user) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(_active_residencies(user).values_list("unit__condominium_id", flat=True))
