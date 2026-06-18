"""
/admin/config — school_admin curriculum configuration CRUD (Step 2).

Every handler is tenant-scoped: reads/writes go through tenant_query / explicit
school_id == g.current_school_id filters, and creates stamp the row with
g.current_school_id. Validation that the spec calls out (grade boundary
overlap, weights=100, term dates inside the academic year) is delegated to
services/config_validation.py — never inlined here.
"""
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
)
from flask_login import login_required

from extensions import db
from auth.security import require_role
from services.tenant import tenant_query, get_tenant_or_404
from services.audit import log_action
from services import config_validation as cv
from models.config_tables import (
    AcademicYear, Term, LevelGroup, Level, Class, Subject, LevelSubject,
    GradingScheme, GradeBoundary, AssessmentComponent, ReportSettings,
)

config_bp = Blueprint('admin_config', __name__, url_prefix='/admin/config')


@config_bp.before_request
@login_required
@require_role('school_admin')
def _guard():
    """All config routes require a logged-in school_admin with a tenant."""
    if g.get('current_school_id') is None:
        abort(403)


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------
@config_bp.route('/')
def index():
    counts = {
        'academic_years': tenant_query(AcademicYear).count(),
        'terms': tenant_query(Term).count(),
        'level_groups': tenant_query(LevelGroup).count(),
        'levels': tenant_query(Level).count(),
        'classes': tenant_query(Class).count(),
        'subjects': tenant_query(Subject).count(),
        'grading_schemes': tenant_query(GradingScheme).count(),
        'components': tenant_query(AssessmentComponent).count(),
    }
    return render_template('admin/config/index.html', counts=counts)


# ---------------------------------------------------------------------------
# School profile (name, contact, logo)
# ---------------------------------------------------------------------------
@config_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    from models.platform import School
    from services import uploads
    from services.uploads import UploadError
    school = db.session.get(School, g.current_school_id)
    if request.method == 'POST':
        school.name = (request.form.get('name') or school.name).strip()
        school.address = (request.form.get('address') or '').strip() or None
        school.phone = (request.form.get('phone') or '').strip() or None
        school.email = (request.form.get('email') or '').strip() or None
        # Optional logo upload.
        logo = request.files.get('logo')
        try:
            if logo and logo.filename:
                old = school.logo_path
                school.logo_path = uploads.save_upload(
                    logo, g.current_school_id, 'logo', images_only=True)
                if old:
                    uploads.delete_upload(old)
            log_action('update', entity='school_profile',
                       entity_id=school.id)
            db.session.commit()
            flash('School profile saved.', 'success')
        except UploadError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_config.profile'))
    return render_template('admin/config/profile.html', school=school)


# ---------------------------------------------------------------------------
# Notification settings (per-school SMTP + SMS)
# ---------------------------------------------------------------------------
@config_bp.route('/notifications', methods=['GET', 'POST'])
def notifications():
    from services import school_settings
    s = school_settings.get_or_create(g.current_school_id)
    if request.method == 'POST':
        section = request.form.get('section')
        if section == 'smtp':
            school_settings.update_smtp(
                g.current_school_id,
                enabled=request.form.get('smtp_enabled'),
                host=request.form.get('smtp_host'),
                port=request.form.get('smtp_port'),
                use_tls=request.form.get('smtp_use_tls'),
                username=request.form.get('smtp_username'),
                password=request.form.get('smtp_password'),
                from_email=request.form.get('smtp_from_email'),
                from_name=request.form.get('smtp_from_name'))
            log_action('update', entity='school_smtp', entity_id=g.current_school_id)
            db.session.commit()
            flash('Email (SMTP) settings saved.', 'success')
        elif section == 'sms':
            school_settings.update_sms(
                g.current_school_id,
                enabled=request.form.get('sms_enabled'),
                sender_id=request.form.get('sms_sender_id'))
            log_action('update', entity='school_sms', entity_id=g.current_school_id)
            db.session.commit()
            flash('SMS settings saved.', 'success')
        return redirect(url_for('admin_config.notifications'))
    return render_template('admin/config/notifications.html', s=s)


@config_bp.route('/notifications/test-email', methods=['POST'])
def test_email():
    from services import notify
    to = (request.form.get('to') or '').strip()
    if not to:
        flash('Enter a recipient email to test.', 'warning')
    else:
        entry = notify.test_email(g.current_school_id, to)
        if entry.status == 'sent':
            flash(f'Test email sent to {to}.', 'success')
        elif entry.status == 'logged':
            flash('No email provider configured — the message was logged only.',
                  'warning')
        else:
            flash(f'Test email failed: {entry.error}', 'danger')
    return redirect(url_for('admin_config.notifications'))


