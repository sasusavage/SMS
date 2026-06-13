"""
Step 2 route tests: /admin/config CRUD tenant-scoping + validation surfacing,
and the onboarding wizard flow.
"""
from models.enums import UserRole
from models.config_tables import (
    AcademicYear, Subject, LevelGroup, GradingScheme, GradeBoundary,
)
from models.platform import School
from models.operational import User
from tests.factories import make_school, make_user


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


# --- Access control ---------------------------------------------------------
def test_config_requires_login(client):
    resp = client.get('/admin/config/', follow_redirects=False)
    assert resp.status_code in (302, 401)  # redirected to login


def test_teacher_cannot_access_config(app, db, client):
    school = make_school(db, slug='s')
    make_user(db, school, email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    resp = client.get('/admin/config/')
    assert resp.status_code == 403


def test_admin_can_access_config(app, db, client):
    school = make_school(db, slug='s')
    make_user(db, school, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    resp = client.get('/admin/config/')
    assert resp.status_code == 200


# --- CRUD is tenant-scoped --------------------------------------------------
def test_create_subject_is_scoped_to_my_school(app, db, client):
    a = make_school(db, slug='a')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 'a', 'a@a.test')
    client.post('/admin/config/subjects',
                data={'name': 'Math', 'code': 'M', 'is_core': 'on'})
    subs = Subject.query.filter_by(school_id=a.id).all()
    assert len(subs) == 1 and subs[0].name == 'Math'


def test_cannot_delete_other_schools_subject(app, db, client):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    b_subj = Subject(school_id=b.id, name='Secret', is_core=True)
    db.session.add(b_subj)
    db.session.commit()
    _login(client, 'a', 'a@a.test')
    # School A admin tries to delete School B's subject -> 404 (not 403)
    resp = client.post(f'/admin/config/subjects/{b_subj.id}/delete')
    assert resp.status_code == 404
    assert db.session.get(Subject, b_subj.id) is not None  # still there


# --- Validation surfaced through routes -------------------------------------
def test_term_outside_year_is_rejected_via_route(app, db, client):
    from datetime import date
    school = make_school(db, slug='s')
    make_user(db, school, email='a@s.test', role=UserRole.school_admin)
    ay = AcademicYear(school_id=school.id, name='2025/2026',
                      start_date=date(2025, 9, 1), end_date=date(2026, 7, 31))
    db.session.add(ay)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    resp = client.post('/admin/config/terms', data={
        'academic_year_id': ay.id, 'name': 'Bad', 'sequence': '1',
        'start_date': '2025-08-01', 'end_date': '2025-12-01',
    }, follow_redirects=True)
    # term not created
    from models.config_tables import Term
    assert Term.query.filter_by(school_id=school.id).count() == 0
    assert b'before the academic year' in resp.data


def test_overlapping_boundary_rejected_via_route(app, db, client):
    school = make_school(db, slug='s')
    make_user(db, school, email='a@s.test', role=UserRole.school_admin)
    scheme = GradingScheme(school_id=school.id, name='X', is_default=True)
    db.session.add(scheme)
    db.session.flush()
    db.session.add(GradeBoundary(school_id=school.id, grading_scheme_id=scheme.id,
                                 min_score=50, max_score=100, grade_label='A'))
    db.session.commit()
    _login(client, 's', 'a@s.test')
    resp = client.post(f'/admin/config/grading-schemes/{scheme.id}', data={
        'min_score': '40', 'max_score': '60', 'grade_label': 'B',  # overlaps A
    }, follow_redirects=True)
    assert GradeBoundary.query.filter_by(school_id=school.id).count() == 1
    assert b'overlap' in resp.data


# --- Onboarding wizard ------------------------------------------------------
def test_signup_creates_school_admin_and_applies_template(app, db, client):
    resp = client.post('/signup', data={
        'school_name': 'New School', 'slug': 'new-school',
        'admin_name': 'Boss', 'admin_email': 'boss@new.test',
        'password': 'longenough', 'template': 'ghana_ges',
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
    school = School.query.filter_by(slug='new-school').one()
    assert User.query.filter_by(school_id=school.id,
                                role=UserRole.school_admin).count() == 1
    # template applied
    assert Subject.query.filter_by(school_id=school.id).count() == 9
    assert LevelGroup.query.filter_by(school_id=school.id).count() == 4


def test_signup_rejects_duplicate_slug(app, db, client):
    make_school(db, slug='taken')
    db.session.commit()
    resp = client.post('/signup', data={
        'school_name': 'X', 'slug': 'taken', 'admin_name': 'A',
        'admin_email': 'a@x.test', 'password': 'longenough', 'template': 'blank',
    })
    assert resp.status_code == 400
    assert b'taken' in resp.data


def test_signup_rejects_short_password(app, db, client):
    resp = client.post('/signup', data={
        'school_name': 'X', 'slug': 'x-school', 'admin_name': 'A',
        'admin_email': 'a@x.test', 'password': 'short', 'template': 'blank',
    })
    assert resp.status_code == 400
    assert School.query.filter_by(slug='x-school').first() is None
