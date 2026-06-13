"""
Portal service (Step 7) — student + parent self-service, PUBLISHED data only.

Hard security rules:
  - A student user sees ONLY their own Student record (Student.user_id == user.id).
  - A parent user sees ONLY students linked via parent_students.
  - Results are PUBLISHED-only (reuses report_card.build_report_card with
    include_unpublished=False).
  - Everything is tenant-scoped to g.current_school_id (the user's own school).

Any attempt to view a student you're not entitled to raises PortalError, which
routes translate to 404 (don't leak existence).
"""
from extensions import db
from models.enums import UserRole
from models.operational import (
    Student, ParentStudent, TermResult, AttendanceRecord,
)
from models.config_tables import Subject, Term, Class
from services import report_card


class PortalError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Who can the logged-in user see?
# ---------------------------------------------------------------------------
def student_for_user(school_id, user_id):
    """The Student record owned by this login (or None)."""
    return Student.query.filter_by(school_id=school_id, user_id=user_id).first()


def children_for_parent(school_id, parent_user_id):
    """Students linked to this parent, ordered by name."""
    return (db.session.query(Student)
            .join(ParentStudent, ParentStudent.student_id == Student.id)
            .filter(ParentStudent.school_id == school_id,
                    ParentStudent.parent_user_id == parent_user_id)
            .order_by(Student.last_name, Student.first_name)
            .all())


def assert_can_view(school_id, user, student_id):
    """
    Raise PortalError unless `user` may view student_id.
      - student role: only their own student record.
      - parent role: only a linked child.
    Returns the Student on success.
    """
    role = getattr(user, 'role', None)
    role = role.value if hasattr(role, 'value') else role
    student = Student.query.filter_by(school_id=school_id, id=student_id).first()
    if student is None:
        raise PortalError('Not found.')

    if role == UserRole.student.value:
        if student.user_id == user.id:
            return student
    elif role == UserRole.parent.value:
        link = ParentStudent.query.filter_by(
            school_id=school_id, parent_user_id=user.id,
            student_id=student_id).first()
        if link is not None:
            return student
    raise PortalError('Not found.')


# ---------------------------------------------------------------------------
# Data views (published-only)
# ---------------------------------------------------------------------------
def published_terms(school_id, student_id):
    """Terms that have at least one PUBLISHED result for this student."""
    term_ids = {
        tid for (tid,) in
        TermResult.query.with_entities(TermResult.term_id)
        .filter_by(school_id=school_id, student_id=student_id,
                   is_published=True).all()
    }
    if not term_ids:
        return []
    return (Term.query.filter(Term.school_id == school_id,
                              Term.id.in_(term_ids))
            .order_by(Term.sequence).all())


def published_results(school_id, student_id, term_id):
    """Published TermResult rows for a student+term, with subject names."""
    rows = TermResult.query.filter_by(
        school_id=school_id, student_id=student_id, term_id=term_id,
        is_published=True).all()
    names = {s.id: s.name for s in Subject.query.filter_by(
        school_id=school_id).all()}
    out = []
    for r in sorted(rows, key=lambda x: names.get(x.subject_id, '')):
        out.append({
            'subject': names.get(r.subject_id, r.subject_id),
            'total_score': r.total_score, 'grade_label': r.grade_label,
            'remark': r.remark, 'is_pass': r.is_pass,
            'class_position': r.class_position,
        })
    return out


def attendance_summary(school_id, student_id):
    """Lifetime attendance counts for a student (own data only)."""
    counts = {'present': 0, 'absent': 0, 'late': 0, 'excused': 0}
    total = 0
    for r in AttendanceRecord.query.filter_by(
            school_id=school_id, student_id=student_id).all():
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
        total += 1
    counts['total'] = total
    return counts


def student_overview(school_id, student):
    """Profile + attendance + published terms for a portal landing."""
    klass = (Class.query.filter_by(school_id=school_id,
                                   id=student.current_class_id).first()
             if student.current_class_id else None)
    return {
        'student': student,
        'klass': klass,
        'attendance': attendance_summary(school_id, student.id),
        'terms': published_terms(school_id, student.id),
    }


def report_card_published(school_id, student_id, term_id):
    """Report card with PUBLISHED results only (for portals)."""
    return report_card.build_report_card(
        school_id, student_id, term_id, include_unpublished=False)
