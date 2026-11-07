from datetime import timedelta

from django.utils import timezone

from core import models as m


def make_condo(code="alpha", **kw):
    return m.Condominium.objects.create(name=code.title(), code=code, **kw)


def make_unit(condo, floor="05", number="12"):
    block, _ = m.Block.objects.get_or_create(condominium=condo, name="Block 1")
    return m.Unit.objects.create(condominium=condo, block=block, floor=floor, unit_number=number)


def make_user(username, **kw):
    return m.User.objects.create_user(username=username, password="pw-123456!", **kw)


def make_staff(username, condo, role):
    user = make_user(username)
    m.StaffAssignment.objects.create(user=user, condominium=condo, role=role)
    return user


def make_resident(username, unit):
    user = make_user(username)
    m.Residency.objects.create(user=user, unit=unit)
    return user


def make_invitation(unit, host, **kw):
    now = timezone.now()
    defaults = {"visitor_name": "Tan Ah Kow", "valid_from": now - timedelta(hours=1), "valid_until": now + timedelta(hours=5)}
    return m.Invitation.objects.create(unit=unit, host=host, **{**defaults, **kw})
