"""
Platform service (Step 8) — super-admin, CROSS-TENANT operations.

Unlike every other service, this one deliberately operates across all schools:
the super admin manages tenants, plans, subscriptions and views platform-wide
metrics. There is no g.current_school_id here. Access is gated at the route
layer by @platform_only (super admins only).

Paystack billing is Phase 2 — subscriptions here are marked MANUALLY (plan,
dates, status set by hand).
"""
from datetime import date

from extensions import db
from models.platform import School, Plan, Subscription, PlatformUser
from models.enums import SchoolStatus
from models.operational import User, Student


class PlatformError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Schools — suspend / activate
# ---------------------------------------------------------------------------
def set_school_status(school_id, status):
    """status: SchoolStatus or its value ('trial'|'active'|'suspended')."""
    school = db.session.get(School, school_id)
    if school is None:
        raise PlatformError('School not found.')
    school.status = _coerce_status(status)
    db.session.flush()
    return school


def suspend_school(school_id):
    return set_school_status(school_id, SchoolStatus.suspended)


def activate_school(school_id):
    return set_school_status(school_id, SchoolStatus.active)


# ---------------------------------------------------------------------------
# Plans — CRUD
# ---------------------------------------------------------------------------
def create_plan(*, name, price_ghs=0, max_students=None, billing_cycle='monthly'):
    name = (name or '').strip()
    if not name:
        raise PlatformError('Plan name is required.')
    if Plan.query.filter(db.func.lower(Plan.name) == name.lower()).first():
        raise PlatformError(f'A plan named "{name}" already exists.')
    plan = Plan(name=name, price_ghs=price_ghs or 0,
                max_students=max_students, billing_cycle=billing_cycle or 'monthly')
    db.session.add(plan)
    db.session.flush()
    return plan


def update_plan(plan_id, **fields):
    plan = db.session.get(Plan, plan_id)
    if plan is None:
        raise PlatformError('Plan not found.')
    if 'name' in fields and fields['name']:
        plan.name = fields['name'].strip()
    if 'price_ghs' in fields and fields['price_ghs'] is not None:
        plan.price_ghs = fields['price_ghs']
    if 'max_students' in fields:
        plan.max_students = fields['max_students']
    if 'billing_cycle' in fields and fields['billing_cycle']:
        plan.billing_cycle = fields['billing_cycle']
    db.session.flush()
    return plan


def delete_plan(plan_id):
    plan = db.session.get(Plan, plan_id)
    if plan is None:
        raise PlatformError('Plan not found.')
    if Subscription.query.filter_by(plan_id=plan_id).first():
        raise PlatformError('Cannot delete a plan that has subscriptions.')
    db.session.delete(plan)
    db.session.flush()


# ---------------------------------------------------------------------------
# Subscriptions — manual marking (no Paystack in Phase 1)
# ---------------------------------------------------------------------------
def set_subscription(school_id, plan_id, *, starts_on=None, ends_on=None,
                     status='active', paystack_ref=None):
    """
    Create or replace a school's current subscription record (manual). Keeps it
    simple for Phase 1: one active subscription row tracked per school; this
    upserts the latest.
    """
    school = db.session.get(School, school_id)
    if school is None:
        raise PlatformError('School not found.')
    plan = db.session.get(Plan, plan_id)
    if plan is None:
        raise PlatformError('Plan not found.')

    sub = Subscription(
        school_id=school_id, plan_id=plan_id,
        starts_on=starts_on or date.today(), ends_on=ends_on,
        status=status or 'active', paystack_ref=paystack_ref)
    db.session.add(sub)
    db.session.flush()
    return sub


def current_subscription(school_id):
    return (Subscription.query.filter_by(school_id=school_id)
            .order_by(Subscription.id.desc()).first())


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def platform_metrics():
    """Platform-wide counts for the super-admin dashboard."""
    schools = School.query.all()
    by_status = {s.value: 0 for s in SchoolStatus}
    for s in schools:
        key = s.status.value if s.status else 'trial'
        by_status[key] = by_status.get(key, 0) + 1
    return {
        'schools_total': len(schools),
        'schools_by_status': by_status,
        'students_total': Student.query.count(),
        'users_total': User.query.count(),
        'plans_total': Plan.query.count(),
        'platform_admins': PlatformUser.query.count(),
    }


def school_detail(school_id):
    school = db.session.get(School, school_id)
    if school is None:
        raise PlatformError('School not found.')
    return {
        'school': school,
        'students': Student.query.filter_by(school_id=school_id).count(),
        'users': User.query.filter_by(school_id=school_id).count(),
        'subscription': current_subscription(school_id),
        'subscriptions': (Subscription.query.filter_by(school_id=school_id)
                          .order_by(Subscription.id.desc()).all()),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _coerce_status(status):
    if isinstance(status, SchoolStatus):
        return status
    try:
        return SchoolStatus(status)
    except ValueError:
        raise PlatformError(f'Invalid status: {status!r}.')
