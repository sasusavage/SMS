"""Super-admin: create school directly + platform broadcast."""
from unittest.mock import patch

import pytest

from services import platform as plat
from services.platform import PlatformError
from models.platform import School
from models.operational import User, Student
from models.config_tables import Subject
from models.enums import UserRole, SchoolStatus
from services import platform_settings, school_settings
from tests.factories import make_school, make_user, make_platform_user


# --- create_school_with_admin ----------------------------------------------
def test_create_school_with_admin(app, db):
    school = plat.create_school_with_admin(
        name='New School', slug='new-school', country='Ghana',
        template='ghana_ges', admin_name='Boss', admin_email='boss@new.test',
        admin_password='secret12')
    db.session.commit()
    assert school.id and school.status == SchoolStatus.active
    assert User.query.filter_by(school_id=school.id,
                                role=UserRole.school_admin).count() == 1
    # template applied
    assert Subject.query.filter_by(school_id=school.id).count() == 9


def test_create_school_duplicate_slug(app, db):
    make_school(db, slug='taken')
    db.session.commit()
    with pytest.raises(PlatformError, match='taken'):
        plat.create_school_with_admin(
            name='X', slug='taken', country=None, template='blank',
            admin_name='A', admin_email='a@x.test', admin_password='secret12')


def test_create_school_short_password(app, db):
    with pytest.raises(PlatformError, match='at least 8'):
        plat.create_school_with_admin(
            name='X', slug='x-school', country=None, template='blank',
            admin_name='A', admin_email='a@x.test', admin_password='x')


# --- broadcast --------------------------------------------------------------
def test_broadcast_email_to_admins(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='a1@a.test', role=UserRole.school_admin)
    make_user(db, b, email='b1@b.test', role=UserRole.school_admin)
    db.session.commit()
    with patch('services.notify._smtp_send'):  # email path
        # no SMTP configured -> stub-logged, still counts as attempted
        n = plat.broadcast(channel='email', subject='Hi', message='Hello all')
    db.session.commit()
    assert n == 2


def test_broadcast_skips_suspended(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    b.status = SchoolStatus.suspended
    make_user(db, a, email='a1@a.test', role=UserRole.school_admin)
    make_user(db, b, email='b1@b.test', role=UserRole.school_admin)
    db.session.commit()
    n = plat.broadcast(channel='email', subject='Hi', message='Hello')
    db.session.commit()
    assert n == 1   # only the active school


# --- Routes -----------------------------------------------------------------
def _login_super(client, db, email='super@x.test'):
    make_platform_user(db, email=email)
    db.session.commit()
    return client.post('/auth/login', data={'school_slug': '', 'email': email,
                                            'password': 'pw'})


def test_new_school_route(app, db, client):
    _login_super(client, db)
    client.post('/platform/schools/new', data={
        'name': 'Created', 'slug': 'created', 'template': 'blank',
        'admin_name': 'A', 'admin_email': 'a@created.test',
        'admin_password': 'secret12'}, follow_redirects=True)
    assert School.query.filter_by(slug='created').count() == 1


def test_broadcast_route(app, db, client):
    a = make_school(db, slug='a')
    make_user(db, a, email='a1@a.test', role=UserRole.school_admin)
    _login_super(client, db)
    r = client.post('/platform/broadcast', data={
        'channel': 'email', 'subject': 'Hi', 'message': 'Hello'},
        follow_redirects=True)
    assert b'Broadcast queued' in r.data
