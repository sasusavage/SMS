"""
Auth blueprint: login (school slug + email + password), logout, password reset.

Login resolves the tenant from the submitted *school slug*, then matches the
user within that school. Super admins log in via the same form with no school
slug (or a reserved sentinel) and are routed to the platform area.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g,
)
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models.platform import School, PlatformUser
from models.operational import User
from models.enums import SchoolStatus
from auth.security import (
    verify_password, PlatformIdentity, is_platform_user,
)
from services.audit import log_action

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        school_slug = (request.form.get('school_slug') or '').strip().lower()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        # Platform super admin: no school slug provided.
        if not school_slug:
            pu = PlatformUser.query.filter(
                db.func.lower(PlatformUser.email) == email
            ).first()
            if pu and pu.is_active and verify_password(pu.password_hash, password):
                login_user(PlatformIdentity(pu))
                log_action('login', entity='platform_user', entity_id=pu.id,
                           user_id=pu.id, commit=True)
                return redirect(url_for('platform.index'))
            flash('Invalid credentials.', 'danger')
            return render_template('auth/login.html'), 401

        # In-school user: resolve tenant from slug, then match user in school.
        school = School.query.filter(
            db.func.lower(School.slug) == school_slug
        ).first()
        if school:
            user = User.query.filter(
                User.school_id == school.id,
                db.func.lower(User.email) == email,
            ).first()
            if user and user.is_active and verify_password(user.password_hash, password):
                # Suspended tenants are locked out entirely.
                if school.status == SchoolStatus.suspended:
                    flash('This school is suspended. Please contact your '
                          'administrator.', 'danger')
                    return render_template('auth/login.html'), 403
                login_user(user)
                log_action('login', entity='user', entity_id=user.id,
                           school_id=school.id, user_id=user.id, commit=True)
                return redirect(url_for('dashboard.index'))

        # Same generic message whether school, user, or password was wrong —
        # don't leak which schools exist.
        flash('Invalid school code, email, or password.', 'danger')
        return render_template('auth/login.html'), 401

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    if is_platform_user():
        log_action('logout', entity='platform_user', entity_id=current_user.id,
                   user_id=current_user.id, commit=True)
    else:
        log_action('logout', entity='user', entity_id=current_user.id,
                   commit=True)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/password-reset', methods=['GET', 'POST'])
def password_reset():
    """
    Placeholder for Phase 1. Email delivery is out of scope (no SMS/email in
    Phase 1), so this just acknowledges the request without revealing whether
    the account exists. Full token flow lands when notifications arrive.
    """
    if request.method == 'POST':
        flash('If that account exists, a reset link will be sent by your '
              'administrator.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/password_reset.html')
