"""
Role-aware landing. Step 1 ships a minimal placeholder; role-specific dashboards
are fleshed out in later steps.
"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from auth.security import is_platform_user

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/')
@login_required
def index():
    from flask import redirect, url_for, g
    # Super admins belong in /platform — UNLESS impersonating a school, in which
    # case they get that school's admin dashboard.
    if is_platform_user() and g.get('impersonating_school_id') is None:
        return redirect(url_for('platform.index'))
    role = getattr(current_user, 'role', None)
    role = role.value if hasattr(role, 'value') else role
    if g.get('impersonating_school_id') is not None:
        role = 'school_admin'
    # Students and parents land in their portal, not the admin dashboard.
    if role == 'student':
        return redirect(url_for('portal.student_home'))
    if role == 'parent':
        return redirect(url_for('portal.parent_home'))

    analytics_data = None
    if role == 'school_admin':
        from services import analytics
        if g.get('current_school_id'):
            analytics_data = analytics.school_dashboard(g.current_school_id)
    return render_template('dashboard/index.html', role=role,
                           analytics=analytics_data)
