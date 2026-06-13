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
    from flask import redirect, url_for
    # Super admins belong in /platform, not the tenant dashboard.
    if is_platform_user():
        return redirect(url_for('platform.index'))
    role = getattr(current_user, 'role', None)
    role = role.value if hasattr(role, 'value') else role
    # Students and parents land in their portal, not the admin dashboard.
    if role == 'student':
        return redirect(url_for('portal.student_home'))
    if role == 'parent':
        return redirect(url_for('portal.parent_home'))
    return render_template('dashboard/index.html', role=role)