@config_bp.route('/notifications/test-sms', methods=['POST'])
def test_sms():
    from services import notify
    to = (request.form.get('to') or '').strip()
    if not to:
        flash('Enter a phone number to test.', 'warning')
    else:
        entry = notify.test_sms(g.current_school_id, to)
        if entry.status == 'sent':
            flash(f'Test SMS sent to {to}.', 'success')
        elif entry.status == 'logged':
            flash('No SMS provider configured — the message was logged only.',
                  'warning')
        else:
            flash(f'Test SMS failed: {entry.error}', 'danger')
    return redirect(url_for('admin_config.notifications'))


# ---------------------------------------------------------------------------
# Academic years
# ---------------------------------------------------------------------------
@config_bp.route('/academic-years', methods=['GET', 'POST'])
def academic_years():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Name is required.', 'danger')
        else:
            ay = AcademicYear(
                school_id=g.current_school_id, name=name,
                start_date=_date(request.form.get('start_date')),
                end_date=_date(request.form.get('end_date')),
                is_current=False,
            )
            db.session.add(ay)
            _commit_with_audit('create', 'academic_year', ay)
            flash('Academic year added.', 'info')
        return redirect(url_for('admin_config.academic_years'))

    years = tenant_query(AcademicYear).order_by(AcademicYear.name).all()
    return render_template('admin/config/academic_years.html', years=years)


@config_bp.route('/academic-years/<int:year_id>/set-current', methods=['POST'])
def set_current_year(year_id):
    get_tenant_or_404(AcademicYear, year_id)  # tenant check
    try:
        cv.set_current_academic_year(g.current_school_id, year_id)
        _commit_with_audit('set_current', 'academic_year', _ref(year_id))
        flash('Current academic year updated.', 'info')
    except cv.ValidationError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_config.academic_years'))


@config_bp.route('/academic-years/<int:year_id>/delete', methods=['POST'])
def delete_year(year_id):
    ay = get_tenant_or_404(AcademicYear, year_id)
    db.session.delete(ay)
    _commit_with_audit('delete', 'academic_year', _ref(year_id))
    flash('Academic year deleted.', 'info')
    return redirect(url_for('admin_config.academic_years'))


# ---------------------------------------------------------------------------
# Terms (validated against their academic year)
# ---------------------------------------------------------------------------
@config_bp.route('/terms', methods=['GET', 'POST'])
def terms():
    years = tenant_query(AcademicYear).order_by(AcademicYear.name).all()
    if request.method == 'POST':
        ay = get_tenant_or_404(AcademicYear,
                               _int(request.form.get('academic_year_id')))
        start = _date(request.form.get('start_date'))
        end = _date(request.form.get('end_date'))
        name = (request.form.get('name') or '').strip()
        seq = _int(request.form.get('sequence')) or 1
        if not name:
            flash('Term name is required.', 'danger')
        else:
            try:
                cv.validate_term_dates(ay, start, end)
                term = Term(school_id=g.current_school_id,
                            academic_year_id=ay.id, name=name, sequence=seq,
                            start_date=start, end_date=end, is_current=False)
                db.session.add(term)
                _commit_with_audit('create', 'term', term)
                flash('Term added.', 'info')
            except cv.ValidationError as e:
                db.session.rollback()
                flash(e.message, 'danger')
        return redirect(url_for('admin_config.terms'))

    all_terms = (tenant_query(Term)
                 .order_by(Term.academic_year_id, Term.sequence).all())
    return render_template('admin/config/terms.html', terms=all_terms,
                           years=years)


@config_bp.route('/terms/<int:term_id>/set-current', methods=['POST'])
def set_current_term_route(term_id):
    term = get_tenant_or_404(Term, term_id)
    try:
        cv.set_current_term(g.current_school_id, term.academic_year_id, term_id)
        _commit_with_audit('set_current', 'term', _ref(term_id))
        flash('Current term updated.', 'info')
    except cv.ValidationError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_config.terms'))


@config_bp.route('/terms/<int:term_id>/delete', methods=['POST'])
def delete_term(term_id):
    term = get_tenant_or_404(Term, term_id)
    db.session.delete(term)
    _commit_with_audit('delete', 'term', _ref(term_id))
    flash('Term deleted.', 'info')
    return redirect(url_for('admin_config.terms'))


