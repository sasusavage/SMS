"""
NaCCA School Management System - Main Application
Flask Application Factory with RBAC
"""
import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, g, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_apscheduler import APScheduler

from dotenv import load_dotenv

from config import config
from models import db, User, UserRole, School, AcademicYear, Term

# Load environment variables early
load_dotenv()

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
scheduler = APScheduler()


def create_app(config_name='default'):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Persistent-volume file serving (/uploads/<subfolder>/<filename>)
    @app.route('/uploads/<path:filename>')
    @login_required
    def serve_upload(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
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
        from models import ModuleConfig
        config = None
        if current_user.is_authenticated:
            config = ModuleConfig.query.filter_by(school_id=current_user.school_id).first()
            
        return dict(
            current_year=datetime.now().year,
            UserRole=UserRole,
            module_config=config
        )
    
    @app.before_request
    def before_request():
        if current_user.is_authenticated:
            # Super Admin has no school context — skip school-scoped lookups
            if current_user.role == UserRole.SUPER_ADMIN:
                g.current_academic_year = None
                g.current_term = None
                return

            # Load school status
            from models import School
            school = School.query.get(current_user.school_id)

            # Global Suspension Guard
            if school and school.is_account_suspended:
                allowed_endpoints = ['auth.logout', 'admin.support_contact']
                if request.endpoint not in allowed_endpoints:
                    flash(f"Account Suspended: {school.suspension_reason}", "error")
                    return redirect(url_for('admin.support_contact'))

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
    from routes.saas_admin import saas_admin_bp
    from routes.students import students_bp
    from routes.staff import staff_bp
    from routes.classes import classes_bp
    from routes.assessments import assessments_bp
    from routes.fees import fees_bp
    from routes.reports import reports_bp
    from routes.parent_portal import parent_bp
    from routes.api import api_bp
    from routes.admin import admin_bp
    from routes.api_ai import ai_bp
    from routes.market import market_bp
    from routes.migration import migration_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(saas_admin_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(fees_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(migration_bp)
    
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
    
    # CLI Commands
    @app.cli.command("run-analytics")
    def run_analytics_command():
        """Midnight task to generate school insights."""
        from services.analytics_engine import run_midnight_analytics
        run_midnight_analytics()
        print("Sasu AI: School Insights generated for all active schools.")

    # ── APScheduler: scheduled jobs ──────────────────────────────────────────
    app.config['SCHEDULER_API_ENABLED'] = False
    scheduler.init_app(app)

    @scheduler.task('cron', id='weekly_briefing', day_of_week='fri', hour=16, minute=0,
                    misfire_grace_time=900)
    def weekly_briefing_job():
        """Every Friday 4 PM: send weekly vitals PDF to each school's headteacher."""
        with app.app_context():
            from services.report_service import send_weekly_vitals
            send_weekly_vitals()

    @scheduler.task('cron', id='midnight_analytics', hour=0, minute=5,
                    misfire_grace_time=300)
    def midnight_analytics_job():
        """Daily 00:05: run predictive analytics for all schools."""
        with app.app_context():
            from services.analytics_engine import run_midnight_analytics
            run_midnight_analytics()

    scheduler.start()

    return app


# decorators have been moved to utils/decorators.py to avoid circular imports


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
# Create app instance for gunicorn (production)
app = create_app(os.environ.get('FLASK_CONFIG', 'production'))

if __name__ == '__main__':
    app = create_app(os.environ.get('FLASK_CONFIG', 'development'))
    
    from models import init_db
    init_db(app)
    
    app.run(debug=True, port=5008)
