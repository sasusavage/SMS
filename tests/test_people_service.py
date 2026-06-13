"""Tests for the Step 3 people service layer."""
import pytest

from services import people
from services.people import PeopleError
from models.enums import UserRole, StudentStatus
from models.operational import User, Student, ParentStudent, TeacherAssignment
from models.config_tables import Class, Subject, Term, Level, LevelGroup, AcademicYear
from tests.factories import make_school, make_user, make_student


# --- Users ------------------------------------------------------------------
def test_create_user_generates_password(app, db):
    s = make_school(db, slug='s')
    user, pw = people.create_user(s.id, name='T One', email='t1@s.test',
                                  role='teacher')
    db.session.commit()
    assert user.id and pw and len(pw) >= 8
    assert user.role == UserRole.teacher


def test_create_user_duplicate_email_rejected(app, db):
    s = make_school(db, slug='s')
    people.create_user(s.id, name='A', email='dup@s.test', role='teacher')
    db.session.commit()
    with pytest.raises(PeopleError, match='already exists'):
        people.create_user(s.id, name='B', email='dup@s.test', role='parent')


def test_same_email_allowed_in_different_schools(app, db):
    a = make_school(db, slug='a'); b = make_school(db, slug='b')
    people.create_user(a.id, name='A', email='same@x.test', role='teacher')
    people.create_user(b.id, name='B', email='same@x.test', role='teacher')
    db.session.commit()  # must not raise


def test_reset_password_scoped(app, db):
    a = make_school(db, slug='a'); b = make_school(db, slug='b')
    ua, _ = people.create_user(a.id, name='A', email='a@a.test', role='teacher')
    db.session.commit()
    # Resetting from another school must fail (not found)
    with pytest.raises(PeopleError, match='not found'):
        people.reset_password(b.id, ua.id)
    new = people.reset_password(a.id, ua.id)
    assert len(new) >= 8


def test_deactivate_user(app, db):
    s = make_school(db, slug='s')
    u, _ = people.create_user(s.id, name='A', email='a@s.test', role='teacher')
    db.session.commit()
    people.set_user_active(s.id, u.id, False)
    db.session.commit()
    assert db.session.get(User, u.id).is_active is False


# --- Students ---------------------------------------------------------------
def test_create_student_ok(app, db):
    s = make_school(db, slug='s')
    st = people.create_student(s.id, admission_no='A1', first_name='Ama',
                               last_name='Owusu')
    db.session.commit()
    assert st.id and st.status == StudentStatus.active


def test_duplicate_admission_no_per_school_rejected(app, db):
    s = make_school(db, slug='s')
    people.create_student(s.id, admission_no='A1', first_name='X', last_name='Y')
    db.session.commit()
    with pytest.raises(PeopleError, match='already exists'):
        people.create_student(s.id, admission_no='A1', first_name='P', last_name='Q')


def test_same_admission_no_different_schools_ok(app, db):
    a = make_school(db, slug='a'); b = make_school(db, slug='b')
    people.create_student(a.id, admission_no='SAME', first_name='X', last_name='Y')
    people.create_student(b.id, admission_no='SAME', first_name='P', last_name='Q')
    db.session.commit()


def _class_in(db, school):
    lg = LevelGroup(school_id=school.id, name='G', sequence=1)
    db.session.add(lg); db.session.flush()
    lvl = Level(school_id=school.id, level_group_id=lg.id, name='L', sequence=1)
    ay = AcademicYear(school_id=school.id, name='2025/2026')
    db.session.add_all([lvl, ay]); db.session.flush()
    c = Class(school_id=school.id, level_id=lvl.id, academic_year_id=ay.id, name='C')
    db.session.add(c); db.session.flush()
    return c


def test_transfer_student_rejects_other_school_class(app, db):
    a = make_school(db, slug='a'); b = make_school(db, slug='b')
    st = people.create_student(a.id, admission_no='A1', first_name='X', last_name='Y')
    b_class = _class_in(db, b)
    db.session.commit()
    with pytest.raises(PeopleError, match='Class not found'):
        people.transfer_student(a.id, st.id, b_class.id)


# --- CSV import -------------------------------------------------------------
GOOD_CSV = (
    "admission_no,first_name,last_name,other_names,gender,dob,guardian_name,guardian_phone\n"
    "A1,Ama,Owusu,,F,2012-05-01,Mary,024000\n"
    "A2,Kofi,Mensah,Kojo,M,2011-03-15,John,024111\n"
)