# ---------------------------------------------------------------------------
# Level groups & levels
# ---------------------------------------------------------------------------
@config_bp.route('/level-groups', methods=['GET', 'POST'])
def level_groups():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Name is required.', 'danger')
        else:
            lg = LevelGroup(school_id=g.current_school_id, name=name,
                            sequence=_int(request.form.get('sequence')) or 0)
            db.session.add(lg)
            _commit_with_audit('create', 'level_group', lg)
            flash('Level group added.', 'info')
        return redirect(url_for('admin_config.level_groups'))
    groups = tenant_query(LevelGroup).order_by(LevelGroup.sequence).all()
    return render_template('admin/config/level_groups.html', groups=groups)


@config_bp.route('/level-groups/<int:group_id>/delete', methods=['POST'])
def delete_level_group(group_id):
    lg = get_tenant_or_404(LevelGroup, group_id)
    db.session.delete(lg)
    _commit_with_audit('delete', 'level_group', _ref(group_id))
    flash('Level group deleted.', 'info')
    return redirect(url_for('admin_config.level_groups'))


@config_bp.route('/levels', methods=['GET', 'POST'])
def levels():
    groups = tenant_query(LevelGroup).order_by(LevelGroup.sequence).all()
    if request.method == 'POST':
        lg = get_tenant_or_404(LevelGroup,
                               _int(request.form.get('level_group_id')))
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Name is required.', 'danger')
        else:
            lvl = Level(school_id=g.current_school_id, level_group_id=lg.id,
                        name=name, sequence=_int(request.form.get('sequence')) or 0)
            db.session.add(lvl)
            _commit_with_audit('create', 'level', lvl)
            flash('Level added.', 'info')
        return redirect(url_for('admin_config.levels'))
    all_levels = (tenant_query(Level)
                  .order_by(Level.level_group_id, Level.sequence).all())
    return render_template('admin/config/levels.html', levels=all_levels,
                           groups=groups)


@config_bp.route('/levels/<int:level_id>/delete', methods=['POST'])
def delete_level(level_id):
    lvl = get_tenant_or_404(Level, level_id)
    db.session.delete(lvl)
    _commit_with_audit('delete', 'level', _ref(level_id))
    flash('Level deleted.', 'info')
    return redirect(url_for('admin_config.levels'))


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------
@config_bp.route('/classes', methods=['GET', 'POST'])
def classes():
    levels_list = tenant_query(Level).order_by(Level.sequence).all()
    years = tenant_query(AcademicYear).order_by(AcademicYear.name).all()
    if request.method == 'POST':
        lvl = get_tenant_or_404(Level, _int(request.form.get('level_id')))
        ay = get_tenant_or_404(AcademicYear,
                               _int(request.form.get('academic_year_id')))
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Class name is required.', 'danger')
        else:
            cls = Class(school_id=g.current_school_id, level_id=lvl.id,
                        academic_year_id=ay.id, name=name)
            db.session.add(cls)
            _commit_with_audit('create', 'class', cls)
            flash('Class added.', 'info')
        return redirect(url_for('admin_config.classes'))
    all_classes = tenant_query(Class).order_by(Class.name).all()
    return render_template('admin/config/classes.html', classes=all_classes,
                           levels=levels_list, years=years)


@config_bp.route('/classes/<int:class_id>/delete', methods=['POST'])
def delete_class(class_id):
    cls = get_tenant_or_404(Class, class_id)
    db.session.delete(cls)
    _commit_with_audit('delete', 'class', _ref(class_id))
    flash('Class deleted.', 'info')
    return redirect(url_for('admin_config.classes'))


# ---------------------------------------------------------------------------
# Subjects & level-subjects
# ---------------------------------------------------------------------------
@config_bp.route('/subjects', methods=['GET', 'POST'])
def subjects():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Subject name is required.', 'danger')
        else:
            subj = Subject(school_id=g.current_school_id, name=name,
                           code=(request.form.get('code') or '').strip() or None,
                           is_core=bool(request.form.get('is_core')))
            db.session.add(subj)
            _commit_with_audit('create', 'subject', subj)
            flash('Subject added.', 'info')
        return redirect(url_for('admin_config.subjects'))
    all_subjects = tenant_query(Subject).order_by(Subject.name).all()
    return render_template('admin/config/subjects.html', subjects=all_subjects)


