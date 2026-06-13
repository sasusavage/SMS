"""Tests for the Step 4 attendance service."""
from datetime import date, timedelta

import pytest

from services import attendance
from services.attendance import AttendanceError
from models.enums import UserRole, AttendanceStatus
from models.operational import AttendanceRecord, TeacherAssignment
from models.config_tables import Subject, Term
from tests.factories import make_school, make_user, make_student, make_class


def _roster(db, school, klass, n=3):
    students = []
    for i in range(n):
        students.append(make_student(db, school, admission_no=f'A{i}',
                                     first=f'F{i}', last=f'L{i}',
                                     current_class_id=klass.id))
    db.session.flush()
    return students


# Two safely-past dates in the SAME month, regardless of when the suite runs:
# the 10th and 11th of the previous calendar month.
_prev_month_last = date.today().replace(day=1) - timedelta(days=1)
PAST = _prev_month_last.replace(day=10)
PAST2 = _prev_month_last.replace(day=11)


# --- Daily grid upsert ------------------------------------------------------
def test_save_creates_records(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c)
    db.session.commit()
    marks = {students[0].id: 'present', students[1].id: 'absent',
             students[2].id: 'late'}
    saved = attendance.save_day_attendance(s.id, c.id, PAST, marks)
    db.session.commit()
    assert saved == 3
    assert AttendanceRecord.query.filter_by(school_id=s.id, class_id=c.id).count() == 3


def test_save_is_upsert_not_duplicate(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c)
    db.session.commit()
    d = PAST
    attendance.save_day_attendance(s.id, c.id, d, {students[0].id: 'present'})
    db.session.commit()
    # Re-mark the same student the same day -> update, not a second row
    attendance.save_day_attendance(s.id, c.id, d, {students[0].id: 'absent'})
    db.session.commit()
    rows = AttendanceRecord.query.filter_by(
        school_id=s.id, student_id=students[0].id, date=d).all()
    assert len(rows) == 1
    assert rows[0].status == AttendanceStatus.absent


def test_get_day_attendance_returns_map(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c, n=2)
    db.session.commit()
    d = PAST
    attendance.save_day_attendance(s.id, c.id, d,
                                   {students[0].id: 'present', students[1].id: 'late'})
    db.session.commit()
    m = attendance.get_day_attendance(s.id, c.id, d)
    assert m == {students[0].id: 'present', students[1].id: 'late'}


def test_save_ignores_students_not_in_class(app, db):
    """A tampered form id for another class/student must not be written."""
    s = make_school(db, slug='s')
    c = make_class(db, s, name='C1')
    other = make_student(db, s, admission_no='OUT', current_class_id=None)
    students = _roster(db, s, c, n=1)
    db.session.commit()
    saved = attendance.save_day_attendance(
        s.id, c.id, PAST,
        {students[0].id: 'present', other.id: 'present'})
    db.session.commit()
    assert saved == 1
    assert AttendanceRecord.query.filter_by(student_id=other.id).count() == 0


def test_save_rejects_future_date(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c, n=1)
    db.session.commit()
    future = date.today() + timedelta(days=1)
    with pytest.raises(AttendanceError, match='future'):
        attendance.save_day_attendance(s.id, c.id, future, {students[0].id: 'present'})


def test_save_rejects_invalid_status(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c, n=1)
    db.session.commit()
    with pytest.raises(AttendanceError, match='Invalid status'):
        attendance.save_day_attendance(s.id, c.id, PAST,
                                       {students[0].id: 'teleported'})


def test_save_empty_class_rejected(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    db.session.commit()
    with pytest.raises(AttendanceError, match='no students'):
        attendance.save_day_attendance(s.id, c.id, PAST, {})


# --- Monthly summary --------------------------------------------------------
def test_monthly_summary_counts(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c, n=2)
    db.session.commit()
    attendance.save_day_attendance(s.id, c.id, PAST,
                                   {students[0].id: 'present', students[1].id: 'absent'})
    attendance.save_day_attendance(s.id, c.id, PAST2,
                                   {students[0].id: 'present', students[1].id: 'present'})
    db.session.commit()
    summary = attendance.monthly_summary(s.id, c.id, PAST.year, PAST.month)
    assert len(summary['students']) == 2
    s0 = next(x for x in summary['students'] if x['student'].id == students[0].id)
    assert s0['counts']['present'] == 2 and s0['total'] == 2
    assert summary['totals']['present'] == 3 and summary['totals']['absent'] == 1
    assert len(summary['days']) == 2


def test_monthly_summary_excludes_other_months(app, db):
    s = make_school(db, slug='s')
    c = make_class(db, s)
    students = _roster(db, s, c, n=1)
    db.session.commit()
    # Use two clearly-past months relative to today, to avoid the future guard.
    today = date.today()
    this_month = today.replace(day=1)
    prev_month_last = this_month - timedelta(days=1)  # last day of previous month
    attendance.save_day_attendance(s.id, c.id, this_month,
                                   {students[0].id: 'present'})
    attendance.save_day_attendance(s.id, c.id, prev_month_last,
                                   {students[0].id: 'absent'})
    db.session.commit()
    summary = attendance.monthly_summary(s.id, c.id, this_month.year,
                                         this_month.month)
    assert summary['totals']['present'] == 1 and summary['totals']['absent'] == 0


# --- Access control ---------------------------------------------------------
def test_admin_can_access_any_class(app, db):
    s = make_school(db, slug='s')
    admin = make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    c = make_class(db, s)
    db.session.commit()
    assert attendance.teacher_can_access_class(s.id, admin, c.id) is True


def test_class_teacher_can_access(app, db):
    s = make_school(db, slug='s')
    teacher = make_user(db, s, email='t@s.test', role=UserRole.teacher)
    c = make_class(db, s, class_teacher_id=teacher.id)
    db.session.commit()
    assert attendance.teacher_can_access_class(s.id, teacher, c.id) is True


def test_unassigned_teacher_cannot_access(app, db):
    s = make_school(db, slug='s')
    teacher = make_user(db, s, email='t@s.test', role=UserRole.teacher)
    c = make_class(db, s)  # not class teacher, not assigned
    db.session.commit()
    assert attendance.teacher_can_access_class(s.id, teacher, c.id) is False


def test_assigned_teacher_can_access(app, db):
    s = make_school(db, slug='s')
    teacher = make_user(db, s, email='t@s.test', role=UserRole.teacher)
    c = make_class(db, s)
    subj = Subject(school_id=s.id, name='Math', is_core=True)
    term = Term(school_id=s.id, academic_year_id=c.academic_year_id,
                name='T1', sequence=1)
    db.session.add_all([subj, term])
    db.session.flush()
    db.session.add(TeacherAssignment(school_id=s.id, teacher_user_id=teacher.id,
                                     class_id=c.id, subject_id=subj.id,
                                     term_id=term.id))
    db.session.commit()
    assert attendance.teacher_can_access_class(s.id, teacher, c.id) is True


def test_cross_school_class_not_accessible(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    admin_a = make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    c_b = make_class(db, b)
    db.session.commit()
    # admin of A cannot access B's class even though they're an admin
    assert attendance.teacher_can_access_class(a.id, admin_a, c_b.id) is False
