"""Tests for Phase 1 hardening: health, headers, 500 handling, student edit."""
from models.enums import UserRole
from models.operational import Student
from services import people
from services.people import PeopleError
from tests.factories import make_school, make_user, make_student
import pytest


# --- Health + headers -------------------------------------------------------
def test_health_ok(app, client):
    r = client.get('/health')
    assert r.status_code == 200 and r.get_json()['status'] == 'ok'


def test_health_needs_no_login(app, client):
    # health must be reachable without auth (Coolify probes it).
    r = client.get('/health')
    assert r.status_code == 200


def test_security_headers_present(app, client):
    r = client.get('/health')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert r.headers.get('Referrer-Policy') == 'same-origin'


# --- Student edit (service) -------------------------------------------------
def test_update_student_changes_fields(app, db):
    s = make_school(db, slug='s')
    st = people.create_student(s.id, admission_no='A1', first_name='Ama',
                               last_name='Owsu')  # typo
    db.session.commit()
    people.update_student(s.id, st.id, last_name='Owusu', guardian_name='Mary')
    db.session.commit()
    fresh = db.session.get(Student, st.id)
    assert fresh.last_name == 'Owusu' and fresh.guardian_name == 'Mary'


def test_update_student_duplicate_admission_rejected(app, db):
    s = make_school(db, slug='s')
    people.create_student(s.id, admission_no='A1', first_name='X', last_name='Y')
    st2 = people.create_student(s.id, admission_no='A2', first_name='P', last_name='Q')
    db.session.commit()
    with pytest.raises(PeopleError, match='already exists'):
        people.update_student(s.id, st2.id, admission_no='A1')  # collides


def test_update_student_keeps_own_admission_no(app, db):
    """Editing other fields while keeping the same admission_no must be allowed."""
    s = make_school(db, slug='s')
    st = people.create_student(s.id, admission_no='A1', first_name='X', last_name='Y')
    db.session.commit()
    people.update_student(s.id, st.id, admission_no='A1', first_name='Xavier')
    db.session.commit()
    assert db.session.get(Student, st.id).first_name == 'Xavier'


def test_update_student_cross_school_blocked(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    b_student = people.create_student(b.id, admission_no='B1', first_name='X', last_name='Y')
    db.session.commit()
    with pytest.raises(PeopleError, match='not found'):
        people.update_student(a.id, b_student.id, first_name='Hacked')


# --- Student edit (route) ---------------------------------------------------
def test_edit_student_via_route(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    st = make_student(db, s, admission_no='A1', first='Ama', last='Owsu')
    db.session.commit()
    client.post('/auth/login', data={'school_slug': 's', 'email': 'a@s.test',
                                     'password': 'pw'})
    client.post(f'/admin/students/{st.id}/edit',
                data={'admission_no': 'A1', 'first_name': 'Ama',
                      'last_name': 'Owusu'}, follow_redirects=True)
    assert db.session.get(Student, st.id).last_name == 'Owusu'


def test_edit_other_school_student_404(app, db, client):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    b_student = make_student(db, b, admission_no='B1')
    db.session.commit()
    client.post('/auth/login', data={'school_slug': 'a', 'email': 'a@a.test',
                                     'password': 'pw'})
    # update_student raises PeopleError -> flashed, but the row must be untouched
    client.post(f'/admin/students/{b_student.id}/edit',
                data={'first_name': 'Hacked'}, follow_redirects=True)
    assert db.session.get(Student, b_student.id).first_name != 'Hacked'
