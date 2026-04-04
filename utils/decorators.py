from functools import wraps
from flask import abort, redirect, url_for, flash, g
from flask_login import current_user

def module_required(feature_name):
    """Decorator to ensure a multi-tenant module is active for the school."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            from models import ModuleConfig
            config = ModuleConfig.query.filter_by(school_id=current_user.school_id).first()
            
            # 1. Check if module is enabled
            is_enabled = getattr(config, f"is_{feature_name}_enabled", False) if config else False
            
            if not is_enabled:
                flash(f"The {feature_name.replace('_', ' ').title()} module is locked. Upgrade to unlock!", "warning")
                return redirect(url_for('dashboard.index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
