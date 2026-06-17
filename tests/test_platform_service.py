"""Step 8 platform service tests (cross-tenant super-admin operations)."""
from datetime import date

import pytest

from services import platform as plat
from services.platform import PlatformError
from models.enums import SchoolStatus, UserRole
from models.platform import Plan, Subscription
from tests.factories import make_school, make_user, make_student


# --- Suspend / activate -----------------------------------------------------
def test_suspend_and_activate(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    plat.suspend_school(s.id)
    db.session.commit()
    assert s.status == SchoolStatus.suspended
    plat.activate_school(s.id)
    db.session.commit()
    assert s.status == SchoolStatus.active


def test_set_status_unknown_school(app, db):
    with pytest.raises(PlatformError, match='not found'):
        plat.set_school_status(999999, 'active')


def test_invalid_status_rejected(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    with pytest.raises(PlatformError, match='Invalid status'):
        plat.set_school_status(s.id, 'frozen')


# --- Plans ------------------------------------------------------------------
def test_create_plan(app, db):
    p = plat.create_plan(name='Gold', price_ghs=200, max_students=500)
    db.session.commit()
    assert p.id and p.name == 'Gold'


def test_duplicate_plan_rejected(app, db):
    plat.create_plan(name='Basic')
    db.session.commit()
    with pytest.raises(PlatformError, match='already exists'):
        plat.create_plan(name='basic')  # case-insensitive


def test_update_plan(app, db):
    p = plat.create_plan(name='Std', price_ghs=100)
    db.session.commit()
    plat.update_plan(p.id, price_ghs=150, max_students=None)
    db.session.commit()
    assert db.session.get(Plan, p.id).price_ghs == 150


def test_delete_plan_blocked_when_in_use(app, db):
    s = make_school(db, slug='s')
    p = plat.create_plan(name='Std')
    db.session.commit()
    plat.set_subscription(s.id, p.id)
    db.session.commit()
    with pytest.raises(PlatformError, match='has subscriptions'):
        plat.delete_plan(p.id)


def test_delete_unused_plan(app, db):
    p = plat.create_plan(name='Temp')
    db.session.commit()
    plat.delete_plan(p.id)
    db.session.commit()
    assert db.session.get(Plan, p.id) is None


# --- Subscriptions (manual) -------------------------------------------------
def test_set_subscription(app, db):
    s = make_school(db, slug='s')
    p = plat.create_plan(name='Pro')
    db.session.commit()
    sub = plat.set_subscription(s.id, p.id, starts_on=date(2026, 1, 1),
                                ends_on=date(2026, 12, 31), status='active')
    db.session.commit()
    assert sub.id
    assert plat.current_subscription(s.id).id == sub.id


def test_set_subscription_unknown_plan(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    with pytest.raises(PlatformError, match='Plan not found'):
        plat.set_subscription(s.id, 999999)


# --- Metrics ----------------------------------------------------------------
def test_platform_metrics(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    plat.suspend_school(b.id)
    make_user(db, a, email='u@a.test', role=UserRole.teacher)
    make_student(db, a, admission_no='A1')
    db.session.commit()
    m = plat.platform_metrics()
    assert m['schools_total'] == 2
    assert m['schools_by_status']['suspended'] == 1
    assert m['students_total'] == 1
    assert m['users_total'] >= 1


def test_school_detail(app, db):
    s = make_school(db, slug='s')
    make_student(db, s, admission_no='A1')
    p = plat.create_plan(name='Pro')
    db.session.commit()
    plat.set_subscription(s.id, p.id)
    db.session.commit()
    d = plat.school_detail(s.id)
    assert d['students'] == 1
    assert d['subscription'] is not None
