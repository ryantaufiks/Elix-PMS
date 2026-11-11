from datetime import timedelta

from django.utils import timezone

from core import entitlements
from core import models as m


def make_condo(code="alpha", plan="full", **kw):
    """A site on ``plan`` (default every module), active."""
    condo = m.Condominium.objects.create(name=code.title(), code=code, **kw)
    set_plan(condo, plan)
    return condo


def set_plan(condo, plan, **subscription):
    entitlements.ensure_default_plans()  # TransactionTestCase empties the tables migrations filled.
    m.Subscription.objects.update_or_create(condominium=condo, defaults={
        "plan": m.Plan.objects.get(code=plan), "status": m.Subscription.Status.ACTIVE, **subscription})
    condo.refresh_from_db()
    return condo


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
