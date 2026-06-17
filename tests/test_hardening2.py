"""Hardening round 2: uploads, edit coverage, self password change."""
import io

import pytest

from models.enums import UserRole
from models.operational import User, Student
from models.config_tables import Subject
from models.platform import Plan
from services import people, uploads
from services.uploads import UploadError
from auth.security import verify_password, hash_password
from tests.factories import make_school, make_user, make_student, make_platform_user


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


def _img_bytes():
    # A 1x1 PNG.
    return (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00'
            b'\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc'
            b'\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


# --- Upload service ---------------------------------------------------------
def test_upload_rejects_bad_extension(app, db):
    from werkzeug.datastructures import FileStorage
    fs = FileStorage(stream=io.BytesIO(b'x'), filename='evil.exe')
    with pytest.raises(UploadError, match='Unsupported'):
        uploads.save_upload(fs, 1, 'photo', images_only=True)


def test_upload_rejects_empty(app, db):
    from werkzeug.datastructures import FileStorage
    fs = FileStorage(stream=io.BytesIO(b''), filename='x.png')
    with pytest.raises(UploadError, match='empty'):
        uploads.save_upload(fs, 1, 'photo')


def test_belongs_to_school():
    assert uploads.belongs_to_school('3/logo/a.png', 3) is True
    assert uploads.belongs_to_school('3/logo/a.png', 4) is False
    assert uploads.belongs_to_school(None, 3) is False


def test_abs_path_rejects_traversal(app):
    # A path trying to escape the upload root resolves to None.
    assert uploads.abs_path_for('../../etc/passwd') is None


# --- Student photo upload (route) -------------------------------------------
def test_student_photo_upload(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    st = make_student(db, s, admission_no='A1')
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.post(f'/admin/students/{st.id}/photo',
                    data={'photo': (io.BytesIO(_img_bytes()), 'p.png')},
                    content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Student, st.id).photo_path is not None


def test_media_serve_tenant_scoped(app, db, client):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 'a', 'a@a.test')
    # School A user requesting a path under school B's folder -> 404.
    assert client.get('/media/{}/logo/x.png'.format(b.id)).status_code == 404


# --- Edit coverage ----------------------------------------------------------
def test_subject_edit_route(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    subj = Subject(school_id=s.id, name='Maths', is_core=True)
    db.session.add(subj)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post(f'/admin/config/subjects/{subj.id}/edit',
                data={'name': 'Mathematics', 'code': 'MATH'},
                follow_redirects=True)
    assert db.session.get(Subject, subj.id).name == 'Mathematics'


def test_user_edit_route(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    t = make_user(db, s, email='t@s.test', role=UserRole.teacher, name='Old Name')
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post(f'/admin/users/{t.id}/edit',
                data={'name': 'New Name', 'email': 't@s.test'},
                follow_redirects=True)
    assert db.session.get(User, t.id).name == 'New Name'


def test_user_edit_duplicate_email_rejected(app, db):
    s = make_school(db, slug='s')
    people.create_user(s.id, name='A', email='a@s.test', role='teacher')
    u2, _ = people.create_user(s.id, name='B', email='b@s.test', role='teacher')
    db.session.commit()
    from services.people import PeopleError
    with pytest.raises(PeopleError, match='already exists'):
        people.update_user(s.id, u2.id, email='a@s.test')


def test_plan_edit_route(app, db, client):
    make_plan = Plan(name='Std', price_ghs=100)
    db.session.add(make_plan)
    db.session.commit()
    make_platform_user(db, email='super@x.test')
    db.session.commit()
    client.post('/auth/login', data={'school_slug': '', 'email': 'super@x.test',
                                     'password': 'pw'})
    client.post(f'/platform/plans/{make_plan.id}/edit',
                data={'name': 'Std', 'price_ghs': '250', 'billing_cycle': 'annual'},
                follow_redirects=True)
    assert db.session.get(Plan, make_plan.id).price_ghs == 250


# --- Self password change ---------------------------------------------------
def test_change_password_success(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin, password='oldpass1')
    db.session.commit()
    _login(client, 's', 'a@s.test', password='oldpass1')
    r = client.post('/auth/change-password', data={
        'current_password': 'oldpass1', 'new_password': 'newpass123',
        'confirm_password': 'newpass123'}, follow_redirects=True)
    assert r.status_code == 200
    u = User.query.filter_by(email='a@s.test').first()
    assert verify_password(u.password_hash, 'newpass123')


def test_change_password_wrong_current(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin, password='oldpass1')
    db.session.commit()
    _login(client, 's', 'a@s.test', password='oldpass1')
    client.post('/auth/change-password', data={
        'current_password': 'WRONG', 'new_password': 'newpass123',
        'confirm_password': 'newpass123'}, follow_redirects=True)
    u = User.query.filter_by(email='a@s.test').first()
    assert verify_password(u.password_hash, 'oldpass1')  # unchanged


def test_change_password_mismatch(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin, password='oldpass1')
    db.session.commit()
    _login(client, 's', 'a@s.test', password='oldpass1')
    client.post('/auth/change-password', data={
        'current_password': 'oldpass1', 'new_password': 'newpass123',
        'confirm_password': 'different'}, follow_redirects=True)
    u = User.query.filter_by(email='a@s.test').first()
    assert verify_password(u.password_hash, 'oldpass1')  # unchanged
