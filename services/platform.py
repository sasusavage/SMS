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
    # Subscription revenue (successful Payment rows), in GHS.
    from decimal import Decimal
    from models.platform import Payment
    paid = Payment.query.filter_by(status='success').all()
    revenue = sum((Decimal(str(p.amount_pesewas)) for p in paid),
                  Decimal('0')) / 100
    return {
        'schools_total': len(schools),
        'schools_by_status': by_status,
        'students_total': Student.query.count(),
        'users_total': User.query.count(),
        'plans_total': Plan.query.count(),
        'platform_admins': PlatformUser.query.count(),
        'revenue_ghs': revenue,
        'paid_count': len(paid),
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
# Platform admins (super admins)
# ---------------------------------------------------------------------------
def list_platform_admins():
    return PlatformUser.query.order_by(PlatformUser.name).all()


def create_platform_admin(*, name, email, password):
    from auth.security import hash_password
    name = (name or '').strip()
    email = (email or '').strip().lower()
    if not name:
        raise PlatformError('Name is required.')
    if not email:
        raise PlatformError('Email is required.')
    if len(password or '') < 8:
        raise PlatformError('Password must be at least 8 characters.')
    if PlatformUser.query.filter(
            db.func.lower(PlatformUser.email) == email).first():
        raise PlatformError(f'A platform admin with email {email} already exists.')
    pu = PlatformUser(name=name, email=email,
                      password_hash=hash_password(password), is_active=True)
    db.session.add(pu)
    db.session.flush()
    return pu


def set_platform_admin_active(admin_id, active, *, acting_id=None):
    pu = db.session.get(PlatformUser, admin_id)
    if pu is None:
        raise PlatformError('Platform admin not found.')
    # Don't let an admin deactivate themselves (would lock themselves out).
    if not active and acting_id is not None and pu.id == acting_id:
        raise PlatformError('You cannot deactivate your own account.')
    if not active:
        active_count = PlatformUser.query.filter_by(is_active=True).count()
        if active_count <= 1 and pu.is_active:
            raise PlatformError('At least one active platform admin is required.')
    pu.is_active = bool(active)
    db.session.flush()
    return pu


def reset_platform_admin_password(admin_id, new_password=None):
    import secrets as _secrets
    from auth.security import hash_password
    pu = db.session.get(PlatformUser, admin_id)
    if pu is None:
        raise PlatformError('Platform admin not found.')
    if not new_password:
        new_password = _secrets.token_urlsafe(8)
    elif len(new_password) < 8:
        raise PlatformError('Password must be at least 8 characters.')
    pu.password_hash = hash_password(new_password)
    db.session.flush()
    return new_password


# ---------------------------------------------------------------------------
# Revenue & growth analytics
# ---------------------------------------------------------------------------
def revenue_analytics(months=6):
    """
    Platform revenue + growth for the super-admin analytics page:
      - revenue_by_month: [(YYYY-MM, ghs), ...] last `months`
      - recent_payments: latest successful Payment rows
      - signups_by_month: schools created per month
      - expiring_soon: subscriptions ending within 14 days (active)
      - students_per_school: [(school, count), ...] top by enrolment
    """
    from collections import OrderedDict
    from datetime import date, timedelta
    from decimal import Decimal
    from models.platform import Payment, Subscription

    def month_keys(n):
        today = date.today().replace(day=1)
        keys = []
        y, m = today.year, today.month
        for _ in range(n):
            keys.append(f'{y:04d}-{m:02d}')
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return list(reversed(keys))

    keys = month_keys(months)
    rev = OrderedDict((k, Decimal('0')) for k in keys)
    for p in Payment.query.filter_by(status='success').all():
        d = p.paid_at or p.created_at
        if d is None:
            continue
        k = f'{d.year:04d}-{d.month:02d}'
        if k in rev:
            rev[k] += Decimal(str(p.amount_pesewas)) / 100

    signups = OrderedDict((k, 0) for k in keys)
    for s in School.query.all():
        if s.created_at:
            k = f'{s.created_at.year:04d}-{s.created_at.month:02d}'
            if k in signups:
                signups[k] += 1

    recent_payments = (Payment.query.filter_by(status='success')
                       .order_by(Payment.id.desc()).limit(15).all())

    horizon = date.today() + timedelta(days=14)
    expiring = (Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.ends_on.isnot(None),
        Subscription.ends_on <= horizon,
        Subscription.ends_on >= date.today(),
    ).order_by(Subscription.ends_on).all())

    counts = []
    for s in School.query.all():
        counts.append((s, Student.query.filter_by(school_id=s.id).count()))
    counts.sort(key=lambda t: t[1], reverse=True)

    return {
        'revenue_by_month': [(k, rev[k]) for k in keys],
        'signups_by_month': [(k, signups[k]) for k in keys],
        'recent_payments': recent_payments,
        'expiring_soon': expiring,
        'students_per_school': counts[:10],
    }


