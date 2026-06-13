"""
Attendance service (Step 4).

Daily attendance grid (one record per student per day — upsert) and a monthly
summary per class. All functions are tenant-scoped via an explicit school_id
and never read or write across schools.

Access model:
  - school_admin: any class in their school.
  - teacher: classes they are the class_teacher of, OR are assigned to via a
    TeacherAssignment (any subject/term). Enforced by teacher_can_access_class.

Raises AttendanceError (UI-safe .message) on validation/permission problems.
"""
from calendar import monthrange
from datetime import date

from extensions import db
from models.enums import AttendanceStatus, UserRole
from models.operational import (
    AttendanceRecord, Student, User, TeacherAssignment,
)
from models.config_tables import Class

VALID_STATUSES = {s.value for s in AttendanceStatus}


class AttendanceError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------
def teacher_can_access_class(school_id, user, class_id):
    """
    True if `user` may mark attendance for class_id in this school.
    Admins: always (within school). Teachers: class teacher or assigned.
    """
    klass = Class.query.filter_by(school_id=school_id, id=class_id).first()
    if klass is None:
        return False
    role = getattr(user, 'role', None)
    role = role.value if hasattr(role, 'value') else role
    if role == UserRole.school_admin.value:
        return True
    if role == UserRole.teacher.value:
        if klass.class_teacher_id == user.id:
            return True
        assigned = TeacherAssignment.query.filter_by(
            school_id=school_id, teacher_user_id=user.id,
            class_id=class_id).first()
        return assigned is not None
    return False


def accessible_classes(school_id, user):
    """Classes the user may take attendance for, ordered by name."""
    role = getattr(user, 'role', None)
    role = role.value if hasattr(role, 'value') else role
    base = Class.query.filter_by(school_id=school_id)
    if role == UserRole.school_admin.value:
        return base.order_by(Class.name).all()
    if role == UserRole.teacher.value:
        assigned_ids = {
            cid for (cid,) in
            TeacherAssignment.query
            .with_entities(TeacherAssignment.class_id)
            .filter_by(school_id=school_id, teacher_user_id=user.id).all()
        }
        classes = base.order_by(Class.name).all()
        return [c for c in classes
                if c.id in assigned_ids or c.class_teacher_id == user.id]
    return []


# ---------------------------------------------------------------------------
# Daily grid
# ---------------------------------------------------------------------------
def get_class_roster(school_id, class_id):
    """Active students currently in the class, ordered by name."""
    return (Student.query
            .filter_by(school_id=school_id, current_class_id=class_id)
            .order_by(Student.last_name, Student.first_name).all())


def get_day_attendance(school_id, class_id, on_date):
    """Map of student_id -> status value for an existing day (may be empty)."""
    rows = AttendanceRecord.query.filter_by(
        school_id=school_id, class_id=class_id, date=on_date).all()
    return {r.student_id: r.status.value for r in rows}


def save_day_attendance(school_id, class_id, on_date, marks, marked_by=None):
    """
    Upsert attendance for a class on a date.

    `marks`: dict of {student_id: status_value}. Only students currently in the
    class are accepted (others are ignored — prevents cross-class/-tenant writes
    via a tampered form). Existing records for the day are updated; missing ones
    are created. Returns count saved.
    """
    if on_date is None:
        raise AttendanceError('A date is required.')
    if on_date > date.today():
        raise AttendanceError('Cannot mark attendance for a future date.')

    roster_ids = {s.id for s in get_class_roster(school_id, class_id)}
    if not roster_ids:
        raise AttendanceError('This class has no students.')

    existing = {
        r.student_id: r for r in AttendanceRecord.query.filter_by(
            school_id=school_id, class_id=class_id, date=on_date).all()
    }

    saved = 0
    for student_id, status_value in marks.items():
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            continue
        if student_id not in roster_ids:
            continue  # ignore anything not on this class's roster
        if status_value not in VALID_STATUSES:
            raise AttendanceError(f'Invalid status: {status_value!r}.')

        rec = existing.get(student_id)
        if rec is None:
            rec = AttendanceRecord(
                school_id=school_id, student_id=student_id, class_id=class_id,
                date=on_date, status=AttendanceStatus(status_value),
                marked_by=marked_by)
            db.session.add(rec)
        else:
            rec.status = AttendanceStatus(status_value)
            rec.marked_by = marked_by
        saved += 1

    db.session.flush()
    return saved


# ---------------------------------------------------------------------------
# Monthly summary
# ---------------------------------------------------------------------------
def monthly_summary(school_id, class_id, year, month):
    """
    Per-student counts for a month:
      {
        'days': [date, ...],                 # days that have any record
        'students': [
           {'student': Student,
            'counts': {'present': n, 'absent': n, 'late': n, 'excused': n},
            'total': n},
           ...
        ],
        'totals': {'present': n, ...},       # class totals for the month
      }
    """
    if month < 1 or month > 12:
        raise AttendanceError('Invalid month.')
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])

    records = AttendanceRecord.query.filter(
        AttendanceRecord.school_id == school_id,
        AttendanceRecord.class_id == class_id,
        AttendanceRecord.date >= first,
        AttendanceRecord.date <= last,
    ).all()

    by_student = {}
    days = set()
    totals = {s.value: 0 for s in AttendanceStatus}
    for r in records:
        days.add(r.date)
        bucket = by_student.setdefault(
            r.student_id, {s.value: 0 for s in AttendanceStatus})
        bucket[r.status.value] += 1
        totals[r.status.value] += 1

    roster = get_class_roster(school_id, class_id)
    students = []
    for s in roster:
        counts = by_student.get(s.id, {st.value: 0 for st in AttendanceStatus})
        students.append({
            'student': s,
            'counts': counts,
            'total': sum(counts.values()),
        })

    return {
        'days': sorted(days),
        'students': students,
        'totals': totals,
        'first': first,
        'last': last,
    }