def test_csv_preview_all_valid(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    preview = people.parse_student_csv(s.id, GOOD_CSV)
    assert preview['headers_ok'] and preview['valid'] == 2 and preview['invalid'] == 0


def test_csv_preview_detects_missing_required(app, db):
    s = make_school(db, slug='s'); db.session.commit()
    bad = "admission_no,first_name,last_name\nA1,,Owusu\n,Kofi,Mensah\n"
    preview = people.parse_student_csv(s.id, bad)
    assert preview['valid'] == 0 and preview['invalid'] == 2
    assert any('first_name is required' in e for e in preview['rows'][0]['errors'])


def test_csv_preview_detects_in_file_and_db_dups(app, db):
    s = make_school(db, slug='s')
    people.create_student(s.id, admission_no='EXIST', first_name='X', last_name='Y')
    db.session.commit()
    csv_text = ("admission_no,first_name,last_name\n"
                "EXIST,A,B\n"      # already in DB
                "DUP,C,D\n"
                "DUP,E,F\n")       # duplicated in file
    preview = people.parse_student_csv(s.id, csv_text)
    assert preview['invalid'] == 2
    assert any('already exists' in e for e in preview['rows'][0]['errors'])
    assert any('duplicated in the file' in e for e in preview['rows'][2]['errors'])


def test_csv_bad_headers_rejected(app, db):
    s = make_school(db, slug='s'); db.session.commit()
    preview = people.parse_student_csv(s.id, "name,age\nfoo,10\n")
    assert preview['headers_ok'] is False
    assert 'Missing required column' in preview['header_error']


def test_csv_commit_imports_only_valid_rows(app, db):
    s = make_school(db, slug='s')
    people.create_student(s.id, admission_no='EXIST', first_name='X', last_name='Y')
    db.session.commit()
    csv_text = ("admission_no,first_name,last_name\n"
                "EXIST,A,B\n"   # dup -> skipped
                "NEW1,C,D\n"
                "NEW2,E,F\n")
    result = people.commit_student_csv(s.id, csv_text)
    db.session.commit()
    assert result == {'imported': 2, 'skipped': 1}
    assert Student.query.filter_by(school_id=s.id).count() == 3


def test_csv_commit_bad_headers_raises(app, db):
    s = make_school(db, slug='s'); db.session.commit()
    with pytest.raises(PeopleError):
        people.commit_student_csv(s.id, "wrong,cols\n1,2\n")


# --- Parent linking ---------------------------------------------------------
def test_link_parent_student(app, db):
    s = make_school(db, slug='s')
    parent, _ = people.create_user(s.id, name='P', email='p@s.test', role='parent')
    st = people.create_student(s.id, admission_no='A1', first_name='X', last_name='Y')
    db.session.commit()
    link = people.link_parent_student(s.id, parent.id, st.id, 'Mother')
    db.session.commit()
    assert link.id and link.relationship_label == 'Mother'


def test_link_rejects_non_parent_user(app, db):
    s = make_school(db, slug='s')
    teacher, _ = people.create_user(s.id, name='T', email='t@s.test', role='teacher')
    st = people.create_student(s.id, admission_no='A1', first_name='X', last_name='Y')
    db.session.commit()
    with pytest.raises(PeopleError, match='not a parent'):
        people.link_parent_student(s.id, teacher.id, st.id)


def test_link_duplicate_rejected(app, db):
    s = make_school(db, slug='s')
    parent, _ = people.create_user(s.id, name='P', email='p@s.test', role='parent')
    st = people.create_student(s.id, admission_no='A1', first_name='X', last_name='Y')
    db.session.commit()
    people.link_parent_student(s.id, parent.id, st.id)
    db.session.commit()
    with pytest.raises(PeopleError, match='already linked'):
        people.link_parent_student(s.id, parent.id, st.id)


def test_link_rejects_cross_school_student(app, db):
    a = make_school(db, slug='a'); b = make_school(db, slug='b')
    parent, _ = people.create_user(a.id, name='P', email='p@a.test', role='parent')
    b_student = people.create_student(b.id, admission_no='B1', first_name='X', last_name='Y')
    db.session.commit()
    with pytest.raises(PeopleError, match='Student not found'):
        people.link_parent_student(a.id, parent.id, b_student.id)


# --- Teacher assignments ----------------------------------------------------
def test_assign_teacher_and_uniqueness(app, db):
    s = make_school(db, slug='s')
    teacher, _ = people.create_user(s.id, name='T', email='t@s.test', role='teacher')
    c = _class_in(db, s)
    subj = Subject(school_id=s.id, name='Math', is_core=True)
    term = Term(school_id=s.id, academic_year_id=c.academic_year_id, name='T1', sequence=1)
    db.session.add_all([subj, term]); db.session.commit()
    people.assign_teacher(s.id, teacher.id, c.id, subj.id, term.id)
    db.session.commit()
    with pytest.raises(PeopleError, match='already assigned'):
        people.assign_teacher(s.id, teacher.id, c.id, subj.id, term.id)


def test_assign_rejects_non_teacher(app, db):
    s = make_school(db, slug='s')
    parent, _ = people.create_user(s.id, name='P', email='p@s.test', role='parent')
    c = _class_in(db, s)
    subj = Subject(school_id=s.id, name='Math', is_core=True)
    term = Term(school_id=s.id, academic_year_id=c.academic_year_id, name='T1', sequence=1)
    db.session.add_all([subj, term]); db.session.commit()
    with pytest.raises(PeopleError, match='not a teacher'):
        people.assign_teacher(s.id, parent.id, c.id, subj.id, term.id)
