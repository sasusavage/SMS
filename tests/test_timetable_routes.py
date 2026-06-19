"""Phase 3 timetable route tests."""
from models.enums import UserRole
from models.timetable import Period, TimetableSlot
from models.config_tables import Subject
from services import timetable as tt
from tests.factories import make_school, make_user, make_class


def _login(client, slug, email):
    return client.post('/auth/login', data={'school_slug': slug, 'email': email,
                                            'password': 'pw'})


def _setup(db):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    teacher = make_user(db, s, email='t@s.test', role=UserRole.teacher)
    c = make_class(db, s, name='B1 A')
    subj = Subject(school_id=s.id, name='Maths', is_core=True)
    db.session.add(subj); db.session.flush()
    p = tt.create_period(s.id, name='Period 1', sequence=1)
    db.session.commit()
    return s, teacher, c, subj, p


def test_parent_cannot_access_timetable(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='p@s.test', role=UserRole.parent)
    db.session.commit()
    _login(client, 's', 'p@s.test')
    assert client.get('/timetable/').status_code == 403


def test_admin_creates_period_via_route(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post('/timetable/periods', data={'name': 'Period 1', 'sequence': '1'},
                follow_redirects=True)
    assert Period.query.filter_by(school_id=s.id).count() == 1


def test_admin_sets_slot_via_route(app, db, client):
    s, teacher, c, subj, p = _setup(db)
    _login(client, 's', 'a@s.test')
    client.post('/timetable/set', data={
        'class_id': c.id, 'day_of_week': '0', 'period_id': p.id,
        'subject_id': subj.id, 'teacher_user_id': teacher.id},
        follow_redirects=True)
    assert TimetableSlot.query.filter_by(school_id=s.id).count() == 1


def test_conflict_surfaced_in_route(app, db, client):
    s, teacher, c, subj, p = _setup(db)
    c2 = make_class(db, s, name='B1 B')
    db.session.commit()
    tt.set_slot(s.id, c.id, 0, p.id, subj.id, teacher.id)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.post('/timetable/set', data={
        'class_id': c2.id, 'day_of_week': '0', 'period_id': p.id,
        'subject_id': subj.id, 'teacher_user_id': teacher.id},
        follow_redirects=True)
    assert b'already teaching' in r.data
    assert TimetableSlot.query.filter_by(school_id=s.id).count() == 1


def test_teacher_my_timetable(app, db, client):
    s, teacher, c, subj, p = _setup(db)
    tt.set_slot(s.id, c.id, 0, p.id, subj.id, teacher.id)
    db.session.commit()
    _login(client, 's', 't@s.test')
    r = client.get('/timetable/mine')
    assert r.status_code == 200
    assert b'Maths' in r.data


def test_admin_class_grid_renders(app, db, client):
    s, teacher, c, subj, p = _setup(db)
    _login(client, 's', 'a@s.test')
    assert client.get(f'/timetable/?class_id={c.id}').status_code == 200
