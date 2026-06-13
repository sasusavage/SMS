"""
/teacher — attendance (Step 4).

Daily attendance grid (pick class + date -> mark each student) and a monthly
summary per class. Open to teachers and school_admins; a teacher only sees the
classes they teach (class teacher or assigned), enforced by the attendance
service's access checks. All access is tenant-scoped.
"""
from datetime import date, datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
)
from flask_login import login_required, current_user

from extensions import db
from auth.security import require_role
from services.audit import log_action
from services import attendance
from services.attendance import AttendanceError
from services import results_engine
from services.results_engine import ResultsError
from models.config_tables import Class, Subject, Term

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')


@teacher_bp.before_request
@login_required
@require_role('teacher', 'school_admin')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


@teacher_bp.route('/attendance', methods=['GET', 'POST'])
def attendance_grid():
    sid = _sid()
    classes = attendance.accessible_classes(sid, current_user)

    class_id = _int(request.values.get('class_id'))
    on_date = _date(request.values.get('date')) or date.today()

    # Verify the chosen class is one this user may access.
    if class_id is not None and not attendance.teacher_can_access_class(
            sid, current_user, class_id):
        abort(404)

    if request.method == 'POST':
        if class_id is None:
            flash('Pick a class first.', 'warning')
            return redirect(url_for('teacher.attendance_grid'))
        # Build marks dict from form fields named status_<student_id>.
        marks = {}
        for key, value in request.form.items():
            if key.startswith('status_') and value:
                marks[key[len('status_'):]] = value
        try:
            saved = attendance.save_day_attendance(
                sid, class_id, on_date, marks, marked_by=current_user.id)
            log_action('mark_attendance', entity='class', entity_id=class_id,
                       meta={'date': on_date.isoformat(), 'count': saved})
            db.session.commit()
            flash(f'Attendance saved for {saved} student(s).', 'success')
        except AttendanceError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('teacher.attendance_grid',
                                class_id=class_id, date=on_date.isoformat()))

    roster = []
    existing = {}
    if class_id is not None:
        roster = attendance.get_class_roster(sid, class_id)
        existing = attendance.get_day_attendance(sid, class_id, on_date)

    return render_template('teacher/attendance.html', classes=classes,
                           selected_class_id=class_id, on_date=on_date,
                           today=date.today(), roster=roster, existing=existing,
                           statuses=['present', 'absent', 'late', 'excused'])


@teacher_bp.route('/attendance/summary')
def attendance_summary():
    sid = _sid()
    classes = attendance.accessible_classes(sid, current_user)
    class_id = _int(request.args.get('class_id'))
    today = date.today()
    year = _int(request.args.get('year')) or today.year
    month = _int(request.args.get('month')) or today.month

    if class_id is not None and not attendance.teacher_can_access_class(
            sid, current_user, class_id):
        abort(404)

    summary = None
    if class_id is not None:
        try:
            summary = attendance.monthly_summary(sid, class_id, year, month)
        except AttendanceError as e:
            flash(e.message, 'danger')

    klass = None
    if class_id is not None:
        klass = Class.query.filter_by(school_id=sid, id=class_id).first()

    return render_template('teacher/attendance_summary.html', classes=classes,
                           selected_class_id=class_id, year=year, month=month,
                           summary=summary, klass=klass,
                           months=list(range(1, 13)))


# ---------------------------------------------------------------------------
# Score entry grid  (/teacher/scores)
# ---------------------------------------------------------------------------
@teacher_bp.route('/scores', methods=['GET', 'POST'])
def scores():
    sid = _sid()
    classes = attendance.accessible_classes(sid, current_user)

    class_id = _int(request.values.get('class_id'))
    subject_id = _int(request.values.get('subject_id'))
    term_id = _int(request.values.get('term_id'))

    if class_id is not None and not attendance.teacher_can_access_class(
            sid, current_user, class_id):
        abort(404)

    klass = (Class.query.filter_by(school_id=sid, id=class_id).first()
             if class_id else None)
    subjects = results_engine.subjects_for_class(sid, klass) if klass else []
    terms = Term.query.filter_by(school_id=sid).order_by(Term.sequence).all()
    components = []
    if klass:
        lg = results_engine._class_level_group_id(sid, klass)
        components = results_engine.components_for(sid, lg)

    ready = all(x is not None for x in (class_id, subject_id, term_id))

    if request.method == 'POST' and ready:
        roster = results_engine._roster(sid, class_id)
        entries = []
        for student in roster:
            for comp in components:
                field = f'score_{student.id}_{comp.id}'
                if field in request.form:
                    entries.append({'student_id': student.id,
                                    'component_id': comp.id,
                                    'score': request.form.get(field)})
        try:
            saved = results_engine.save_scores(
                sid, class_id, subject_id, term_id, entries,
                entered_by=current_user.id)
            log_action('save_scores', entity='class', entity_id=class_id,
                       meta={'subject_id': subject_id, 'term_id': term_id,
                             'count': saved})
            db.session.commit()
            flash(f'Saved {saved} score cell(s).', 'success')
        except ResultsError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('teacher.scores', class_id=class_id,
                                subject_id=subject_id, term_id=term_id))

    roster = results_engine._roster(sid, class_id) if ready else []
    grid = (results_engine.get_score_grid(sid, class_id, subject_id, term_id)
            if ready else {})
    return render_template('teacher/scores.html', classes=classes,
                           selected_class_id=class_id, subjects=subjects,
                           selected_subject_id=subject_id, terms=terms,
                           selected_term_id=term_id, components=components,
                           roster=roster, grid=grid, ready=ready)


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        return None
