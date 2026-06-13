"""Step 4 route tests: access control, grid save, summary render."""
from datetime import date, timedelta

from models.enums import UserRole
from models.operational import AttendanceRecord
from tests.factories import make_school, make_user, make_student, make_class


PAST = (date.today().replace(day=1) - timedelta(days=1)).replace(day=10)


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


# --- Access control ---------------------------------------------------------
def test_attendance_requires_teacher_or_admin(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='p@s.test', role=UserRole.parent)
    db.session.commit()
    _login(client, 's', 'p@s.test')
    assert client.get('/teacher/attendance').status_code == 403


def test_admin_sees_attendance_page(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    assert client.get('/teacher/attendance').status_code == 200


def test_teacher_cannot_open_unassigned_class(app, db, client):
    s = make_school(db, slug='s')
    teacher = make_user(db, s, email='t@s.test', role=UserRole.teacher)
    c = make_class(db, s)  # teacher not assigned, not class teacher
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get(f'/teacher/attendance?class_id={c.id}').status_code == 404


def test_cross_school_class_404(app, db, client):
    a = make_school(db, slug='a'); b = make_school(db, slug='b')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    c_b = make_class(db, b)
    db.session.commit()
    _login(client, 'a', 'a@a.test')
    assert client.get(f'/teacher/attendance?class_id={c_b.id}').status_code == 404


# --- Grid save --------------------------------------------------------------
def test_save_attendance_via_route(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    c = make_class(db, s)
    s1 = make_student(db, s, admission_no='A1', current_class_id=c.id)
    s2 = make_student(db, s, admission_no='A2', current_class_id=c.id)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post(f'/teacher/attendance?class_id={c.id}&date={PAST.isoformat()}',
                data={f'status_{s1.id}': 'present', f'status_{s2.id}': 'absent'},
                follow_redirects=True)
    assert AttendanceRecord.query.filter_by(school_id=s.id, class_id=c.id).count() == 2


def test_grid_shows_existing_marks(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    c = make_class(db, s)
    s1 = make_student(db, s, admission_no='A1', current_class_id=c.id)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post(f'/teacher/attendance?class_id={c.id}&date={PAST.isoformat()}',
                data={f'status_{s1.id}': 'late'})
    resp = client.get(f'/teacher/attendance?class_id={c.id}&date={PAST.isoformat()}')
    assert resp.status_code == 200
    # the 'late' radio should be checked
    assert b'value="late" checked' in resp.data


# --- Summary ----------------------------------------------------------------
def test_summary_renders_with_data(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    c = make_class(db, s)
    s1 = make_student(db, s, admission_no='A1', current_class_id=c.id)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post(f'/teacher/attendance?class_id={c.id}&date={PAST.isoformat()}',
                data={f'status_{s1.id}': 'present'})
    resp = client.get(
        f'/teacher/attendance/summary?class_id={c.id}'
        f'&year={PAST.year}&month={PAST.month}')
    assert resp.status_code == 200
    assert b'Present: 1' in resp.data


def test_summary_renders_without_selection(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    assert client.get('/teacher/attendance/summary').status_code == 200
