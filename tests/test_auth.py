"""Auth: password hashing, login flow, role decorators, same-school guard."""
import pytest
from flask import g, Blueprint

from auth.security import (
    hash_password, verify_password, require_role, platform_only,
    require_same_school, PlatformIdentity,
)
from models.enums import UserRole
from models.operational import Student

from tests.factories import (
    make_school, make_user, make_student, make_platform_user,
)


def test_password_hash_roundtrip():
    h = hash_password('s3cret')
    assert h != 's3cret'
    assert verify_password(h, 's3cret')
    assert not verify_password(h, 'wrong')
    assert not verify_password(None, 'x')


def test_email_unique_per_school_not_global(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='admin@x.test')
    make_user(db, b, email='admin@x.test')  # same email, different school: OK
    db.session.commit()


def test_login_success_and_tenant_resolution(app, db, client):
    school = make_school(db, slug='demo')
    make_user(db, school, email='admin@demo.test', password='pw')
    db.session.commit()

    resp = client.post('/auth/login', data={
        'school_slug': 'demo', 'email': 'admin@demo.test', 'password': 'pw',
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_login_wrong_password_rejected(app, db, client):
    school = make_school(db, slug='demo')
    make_user(db, school, email='admin@demo.test', password='pw')
    db.session.commit()
    resp = client.post('/auth/login', data={
        'school_slug': 'demo', 'email': 'admin@demo.test', 'password': 'nope',
    })
    assert resp.status_code == 401


def test_login_wrong_school_slug_rejected(app, db, client):
    school = make_school(db, slug='demo')
    make_user(db, school, email='admin@demo.test', password='pw')
    db.session.commit()
    resp = client.post('/auth/login', data={
        'school_slug': 'other', 'email': 'admin@demo.test', 'password': 'pw',
    })
    assert resp.status_code == 401


def test_inactive_user_cannot_login(app, db, client):
    school = make_school(db, slug='demo')
    make_user(db, school, email='x@demo.test', password='pw', is_active=False)
    db.session.commit()
    resp = client.post('/auth/login', data={
        'school_slug': 'demo', 'email': 'x@demo.test', 'password': 'pw',
    })
    assert resp.status_code == 401


def test_super_admin_blank_slug_login(app, db, client):
    make_platform_user(db, email='super@x.test', password='pw')
    db.session.commit()
    resp = client.post('/auth/login', data={
        'school_slug': '', 'email': 'super@x.test', 'password': 'pw',
    })
    assert resp.status_code in (302, 303)


# --- Decorator tests via tiny ad-hoc views ---------------------------------
def _register_probe_routes(app):
    bp = Blueprint('probe', __name__)

    @bp.route('/probe/admin-only')
    @require_role('school_admin')
    def admin_only():
        return 'ok'

    @bp.route('/probe/platform-only')
    @platform_only
    def plat_only():
        return 'ok'

    @bp.route('/probe/same-school/<int:student_id>')
    @require_same_school((Student, 'student_id'))
    def same_school(student_id):
        return 'ok'

    app.register_blueprint(bp)


def test_require_role_blocks_wrong_role(app, db, client):
    _register_probe_routes(app)
    school = make_school(db, slug='demo')
    make_user(db, school, email='t@demo.test', password='pw',
              role=UserRole.teacher)
    db.session.commit()
    client.post('/auth/login', data={
        'school_slug': 'demo', 'email': 't@demo.test', 'password': 'pw'})
    resp = client.get('/probe/admin-only')
    assert resp.status_code == 403


def test_require_same_school_404_for_other_school(app, db, client):
    _register_probe_routes(app)
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='admin@a.test', password='pw')
    b_student = make_student(db, b, admission_no='B1')
    db.session.commit()
    client.post('/auth/login', data={
        'school_slug': 'a', 'email': 'admin@a.test', 'password': 'pw'})
    resp = client.get(f'/probe/same-school/{b_student.id}')
    assert resp.status_code == 404  # not 403 — don't leak existence


def test_platform_only_blocks_school_user(app, db, client):
    _register_probe_routes(app)
    school = make_school(db, slug='demo')
    make_user(db, school, email='admin@demo.test', password='pw')
    db.session.commit()
    client.post('/auth/login', data={
        'school_slug': 'demo', 'email': 'admin@demo.test', 'password': 'pw'})
    resp = client.get('/probe/platform-only')
    assert resp.status_code == 403
