"""Super-admin: platform admin management + audit log viewer."""
import pytest

from services import platform as plat
from services.platform import PlatformError
from models.platform import PlatformUser
from models.operational import AuditLog
from models.enums import UserRole
from tests.factories import make_school, make_user, make_platform_user
from auth.security import verify_password


# --- Service: platform admins ----------------------------------------------
def test_create_platform_admin(app, db):
    pu = plat.create_platform_admin(name='Boss', email='boss@x.test',
                                    password='secret12')
    db.session.commit()
    assert pu.id and verify_password(pu.password_hash, 'secret12')


def test_create_duplicate_rejected(app, db):
    plat.create_platform_admin(name='A', email='dup@x.test', password='secret12')
    db.session.commit()
    with pytest.raises(PlatformError, match='already exists'):
        plat.create_platform_admin(name='B', email='dup@x.test', password='secret12')


def test_short_password_rejected(app, db):
    with pytest.raises(PlatformError, match='at least 8'):
        plat.create_platform_admin(name='A', email='a@x.test', password='x')


def test_cannot_deactivate_self(app, db):
    pu = make_platform_user(db, email='me@x.test')
    db.session.commit()
    with pytest.raises(PlatformError, match='your own account'):
        plat.set_platform_admin_active(pu.id, False, acting_id=pu.id)


def test_cannot_deactivate_last_admin(app, db):
    pu = make_platform_user(db, email='only@x.test')
    db.session.commit()
    with pytest.raises(PlatformError, match='At least one active'):
        plat.set_platform_admin_active(pu.id, False, acting_id=999)


def test_deactivate_when_another_exists(app, db):
    a = make_platform_user(db, email='a@x.test')
    b = make_platform_user(db, email='b@x.test')
    db.session.commit()
    plat.set_platform_admin_active(b.id, False, acting_id=a.id)
    db.session.commit()
    assert db.session.get(PlatformUser, b.id).is_active is False


def test_reset_password(app, db):
    pu = make_platform_user(db, email='a@x.test')
    db.session.commit()
    new = plat.reset_platform_admin_password(pu.id)
    db.session.commit()
    assert len(new) >= 8 and verify_password(
        db.session.get(PlatformUser, pu.id).password_hash, new)


# --- Service: audit query ---------------------------------------------------
def test_audit_logs_filter(app, db):
    s = make_school(db, slug='s')
    db.session.add_all([
        AuditLog(school_id=s.id, user_id=1, action='login', entity='user'),
        AuditLog(school_id=s.id, user_id=1, action='publish_results', entity='class'),
        AuditLog(school_id=None, user_id=2, action='suspend_school', entity='school'),
    ])
    db.session.commit()
    assert len(plat.audit_logs()) == 3
    assert len(plat.audit_logs(school_id=s.id)) == 2
    assert len(plat.audit_logs(action='publish')) == 1


# --- Routes -----------------------------------------------------------------
def _login_super(client, db, email='super@x.test'):
    make_platform_user(db, email=email)
    db.session.commit()
    return client.post('/auth/login', data={'school_slug': '', 'email': email,
                                            'password': 'pw'})


def test_admins_page_super_only(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    client.post('/auth/login', data={'school_slug': 's', 'email': 'a@s.test',
                                     'password': 'pw'})
    assert client.get('/platform/admins').status_code == 403


def test_create_admin_via_route(app, db, client):
    _login_super(client, db)
    client.post('/platform/admins', data={
        'name': 'New', 'email': 'new@x.test', 'password': 'secret12'},
        follow_redirects=True)
    assert PlatformUser.query.filter_by(email='new@x.test').count() == 1


def test_audit_page_renders(app, db, client):
    _login_super(client, db)
    r = client.get('/platform/audit')
    assert r.status_code == 200
