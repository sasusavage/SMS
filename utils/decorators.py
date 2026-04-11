from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user, login_required


def get_user_home():
    """Get the home URL for the current user based on their role."""
    from models import UserRole
    if current_user.role == UserRole.PARENT:
        return url_for('parent.dashboard')
    if current_user.role == UserRole.SUPER_ADMIN:
        return url_for('saas_admin.dashboard')
    return url_for('dashboard.index')


def school_context_required(f):
    """Block Super Admin from school-scoped routes — they have no school context."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import UserRole
        if current_user.is_authenticated and current_user.role == UserRole.SUPER_ADMIN:
            flash('Super Admin has no school context. Use the SaaS Control Panel.', 'warning')
            return redirect(url_for('saas_admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def module_required(feature_name):
    """Decorator to ensure a multi-tenant module is active for the school."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            from models import ModuleConfig
            config = ModuleConfig.query.filter_by(school_id=current_user.school_id).first()
            is_enabled = getattr(config, f"is_{feature_name}_enabled", False) if config else False

            if not is_enabled:
                flash(f"The {feature_name.replace('_', ' ').title()} module is locked. Upgrade to unlock!", "warning")
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(*roles):
    """Decorator to require specific roles."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('Access denied. Insufficient permissions.', 'error')
                return redirect(get_user_home())
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Require school admin role (HEADTEACHER or ADMIN). Super Admin is blocked — no school context."""
    from models import UserRole
    @wraps(f)
    @login_required
    @school_context_required
    def decorated_function(*args, **kwargs):
        allowed = [UserRole.HEADTEACHER, UserRole.ADMIN]
        if current_user.role not in allowed:
            flash('Admin access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def headteacher_required(f):
    """Require HEADTEACHER role. Super Admin is blocked — no school context."""
    from models import UserRole
    @wraps(f)
    @login_required
    @school_context_required
    def decorated_function(*args, **kwargs):
        if current_user.role != UserRole.HEADTEACHER:
            flash('Headteacher access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    """Require teacher or school admin role. Super Admin is blocked — no school context."""
    from models import UserRole
    @wraps(f)
    @login_required
    @school_context_required
    def decorated_function(*args, **kwargs):
        allowed = [UserRole.HEADTEACHER, UserRole.ADMIN, UserRole.TEACHER]
        if current_user.role not in allowed:
            flash('Teacher access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def accounts_required(f):
    """Require accounts officer or school admin role. Super Admin is blocked — no school context."""
    from models import UserRole
    @wraps(f)
    @login_required
    @school_context_required
    def decorated_function(*args, **kwargs):
        allowed = [UserRole.HEADTEACHER, UserRole.ADMIN, UserRole.ACCOUNTS_OFFICER]
        if current_user.role not in allowed:
            flash('Accounts access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def parent_required(f):
    """Require PARENT role."""
    from models import UserRole
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != UserRole.PARENT:
            flash('Parent access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    """Require any staff role (not parent). Super Admin is blocked — no school context."""
    from models import UserRole
    @wraps(f)
    @login_required
    @school_context_required
    def decorated_function(*args, **kwargs):
        if current_user.role == UserRole.PARENT:
            flash('Staff access required.', 'error')
            return redirect(url_for('parent.dashboard'))
        return f(*args, **kwargs)
    return decorated_function