"""
Report card service (Step 6).

Gathers everything needed to render a student's term report card, tenant-scoped.
The LAYOUT is driven entirely by report_settings (what to show), and the data
respects publication: by default only PUBLISHED results are included, so the
same function backs both the admin preview (include_unpublished=True) and the
student/parent portals (published only, Step 7).

No curriculum constants here — grade labels, remarks and points all come from
the snapshot stored on term_results at compute time.
"""
from extensions import db
from models.operational import (
    Student, TermResult, ReportComment, AttendanceRecord,
)
from models.config_tables import (
    Class, Subject, Term, AcademicYear, ReportSettings, GradeBoundary,
    GradingScheme,
)
from models.platform import School


class ReportError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def get_report_settings(school_id):
    rs = ReportSettings.query.filter_by(school_id=school_id).first()
    return rs  # may be None; template falls back to defaults


def build_report_card(school_id, student_id, term_id, include_unpublished=False):
    """
    Returns a dict with everything the template needs:
      school, student, klass, term, academic_year, settings,
      rows: [{subject, total_score, grade_label, remark, is_pass,
              grade_point, class_position}],
      summary: {average, subjects_count, passed, position_overall},
      comments: ReportComment|None,
      attendance: {present, absent, late, excused, total},
      published: bool   # whether any results are published for this student/term

    Raises ReportError if the student/term aren't in this school.
    """
    student = Student.query.filter_by(school_id=school_id, id=student_id).first()
    if student is None:
        raise ReportError('Student not found.')
    term = Term.query.filter_by(school_id=school_id, id=term_id).first()
    if term is None:
        raise ReportError('Term not found.')

    school = db.session.get(School, school_id)
    settings = get_report_settings(school_id)
    klass = (Class.query.filter_by(school_id=school_id,
                                   id=student.current_class_id).first()
             if student.current_class_id else None)
    academic_year = (AcademicYear.query.filter_by(
        school_id=school_id, id=term.academic_year_id).first())

    q = TermResult.query.filter_by(
        school_id=school_id, student_id=student_id, term_id=term_id)
    all_rows = q.all()
    any_published = any(r.is_published for r in all_rows)

    if include_unpublished:
        result_rows = all_rows
    else:
        result_rows = [r for r in all_rows if r.is_published]

    # Friendly subject names + grade points (from the default scheme bands,
    # matched by the snapshot grade_label — points may not be on the snapshot).
    subject_names = {s.id: s.name for s in Subject.query.filter_by(
        school_id=school_id).all()}
    grade_points = _grade_point_map(school_id)

    rows = []
    total_sum = 0.0
    passed = 0
    for r in sorted(result_rows, key=lambda x: subject_names.get(x.subject_id, '')):
        gp = grade_points.get(r.grade_label)
        rows.append({
            'subject': subject_names.get(r.subject_id, r.subject_id),
            'total_score': r.total_score,
            'grade_label': r.grade_label,
            'remark': r.remark,
            'is_pass': r.is_pass,
            'grade_point': gp,
            'class_position': r.class_position,
        })
        if r.total_score is not None:
            total_sum += float(r.total_score)
        if r.is_pass:
            passed += 1

    n = len(rows)
    summary = {
        'subjects_count': n,
        'average': round(total_sum / n, 2) if n else None,
        'passed': passed,
    }

    comments = ReportComment.query.filter_by(
        school_id=school_id, student_id=student_id, term_id=term_id).first()

    attendance = _attendance_counts(school_id, student_id, term, comments)

    return {
        'school': school, 'student': student, 'klass': klass, 'term': term,
        'academic_year': academic_year, 'settings': settings,
        'rows': rows, 'summary': summary, 'comments': comments,
        'attendance': attendance, 'published': any_published,
    }


def _grade_point_map(school_id):
    """grade_label -> grade_point from the default scheme's bands."""
    scheme = GradingScheme.query.filter_by(
        school_id=school_id, is_default=True).first()
    if scheme is None:
        return {}
    bands = GradeBoundary.query.filter_by(
        school_id=school_id, grading_scheme_id=scheme.id).all()
    return {b.grade_label: b.grade_point for b in bands}


def _attendance_counts(school_id, student_id, term, comments):
    """
    Attendance for the report. Prefer explicit numbers on report_comments if
    set; otherwise derive present/total from attendance_records within the
    term's date range (when the term has dates).
    """
    if comments and comments.attendance_total is not None:
        present = comments.attendance_present or 0
        total = comments.attendance_total
        return {'present': present, 'total': total,
                'absent': max(total - present, 0),
                'late': None, 'excused': None}

    rows_q = AttendanceRecord.query.filter_by(
        school_id=school_id, student_id=student_id)
    if term.start_date and term.end_date:
        rows_q = rows_q.filter(AttendanceRecord.date >= term.start_date,
                               AttendanceRecord.date <= term.end_date)
    counts = {'present': 0, 'absent': 0, 'late': 0, 'excused': 0}
    total = 0
    for r in rows_q.all():
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
        total += 1
    counts['total'] = total
    return counts


# ---------------------------------------------------------------------------
# Report comments (write side) — used by /teacher/comments
# ---------------------------------------------------------------------------
def save_comment(school_id, student_id, term_id, *, teacher_comment=None,
                 head_comment=None):
    student = Student.query.filter_by(school_id=school_id, id=student_id).first()
    if student is None:
        raise ReportError('Student not found.')
    if Term.query.filter_by(school_id=school_id, id=term_id).first() is None:
        raise ReportError('Term not found.')
    rc = ReportComment.query.filter_by(
        school_id=school_id, student_id=student_id, term_id=term_id).first()
    if rc is None:
        rc = ReportComment(school_id=school_id, student_id=student_id,
                           term_id=term_id)
        db.session.add(rc)
    if teacher_comment is not None:
        rc.teacher_comment = teacher_comment.strip() or None
    if head_comment is not None:
        rc.head_comment = head_comment.strip() or None
    db.session.flush()
    return rc
