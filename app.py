"""
NaCCA School Management System - Main Application
Flask Application Factory with RBAC
"""
import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, g
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from config import config
from models import db, User, UserRole, School, AcademicYear, Term

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_name='default'):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Context processors
    @app.context_processor
    def inject_globals():
        return dict(
            current_year=datetime.now().year,
            UserRole=UserRole
        )
    
    @app.before_request
    def before_request():
        if current_user.is_authenticated:
            # Load current academic year and term
            g.current_academic_year = AcademicYear.query.filter_by(
                school_id=current_user.school_id,
                is_current=True
            ).first()
            
            if g.current_academic_year:
                g.current_term = Term.query.filter_by(
                    academic_year_id=g.current_academic_year.id,
                    is_current=True
                ).first()
            else:
                g.current_term = None
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.students import students_bp
    from routes.staff import staff_bp
    from routes.classes import classes_bp
    from routes.assessments import assessments_bp
    from routes.fees import fees_bp
    from routes.reports import reports_bp
    from routes.parent_portal import parent_bp
    from routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(fees_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(api_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    return app


# =============================================================================
# RBAC DECORATORS
# =============================================================================
def get_user_home():
    """Get the home URL for the current user based on their role."""
    if current_user.role == UserRole.PARENT:
        return url_for('parent.dashboard')
    return url_for('dashboard.index')


def role_required(*roles):
    """Decorator to require specific roles."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(get_user_home())
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator to require admin roles."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Administrator access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    """Decorator to require teacher or higher roles."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        allowed = [UserRole.SUPER_ADMIN, UserRole.HEADTEACHER, UserRole.ADMIN, UserRole.TEACHER]
        if current_user.role not in allowed:
            flash('Teacher access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def accounts_required(f):
    """Decorator to require accounts officer or admin roles."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        allowed = [UserRole.SUPER_ADMIN, UserRole.HEADTEACHER, UserRole.ADMIN, UserRole.ACCOUNTS_OFFICER]
        if current_user.role not in allowed:
            flash('Accounts access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def parent_required(f):
    """Decorator to require parent role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != UserRole.PARENT:
            flash('Parent access required.', 'error')
            return redirect(get_user_home())
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    """Decorator to require any staff role (not parent)."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role == UserRole.PARENT:
            flash('Staff access required.', 'error')
            return redirect(url_for('parent.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
# Create app instance for gunicorn (production)
app = create_app(os.environ.get('FLASK_CONFIG', 'production'))

if __name__ == '__main__':
    app = create_app(os.environ.get('FLASK_CONFIG', 'development'))
    
    with app.app_context():
        db.create_all()
    
    app.run(debug=True, port=5008)
