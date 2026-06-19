"""
Timetabling service. Tenant-scoped. Period CRUD + per-class weekly grid with
conflict detection (a teacher can't be booked in two classes at the same
day+period). The (class, day, period) cell itself is unique by DB constraint.
"""
from extensions import db
from models.timetable import Period, TimetableSlot
from models.config_tables import Class, Subject
from models.operational import User
from models.enums import UserRole

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
        'Saturday', 'Sunday']


class TimetableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------
def create_period(school_id, *, name, sequence=0, start_time=None,
                  end_time=None):
    name = (name or '').strip()
    if not name:
        raise TimetableError('Period name is required.')
    if Period.query.filter_by(school_id=school_id, name=name).first():
        raise TimetableError(f'A period named "{name}" already exists.')
    p = Period(school_id=school_id, name=name, sequence=sequence or 0,
               start_time=start_time, end_time=end_time)
    db.session.add(p)
    db.session.flush()
    return p


def delete_period(school_id, period_id):
    p = Period.query.filter_by(school_id=school_id, id=period_id).first()
    if p is None:
        raise TimetableError('Period not found.')
    db.session.delete(p)
    db.session.flush()


def periods(school_id):
    return (Period.query.filter_by(school_id=school_id)
            .order_by(Period.sequence, Period.id).all())


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------
def set_slot(school_id, class_id, day_of_week, period_id, subject_id,
             teacher_user_id=None):
    """
    Create or update a timetable cell. Validates tenancy of all referenced
    rows and rejects a teacher double-booking (same day+period in another class).
    """
    if Class.query.filter_by(school_id=school_id, id=class_id).first() is None:
        raise TimetableError('Class not found.')
    if Period.query.filter_by(school_id=school_id, id=period_id).first() is None:
        raise TimetableError('Period not found.')
    if Subject.query.filter_by(school_id=school_id, id=subject_id).first() is None:
        raise TimetableError('Subject not found.')
    if day_of_week is None or day_of_week < 0 or day_of_week > 6:
        raise TimetableError('Invalid day.')

    if teacher_user_id is not None:
        teacher = User.query.filter_by(school_id=school_id,
                                       id=teacher_user_id).first()
        if teacher is None or teacher.role != UserRole.teacher:
            raise TimetableError('Teacher not found.')
        # Conflict: this teacher already booked elsewhere at this day+period.
        clash = TimetableSlot.query.filter(
            TimetableSlot.school_id == school_id,
            TimetableSlot.day_of_week == day_of_week,
            TimetableSlot.period_id == period_id,
            TimetableSlot.teacher_user_id == teacher_user_id,
            TimetableSlot.class_id != class_id,
        ).first()
        if clash is not None:
            other = db.session.get(Class, clash.class_id)
            raise TimetableError(
                f'{teacher.name} is already teaching '
                f'{other.name if other else "another class"} at that time.')

    slot = TimetableSlot.query.filter_by(
        school_id=school_id, class_id=class_id, day_of_week=day_of_week,
        period_id=period_id).first()
    if slot is None:
        slot = TimetableSlot(school_id=school_id, class_id=class_id,
                             day_of_week=day_of_week, period_id=period_id,
                             subject_id=subject_id,
                             teacher_user_id=teacher_user_id)
        db.session.add(slot)
    else:
        slot.subject_id = subject_id
        slot.teacher_user_id = teacher_user_id
    db.session.flush()
    return slot


def clear_slot(school_id, class_id, day_of_week, period_id):
    slot = TimetableSlot.query.filter_by(
        school_id=school_id, class_id=class_id, day_of_week=day_of_week,
        period_id=period_id).first()
    if slot is not None:
        db.session.delete(slot)
        db.session.flush()
    return True


def class_grid(school_id, class_id):
    """{(day, period_id): slot} for a class."""
    rows = TimetableSlot.query.filter_by(
        school_id=school_id, class_id=class_id).all()
    return {(r.day_of_week, r.period_id): r for r in rows}


def teacher_grid(school_id, teacher_user_id):
    """{(day, period_id): slot} for a teacher across all classes."""
    rows = TimetableSlot.query.filter_by(
        school_id=school_id, teacher_user_id=teacher_user_id).all()
    return {(r.day_of_week, r.period_id): r for r in rows}