@config_bp.route('/subjects/<int:subject_id>/edit', methods=['POST'])
def edit_subject(subject_id):
    subj = get_tenant_or_404(Subject, subject_id)
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Subject name is required.', 'danger')
    else:
        subj.name = name
        subj.code = (request.form.get('code') or '').strip() or None
        subj.is_core = bool(request.form.get('is_core'))
        _commit_with_audit('edit', 'subject', subj)
        flash('Subject updated.', 'success')
    return redirect(url_for('admin_config.subjects'))


@config_bp.route('/subjects/<int:subject_id>/delete', methods=['POST'])
def delete_subject(subject_id):
    subj = get_tenant_or_404(Subject, subject_id)
    db.session.delete(subj)
    _commit_with_audit('delete', 'subject', _ref(subject_id))
    flash('Subject deleted.', 'info')
    return redirect(url_for('admin_config.subjects'))


@config_bp.route('/level-subjects', methods=['GET', 'POST'])
def level_subjects():
    levels_list = tenant_query(Level).order_by(Level.sequence).all()
    subjects_list = tenant_query(Subject).order_by(Subject.name).all()
    if request.method == 'POST':
        lvl = get_tenant_or_404(Level, _int(request.form.get('level_id')))
        subj = get_tenant_or_404(Subject, _int(request.form.get('subject_id')))
        exists = (tenant_query(LevelSubject)
                  .filter_by(level_id=lvl.id, subject_id=subj.id).first())
        if exists:
            flash('That subject is already offered at that level.', 'warning')
        else:
            ls = LevelSubject(school_id=g.current_school_id, level_id=lvl.id,
                              subject_id=subj.id)
            db.session.add(ls)
            _commit_with_audit('create', 'level_subject', ls)
            flash('Subject mapped to level.', 'info')
        return redirect(url_for('admin_config.level_subjects'))
    mappings = tenant_query(LevelSubject).all()
    return render_template('admin/config/level_subjects.html',
                           mappings=mappings, levels=levels_list,
                           subjects=subjects_list)


@config_bp.route('/level-subjects/<int:ls_id>/delete', methods=['POST'])
def delete_level_subject(ls_id):
    ls = get_tenant_or_404(LevelSubject, ls_id)
    db.session.delete(ls)
    _commit_with_audit('delete', 'level_subject', _ref(ls_id))
    flash('Mapping removed.', 'info')
    return redirect(url_for('admin_config.level_subjects'))


# ---------------------------------------------------------------------------
# Grading schemes + boundaries
# ---------------------------------------------------------------------------
@config_bp.route('/grading-schemes', methods=['GET', 'POST'])
def grading_schemes():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Scheme name is required.', 'danger')
        else:
            scheme = GradingScheme(school_id=g.current_school_id, name=name,
                                   is_default=False)
            db.session.add(scheme)
            _commit_with_audit('create', 'grading_scheme', scheme)
            flash('Grading scheme added.', 'info')
        return redirect(url_for('admin_config.grading_schemes'))
    schemes = tenant_query(GradingScheme).order_by(GradingScheme.name).all()
    return render_template('admin/config/grading_schemes.html', schemes=schemes)


@config_bp.route('/grading-schemes/<int:scheme_id>/set-default', methods=['POST'])
def set_default_scheme(scheme_id):
    get_tenant_or_404(GradingScheme, scheme_id)
    try:
        cv.set_default_grading_scheme(g.current_school_id, scheme_id)
        _commit_with_audit('set_default', 'grading_scheme', _ref(scheme_id))
        flash('Default grading scheme updated.', 'info')
    except cv.ValidationError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_config.grading_schemes'))


@config_bp.route('/grading-schemes/<int:scheme_id>', methods=['GET', 'POST'])
def scheme_boundaries(scheme_id):
    scheme = get_tenant_or_404(GradingScheme, scheme_id)
    if request.method == 'POST':
        new_b = GradeBoundary(
            school_id=g.current_school_id, grading_scheme_id=scheme.id,
            min_score=_int(request.form.get('min_score')),
            max_score=_int(request.form.get('max_score')),
            grade_label=(request.form.get('grade_label') or '').strip(),
            remark=(request.form.get('remark') or '').strip() or None,
            grade_point=_dec(request.form.get('grade_point')),
            is_pass=bool(request.form.get('is_pass')),
        )
        # Validate the prospective full set BEFORE persisting.
        existing = (tenant_query(GradeBoundary)
                    .filter_by(grading_scheme_id=scheme.id).all())
        try:
            cv.validate_grade_boundaries(existing + [new_b])
            db.session.add(new_b)
            _commit_with_audit('create', 'grade_boundary', new_b)
            flash('Grade boundary added.', 'info')
        except cv.ValidationError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_config.scheme_boundaries',
                                scheme_id=scheme.id))
    boundaries = (tenant_query(GradeBoundary)
                  .filter_by(grading_scheme_id=scheme.id)
                  .order_by(GradeBoundary.min_score.desc()).all())
    return render_template('admin/config/scheme_boundaries.html',
                           scheme=scheme, boundaries=boundaries)


