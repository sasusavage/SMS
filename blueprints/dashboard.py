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
    # Super admins belong in /platform, not the tenant dashboard.
    if is_platform_user():
        from flask import redirect, url_for
        return redirect(url_for('platform.index'))
    role = getattr(current_user, 'role', None)
    role = role.value if hasattr(role, 'value') else role
    return render_template('dashboard/index.html', role=role)
