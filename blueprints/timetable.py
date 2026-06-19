"""
Timetabling: admin period setup + per-class grid editor (school_admin), and a
read-only 'my timetable' for teachers. Tenant-scoped.
"""
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
)
from flask_login import login_required, current_user

from extensions import db
from auth.security import require_role
from services.tenant import tenant_query
from services.audit import log_action
from services import timetable as tt
from services.timetable import TimetableError, DAYS
from models.config_tables import Class, Subject
from models.operational import User
from models.enums import UserRole

timetable_bp = Blueprint('timetable', __name__, url_prefix='/timetable')


@timetable_bp.before_request
@login_required
@require_role('school_admin', 'teacher')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


def _weekdays():
    return list(enumerate(DAYS[:5]))   # Mon–Fri


# ---------------------------------------------------------------------------
# Periods (school_admin)
# ---------------------------------------------------------------------------
@timetable_bp.route('/periods', methods=['GET', 'POST'])
@require_role('school_admin')
def periods():
    if request.method == 'POST':
        try:
            tt.create_period(_sid(), name=request.form.get('name'),
                             sequence=_int(request.form.get('sequence')) or 0,
                             start_time=_time(request.form.get('start_time')),
                             end_time=_time(request.form.get('end_time')))
            log_action('create', 'period')
            db.session.commit()
            flash('Period added.', 'success')
        except TimetableError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('timetable.periods'))
    return render_template('timetable/periods.html', periods=tt.periods(_sid()))


@timetable_bp.route('/periods/<int:period_id>/delete', methods=['POST'])
@require_role('school_admin')
def delete_period(period_id):
    try:
        tt.delete_period(_sid(), period_id)
        log_action('delete', 'period', period_id)
        db.session.commit()
        flash('Period removed.', 'info')
    except TimetableError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('timetable.periods'))


# ---------------------------------------------------------------------------
# Class timetable editor (school_admin)
# ---------------------------------------------------------------------------
@timetable_bp.route('/', methods=['GET'])
@require_role('school_admin')
def index():
    classes = tenant_query(Class).order_by(Class.name).all()
    class_id = _int(request.args.get('class_id'))
    ps = tt.periods(_sid())
    grid = klass = subjects = teachers = None
    if class_id is not None:
        klass = Class.query.filter_by(school_id=_sid(), id=class_id).first()
        if klass is None:
            abort(404)
        grid = tt.class_grid(_sid(), class_id)
        subjects = tenant_query(Subject).order_by(Subject.name).all()
        teachers = (tenant_query(User).filter(User.role == UserRole.teacher)
                    .order_by(User.name).all())
    return render_template('timetable/index.html', classes=classes,
                           selected_class_id=class_id, klass=klass,
                           periods=ps, days=_weekdays(), grid=grid,
                           subjects=subjects, teachers=teachers)


@timetable_bp.route('/set', methods=['POST'])
@require_role('school_admin')
def set_slot():
    class_id = _int(request.form.get('class_id'))
    day = _int(request.form.get('day_of_week'))
    period_id = _int(request.form.get('period_id'))
    subject_id = _int(request.form.get('subject_id'))
    teacher_id = _int(request.form.get('teacher_user_id'))
    try:
        if subject_id is None:
            tt.clear_slot(_sid(), class_id, day, period_id)
            flash('Slot cleared.', 'info')
        else:
            tt.set_slot(_sid(), class_id, day, period_id, subject_id, teacher_id)
            flash('Timetable updated.', 'success')
        log_action('set_timetable_slot', 'class', class_id,
                   meta={'day': day, 'period_id': period_id})
        db.session.commit()
    except TimetableError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('timetable.index', class_id=class_id))


# ---------------------------------------------------------------------------
# My timetable (teacher)
# ---------------------------------------------------------------------------
@timetable_bp.route('/mine')
def mine():
    grid = tt.teacher_grid(_sid(), current_user.id)
    classes = {c.id: c.name for c in tenant_query(Class).all()}
    subjects = {s.id: s.name for s in tenant_query(Subject).all()}
    return render_template('timetable/mine.html', grid=grid,
                           periods=tt.periods(_sid()), days=_weekdays(),
                           classes=classes, subjects=subjects)


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _time(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%H:%M').time()
    except ValueError:
        return None
