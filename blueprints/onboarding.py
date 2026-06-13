"""
/onboarding — tenant signup + setup wizard (Step 2, spec §5).

Flow:
  GET  /signup           -> school profile + first admin + template pick form
  POST /signup           -> create School + school_admin User + apply template,
                            log the admin in, redirect to the wizard checklist
  GET  /onboarding       -> checklist showing what the template seeded and
                            linking to the /admin/config editors to customise

The wizard intentionally reuses apply_template() (template = data) and the
/admin/config pages (per-area editors), rather than duplicating CRUD here.
"""
import re

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g,
)
from flask_login import login_user, login_required, current_user

from extensions import db
from auth.security import hash_password, is_platform_user
from auth.security import require_role
from services.template_loader import apply_template, VALID_TEMPLATES
from services.audit import log_action
from models.platform import School
from models.enums import SchoolStatus, UserRole
from models.operational import User
from models.config_tables import (
    LevelGroup, Level, Subject, GradingScheme, AssessmentComponent, Term,
)

onboarding_bp = Blueprint('onboarding', __name__)

_SLUG_RE = re.compile(r'[^a-z0-9]+')


def _slugify(value):
    s = _SLUG_RE.sub('-', (value or '').strip().lower()).strip('-')
    return s or 'school'


@onboarding_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated and not is_platform_user():
        return redirect(url_for('onboarding.wizard'))

    if request.method == 'POST':
        name = (request.form.get('school_name') or '').strip()
        country = (request.form.get('country') or '').strip() or None
        admin_name = (request.form.get('admin_name') or '').strip()
        admin_email = (request.form.get('admin_email') or '').strip().lower()
        password = request.form.get('password') or ''
        template = (request.form.get('template') or 'blank').strip()

        errors = []
        if not name:
            errors.append('School name is required.')
        if not admin_email:
            errors.append('Admin email is required.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if template not in VALID_TEMPLATES:
            errors.append('Pick a valid template.')

        # Unique slug per platform
        slug = _slugify(request.form.get('slug') or name)
        if School.query.filter_by(slug=slug).first():
            errors.append(f'School code "{slug}" is taken — choose another.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('onboarding/signup.html',
                                   templates=sorted(VALID_TEMPLATES),
                                   form=request.form), 400

        # Create school + first admin + apply template in one transaction.
        school = School(name=name, slug=slug, country=country,
                        curriculum_template_used=template,
                        status=SchoolStatus.trial)
        db.session.add(school)
        db.session.flush()

        admin = User(school_id=school.id, email=admin_email, name=admin_name,
                     role=UserRole.school_admin,
                     password_hash=hash_password(password), is_active=True)
        db.session.add(admin)
        db.session.flush()

        apply_template(school.id, template)
        log_action('signup', entity='school', entity_id=school.id,
                   school_id=school.id, user_id=admin.id)
        db.session.commit()

        login_user(admin)
        flash('School created! Review your setup below.', 'info')
        return redirect(url_for('onboarding.wizard'))

    return render_template('onboarding/signup.html',
                           templates=sorted(VALID_TEMPLATES), form={})


@onboarding_bp.route('/onboarding')
@login_required
@require_role('school_admin')
def wizard():
    """Checklist of what's configured, linking to the editors."""
    sid = g.current_school_id
    summary = {
        'level_groups': LevelGroup.query.filter_by(school_id=sid).count(),
        'levels': Level.query.filter_by(school_id=sid).count(),
        'subjects': Subject.query.filter_by(school_id=sid).count(),
        'grading_schemes': GradingScheme.query.filter_by(school_id=sid).count(),
        'components': AssessmentComponent.query.filter_by(school_id=sid).count(),
        'terms': Term.query.filter_by(school_id=sid).count(),
    }
    school = School.query.get(sid)
    return render_template('onboarding/wizard.html', summary=summary,
                           school=school)