# ---------------------------------------------------------------------------
# Create a school directly (super admin; no public signup)
# ---------------------------------------------------------------------------
def create_school_with_admin(*, name, slug, country, template,
                             admin_name, admin_email, admin_password):
    """Create a School + first school_admin + apply a curriculum template."""
    import re
    from auth.security import hash_password
    from services.template_loader import apply_template, VALID_TEMPLATES
    from models.operational import User
    from models.enums import UserRole

    name = (name or '').strip()
    admin_email = (admin_email or '').strip().lower()
    if not name:
        raise PlatformError('School name is required.')
    if not admin_email:
        raise PlatformError('Admin email is required.')
    if len(admin_password or '') < 8:
        raise PlatformError('Admin password must be at least 8 characters.')
    if template not in VALID_TEMPLATES:
        raise PlatformError('Pick a valid curriculum template.')

    slug = re.sub(r'[^a-z0-9]+', '-', (slug or name).strip().lower()).strip('-')
    if not slug:
        slug = 'school'
    if School.query.filter_by(slug=slug).first():
        raise PlatformError(f'School code "{slug}" is taken — choose another.')

    school = School(name=name, slug=slug, country=(country or '').strip() or None,
                    curriculum_template_used=template, status=SchoolStatus.active)
    db.session.add(school)
    db.session.flush()
    admin = User(school_id=school.id, email=admin_email, name=(admin_name or '').strip(),
                 role=UserRole.school_admin,
                 password_hash=hash_password(admin_password), is_active=True)
    db.session.add(admin)
    db.session.flush()
    apply_template(school.id, template)
    return school


# ---------------------------------------------------------------------------
# Platform broadcast (announcement to all schools)
# ---------------------------------------------------------------------------
def broadcast(*, channel, subject, message, only_active=True):
    """
    Send a platform-wide announcement to every school's admins.
    channel: 'email' | 'sms'. Returns count of messages attempted.
    """
    from services import notify
    from models.operational import User
    from models.enums import UserRole
    q = School.query
    if only_active:
        q = q.filter(School.status != SchoolStatus.suspended)
    n = 0
    for school in q.all():
        admins = User.query.filter_by(
            school_id=school.id, role=UserRole.school_admin,
            is_active=True).all()
        for a in admins:
            if channel == 'sms':
                if a.phone:
                    notify.send_sms(school.id, a.phone, message)
                    n += 1
            else:
                if a.email:
                    notify.send_email(school.id, a.email,
                                      subject or 'Announcement', message)
                    n += 1
    return n


# ---------------------------------------------------------------------------
# Audit log viewer
# ---------------------------------------------------------------------------
def audit_logs(*, school_id=None, action=None, limit=200):
    from models.operational import AuditLog
    q = AuditLog.query
    if school_id is not None:
        q = q.filter(AuditLog.school_id == school_id)
    if action:
        q = q.filter(AuditLog.action.ilike(f'%{action}%'))
    return q.order_by(AuditLog.id.desc()).limit(limit).all()


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
