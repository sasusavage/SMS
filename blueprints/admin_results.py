"""
/admin/results — compute, review warnings, publish/unpublish per class+term
(Step 5). school_admin only, tenant-scoped.

Compute and publish logic lives in services/results_engine.py; routes handle
HTTP, flash ResultsError.message, and audit. Publishing is what makes results
visible to students/parents (Step 7 portals).
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
    session,
)
from flask_login import login_required, current_user

from extensions import db
from auth.security import require_role
from services.audit import log_action
from services.tenant import tenant_query
from services import results_engine
from services.results_engine import ResultsError
from models.config_tables import Class, Term, Subject
from models.operational import TermResult, Student

results_bp = Blueprint('admin_results', __name__, url_prefix='/admin/results')


@results_bp.before_request
@login_required
@require_role('school_admin')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


def _selection():
    class_id = _int(request.values.get('class_id'))
    term_id = _int(request.values.get('term_id'))
    return class_id, term_id


@results_bp.route('/', methods=['GET'])
def index():
    sid = _sid()
    classes = tenant_query(Class).order_by(Class.name).all()
    terms = tenant_query(Term).order_by(Term.sequence).all()
    class_id, term_id = _selection()

    rows = []
    published_count = 0
    warnings = session.pop('results_warnings', None)
    klass = subject_names = None
    if class_id is not None and term_id is not None:
        klass = Class.query.filter_by(school_id=sid, id=class_id).first()
        if klass is None:
            abort(404)
        rows = results_engine.results_overview(sid, class_id, term_id)
        published_count = sum(1 for r in rows if r.is_published)
        # Friendly lookups for the table.
        subject_names = {s.id: s.name for s in tenant_query(Subject).all()}
        student_names = {
            s.id: f'{s.last_name}, {s.first_name}'
            for s in Student.query.filter_by(school_id=sid).all()}
    else:
        subject_names, student_names = {}, {}

    return render_template('admin/results/index.html', classes=classes,
                           terms=terms, selected_class_id=class_id,
                           selected_term_id=term_id, rows=rows,
                           subject_names=subject_names,
                           student_names=student_names, klass=klass,
                           published_count=published_count, warnings=warnings)


@results_bp.route('/compute', methods=['POST'])
def compute():
    sid = _sid()
    class_id, term_id = _selection()
    if class_id is None or term_id is None:
        flash('Pick a class and term first.', 'warning')
        return redirect(url_for('admin_results.index'))
    try:
        out = results_engine.compute_term_results(sid, class_id, term_id)
        log_action('compute_results', entity='class', entity_id=class_id,
                   meta={'term_id': term_id, 'computed': out['computed']})
        db.session.commit()
        if out['errors']:
            for e in out['errors']:
                flash(e, 'danger')
        else:
            flash(f'Computed {out["computed"]} result(s).'
                  + (f' {len(out["warnings"])} warning(s).'
                     if out['warnings'] else ''), 'success')
        # Stash warnings to show on the review page.
        session['results_warnings'] = out['warnings']
    except ResultsError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_results.index', class_id=class_id,
                            term_id=term_id))


@results_bp.route('/publish', methods=['POST'])
def publish():
    sid = _sid()
    class_id, term_id = _selection()
    try:
        n = results_engine.publish_results(sid, class_id, term_id)
        log_action('publish_results', entity='class', entity_id=class_id,
                   meta={'term_id': term_id, 'published': n})
        db.session.commit()
        flash(f'Published {n} result(s). Students and parents can now see them.',
              'success')
    except ResultsError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_results.index', class_id=class_id,
                            term_id=term_id))


@results_bp.route('/unpublish', methods=['POST'])
def unpublish():
    sid = _sid()
    class_id, term_id = _selection()
    try:
        n = results_engine.unpublish_results(sid, class_id, term_id)
        log_action('unpublish_results', entity='class', entity_id=class_id,
                   meta={'term_id': term_id, 'unpublished': n})
        db.session.commit()
        flash(f'Unpublished {n} result(s).', 'info')
    except ResultsError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_results.index', class_id=class_id,
                            term_id=term_id))


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None
