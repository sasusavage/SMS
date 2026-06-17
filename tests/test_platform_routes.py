"""Step 8 platform route tests: super-admin access, suspend lockout, flows."""
from models.enums import UserRole, SchoolStatus
from models.platform import Plan, School
from tests.factories import (
    make_school, make_user, make_platform_user, make_student,
)


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


def _login_super(client, db, email='super@x.test'):
    make_platform_user(db, email=email)
    db.session.commit()
    return client.post('/auth/login', data={
        'school_slug': '', 'email': email, 'password': 'pw'})


# --- Access control ---------------------------------------------------------
def test_platform_requires_super_admin(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    assert client.get('/platform/').status_code == 403


def test_super_admin_sees_dashboard(app, db, client):
    make_school(db, slug='s')
    _login_super(client, db)
    r = client.get('/platform/')
    assert r.status_code == 200
    assert b'Platform administration' in r.data


def test_anonymous_redirected(app, db, client):
    r = client.get('/platform/', follow_redirects=False)
    assert r.status_code in (302, 401)


# --- Suspend / activate -----------------------------------------------------
def test_suspend_then_activate_school(app, db, client):
    s = make_school(db, slug='s')
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/suspend', follow_redirects=True)
    assert db.session.get(School, s.id).status == SchoolStatus.suspended
    client.post(f'/platform/schools/{s.id}/activate', follow_redirects=True)
    assert db.session.get(School, s.id).status == SchoolStatus.active


def test_suspended_school_blocks_login(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    s.status = SchoolStatus.suspended
    db.session.commit()
    r = client.post('/auth/login', data={
        'school_slug': 's', 'email': 'a@s.test', 'password': 'pw'})
    assert r.status_code == 403
    assert b'suspended' in r.data


def test_suspend_logs_out_active_session(app, db, client):
    """A logged-in user gets kicked out once their school is suspended."""
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    assert client.get('/dashboard/').status_code == 200  # works while active
    # suspend out-of-band
    s2 = db.session.get(School, s.id)
    s2.status = SchoolStatus.suspended
    db.session.commit()
    # next request -> redirected to login
    r = client.get('/dashboard/', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/auth/login' in r.headers['Location']


# --- Plans ------------------------------------------------------------------
def test_create_and_delete_plan(app, db, client):
    _login_super(client, db)
    client.post('/platform/plans', data={'name': 'Gold', 'price_ghs': '200'},
                follow_redirects=True)
    plan = Plan.query.filter_by(name='Gold').first()
    assert plan is not None
    client.post(f'/platform/plans/{plan.id}/delete', follow_redirects=True)
    assert Plan.query.filter_by(name='Gold').first() is None


# --- Subscription -----------------------------------------------------------
def test_mark_subscription(app, db, client):
    s = make_school(db, slug='s')
    p = Plan(name='Pro', price_ghs=400)
    db.session.add(p)
    db.session.commit()
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/subscription',
                data={'plan_id': p.id, 'status': 'active',
                      'starts_on': '2026-01-01', 'ends_on': '2026-12-31'},
                follow_redirects=True)
    from models.platform import Subscription
    assert Subscription.query.filter_by(school_id=s.id, plan_id=p.id).count() == 1


def test_school_detail_renders(app, db, client):
    s = make_school(db, slug='s')
    make_student(db, s, admission_no='A1')
    db.session.commit()
    _login_super(client, db)
    r = client.get(f'/platform/schools/{s.id}')
    assert r.status_code == 200