@config_bp.route('/grade-boundaries/<int:boundary_id>/delete', methods=['POST'])
def delete_boundary(boundary_id):
    b = get_tenant_or_404(GradeBoundary, boundary_id)
    scheme_id = b.grading_scheme_id
    db.session.delete(b)
    _commit_with_audit('delete', 'grade_boundary', _ref(boundary_id))
    flash('Grade boundary deleted.', 'info')
    return redirect(url_for('admin_config.scheme_boundaries', scheme_id=scheme_id))


# ---------------------------------------------------------------------------
# Assessment components (weights must sum to 100 per bucket)
# ---------------------------------------------------------------------------
@config_bp.route('/components', methods=['GET', 'POST'])
def components():
    groups = tenant_query(LevelGroup).order_by(LevelGroup.sequence).all()
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        lg_id = _int(request.form.get('applies_to_level_group_id'))  # None = all
        if lg_id is not None:
            get_tenant_or_404(LevelGroup, lg_id)
        if not name:
            flash('Component name is required.', 'danger')
        else:
            comp = AssessmentComponent(
                school_id=g.current_school_id, name=name,
                weight_percent=_dec(request.form.get('weight_percent')) or 0,
                applies_to_level_group_id=lg_id,
            )
            db.session.add(comp)
            db.session.flush()
            _commit_with_audit('create', 'assessment_component', comp)
            flash('Component added. Remember weights in each bucket must total '
                  '100 before computing results.', 'info')
        return redirect(url_for('admin_config.components'))

    comps = tenant_query(AssessmentComponent).all()
    # Show per-bucket weight totals so the admin can see whether each sums to 100.
    buckets = {}
    for c in comps:
        buckets.setdefault(c.applies_to_level_group_id, 0)
        buckets[c.applies_to_level_group_id] += float(c.weight_percent or 0)
    return render_template('admin/config/components.html', components=comps,
                           groups=groups, buckets=buckets)


@config_bp.route('/components/<int:component_id>/delete', methods=['POST'])
def delete_component(component_id):
    comp = get_tenant_or_404(AssessmentComponent, component_id)
    db.session.delete(comp)
    _commit_with_audit('delete', 'assessment_component', _ref(component_id))
    flash('Component deleted.', 'info')
    return redirect(url_for('admin_config.components'))


# ---------------------------------------------------------------------------
# Report settings (one row per school)
# ---------------------------------------------------------------------------
@config_bp.route('/report-settings', methods=['GET', 'POST'])
def report_settings():
    rs = tenant_query(ReportSettings).first()
    if rs is None:
        rs = ReportSettings(school_id=g.current_school_id)
        db.session.add(rs)
        db.session.flush()
    if request.method == 'POST':
        rs.show_class_position = bool(request.form.get('show_class_position'))
        rs.show_grade_point = bool(request.form.get('show_grade_point'))
        rs.show_skills_ratings = bool(request.form.get('show_skills_ratings'))
        rs.teacher_comment_required = bool(request.form.get('teacher_comment_required'))
        rs.head_comment_required = bool(request.form.get('head_comment_required'))
        rs.next_term_begins_label = (
            request.form.get('next_term_begins_label') or '').strip() or None
        _commit_with_audit('update', 'report_settings', rs)
        flash('Report settings saved.', 'info')
        return redirect(url_for('admin_config.report_settings'))
    return render_template('admin/config/report_settings.html', rs=rs)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _commit_with_audit(action, entity, obj):
    entity_id = getattr(obj, 'id', None)
    log_action(action, entity=entity, entity_id=entity_id)
    db.session.commit()


class _ref:
    """Lightweight stand-in carrying an id for audit logging after delete."""
    def __init__(self, _id):
        self.id = _id


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _dec(v):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(v)) if v not in (None, '') else None
    except (InvalidOperation, TypeError):
        return None


def _date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        return None
