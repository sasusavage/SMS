"""Super-admin impersonation (view as school) — security + behavior."""
from models.enums import UserRole
from models.operational import AuditLog, Student
from tests.factories import make_school, make_user, make_platform_user, make_student


def _login_super(client, db, email='super@x.test'):
    make_platform_user(db, email=email)
    db.session.commit()
    return client.post('/auth/login', data={'school_slug': '', 'email': email,
                                            'password': 'pw'})


def test_impersonate_requires_super_admin(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    client.post('/auth/login', data={'school_slug': 's', 'email': 'a@s.test',
                                     'password': 'pw'})
    # a school admin cannot hit the platform impersonate route
    assert client.post(f'/platform/schools/{s.id}/impersonate').status_code == 403


def test_impersonate_then_access_school_pages(app, db, client):
    s = make_school(db, slug='s')
    make_student(db, s, admission_no='A1')
    _login_super(client, db)
    # start impersonation
    client.post(f'/platform/schools/{s.id}/impersonate', follow_redirects=True)
    # now the super admin can reach school-admin pages, scoped to THIS school
    r = client.get('/admin/students')
    assert r.status_code == 200
    assert b'A1' in r.data
    # the banner shows
    assert b'Viewing as' in r.data


def test_impersonation_is_audited(app, db, client):
    s = make_school(db, slug='s')
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/impersonate')
    assert AuditLog.query.filter_by(action='impersonate_start').count() == 1
    client.post('/platform/exit-impersonation')
    assert AuditLog.query.filter_by(action='impersonate_end').count() == 1


def test_exit_impersonation_restores_platform(app, db, client):
    s = make_school(db, slug='s')
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/impersonate')
    client.post('/platform/exit-impersonation', follow_redirects=True)
    # back to platform; school pages now forbidden again
    assert client.get('/admin/students').status_code == 403
    assert client.get('/platform/').status_code == 200


def test_can_impersonate_suspended_school(app, db, client):
    """Regression: impersonating a SUSPENDED school must NOT log the super
    admin out (they need to inspect the school they suspended)."""
    from models.enums import SchoolStatus
    s = make_school(db, slug='s')
    s.status = SchoolStatus.suspended
    make_student(db, s, admission_no='A1')
    db.session.commit()
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/impersonate', follow_redirects=True)
    r = client.get('/admin/students')           # must work, not bounce to login
    assert r.status_code == 200
    assert b'A1' in r.data


def test_logout_clears_impersonation(app, db, client):
    """Regression: logging out must clear the impersonation flag so it doesn't
    silently resume on next login."""
    s = make_school(db, slug='s')
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/impersonate')
    client.post('/auth/logout')
    # log back in -> should land on platform, NOT still impersonating
    client.post('/auth/login', data={'school_slug': '', 'email': 'super@x.test',
                                     'password': 'pw'})
    r = client.get('/admin/students')
    assert r.status_code == 403   # no longer impersonating


def test_impersonated_actions_tagged_in_audit(app, db, client):
    from models.operational import AuditLog
    s = make_school(db, slug='s')
    make_student(db, s, admission_no='A1')
    _login_super(client, db)
    client.post(f'/platform/schools/{s.id}/impersonate')
    client.get('/admin/export/students.csv')   # an audited action while impersonating
    log = (AuditLog.query.filter_by(action='export', school_id=s.id)
           .order_by(AuditLog.id.desc()).first())
    assert log is not None and log.meta.get('impersonated_by_super_admin') is True


def test_impersonation_scoped_to_one_school(app, db, client):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_student(db, a, admission_no='AONLY')
    b_student = make_student(db, b, admission_no='BONLY')
    _login_super(client, db)
    client.post(f'/platform/schools/{a.id}/impersonate')
    # viewing school A: cannot open school B's student
    assert client.get(f'/admin/students/{b_student.id}').status_code == 404
