"""Step 3 route tests: access control, tenant-scoping, CSV import flow, render."""
import io

from models.enums import UserRole
from models.operational import User, Student, ParentStudent
from services.template_loader import apply_template
from tests.factories import make_school, make_user


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


def _admin(db, slug='s', email=None):
    school = make_school(db, slug=slug)
    email = email or f'admin@{slug}.test'
    make_user(db, school, email=email, role=UserRole.school_admin)
    return school, email


# --- Access control ---------------------------------------------------------
def test_people_requires_admin(app, db, client):
    school = make_school(db, slug='s')
    make_user(db, school, email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get('/admin/users').status_code == 403
    assert client.get('/admin/students').status_code == 403


# --- Users ------------------------------------------------------------------
def test_create_teacher_via_route(app, db, client):
    school, email = _admin(db, slug='s')
    db.session.commit()
    _login(client, 's', email)
    client.post('/admin/users', data={
        'name': 'New Teacher', 'email': 'nt@s.test', 'role': 'teacher'})
    assert User.query.filter_by(school_id=school.id, email='nt@s.test').count() == 1


def test_cannot_reset_other_schools_user(app, db, client):
    a, a_email = _admin(db, slug='a')
    b = make_school(db, slug='b')
    b_user = make_user(db, b, email='b@b.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 'a', a_email)
    resp = client.post(f'/admin/users/{b_user.id}/toggle-active',
                       follow_redirects=False)
    assert resp.status_code == 404  # get_tenant_or_404


# --- Students ---------------------------------------------------------------
def test_create_student_via_route(app, db, client):
    school, email = _admin(db, slug='s')
    db.session.commit()
    _login(client, 's', email)
    client.post('/admin/students', data={
        'admission_no': 'A1', 'first_name': 'Ama', 'last_name': 'Owusu'})
    assert Student.query.filter_by(school_id=school.id).count() == 1


def test_student_detail_other_school_404(app, db, client):
    a, a_email = _admin(db, slug='a')
    b = make_school(db, slug='b')
    from services.people import create_student
    b_student = create_student(b.id, admission_no='B1', first_name='X', last_name='Y')
    db.session.commit()
    _login(client, 'a', a_email)
    assert client.get(f'/admin/students/{b_student.id}').status_code == 404


# --- CSV import flow --------------------------------------------------------
def test_csv_import_preview_then_commit(app, db, client):
    school, email = _admin(db, slug='s')
    db.session.commit()
    _login(client, 's', email)
    csv_bytes = (b"admission_no,first_name,last_name\n"
                 b"A1,Ama,Owusu\n"
                 b"A2,Kofi,Mensah\n")
    # Upload -> preview
    resp = client.post('/admin/students/import',
                       data={'csv_file': (io.BytesIO(csv_bytes), 'students.csv')},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    assert b'2 valid' in resp.data
    # Nothing imported yet
    assert Student.query.filter_by(school_id=school.id).count() == 0
    # Commit
    resp = client.post('/admin/students/import/commit', follow_redirects=True)
    assert Student.query.filter_by(school_id=school.id).count() == 2


def test_csv_import_bad_headers_shows_error(app, db, client):
    school, email = _admin(db, slug='s')
    db.session.commit()
    _login(client, 's', email)
    resp = client.post('/admin/students/import',
                       data={'csv_file': (io.BytesIO(b"foo,bar\n1,2\n"), 'x.csv')},
                       content_type='multipart/form-data')
    assert b'Missing required column' in resp.data


# --- Parent linking via routes ----------------------------------------------
def test_link_parent_via_route(app, db, client):
    school, email = _admin(db, slug='s')
    from services.people import create_user, create_student
    parent, _ = create_user(school.id, name='P', email='p@s.test', role='parent')
    student = create_student(school.id, admission_no='A1', first_name='X', last_name='Y')
    db.session.commit()
    _login(client, 's', email)
    client.post(f'/admin/students/{student.id}/link-parent',
                data={'parent_user_id': parent.id, 'relationship': 'Mother'})
    assert ParentStudent.query.filter_by(school_id=school.id,
                                          student_id=student.id).count() == 1


# --- Render smoke -----------------------------------------------------------
def test_people_pages_render(app, db, client):
    school, email = _admin(db, slug='s')
    apply_template(school.id, 'ghana_ges')
    db.session.commit()
    _login(client, 's', email)
    for path in ['/admin/users', '/admin/students', '/admin/students/import',
                 '/admin/assignments']:
        assert client.get(path).status_code == 200, path
