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
try:
    from flask_apscheduler import APScheduler
    _scheduler_available = True
except ImportError:
    APScheduler = None
    _scheduler_available = False

from dotenv import load_dotenv

from config import config
from models import db, User, UserRole, School, AcademicYear, Term

# Load environment variables early
load_dotenv()

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
scheduler = APScheduler() if _scheduler_available else None


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

    @app.cli.command("seed-prod")
    def seed_prod_command():
        """Safe production seed — creates tables, Super Admin, and one demo school.
        Idempotent: skips if users already exist."""
        from models import init_db, ModuleConfig, SubscriptionPlan, Subscription
        from decimal import Decimal

        init_db(app)

        # Skip if any user already exists
        if User.query.first():
            print("Users already exist — skipping seed.")
            return

        # 1. SaaS HQ school (container for Super Admin)
        hq = School(name="SmartSchool SaaS HQ", email="superadmin@smartschool.com",
                     motto="Powering Ghanaian Education", school_type="SaaS Platform")
        db.session.add(hq)
        db.session.flush()

        sa = User(school_id=hq.id, email="superadmin@smartschool.com",
                  role=UserRole.SUPER_ADMIN)
        sa.set_password("smart_saas_2026")
        db.session.add(sa)
        db.session.add(ModuleConfig(school_id=hq.id, is_ai_enabled=True,
                                     is_sms_enabled=True, is_finance_enabled=True))

        # 2. Subscription plans
        plans = [
            SubscriptionPlan(name="Basic", price=Decimal('49.00'), student_limit=100,
                             features={'core': True, 'reports': True}),
            SubscriptionPlan(name="Standard", price=Decimal('149.00'), student_limit=500,
                             features={'core': True, 'reports': True, 'fees': True, 'sms': True}),
            SubscriptionPlan(name="Elite", price=Decimal('499.00'), student_limit=5000,
                             features={'all': True, 'ai': True, 'marketplace': True,
                                       'predictive': True, 'voice': True}),
        ]
        db.session.add_all(plans)
        db.session.flush()

        # 3. One demo school (Elite tier) so you can demo everything
        from datetime import date
        demo = School(name="Demo International School", email="admin@demo.smartschool.com",
                       city="Accra", region="Greater Accra", phone="0241234567",
                       motto="Excellence in Education", school_type="Primary & JHS",
                       established_year=2005)
        db.session.add(demo)
        db.session.flush()
        db.session.add(Subscription(school_id=demo.id, plan_id=plans[2].id,
                                     status='active',
                                     end_date=date.today().replace(year=date.today().year + 1)))
        db.session.add(ModuleConfig(school_id=demo.id, is_ai_enabled=True,
                                     is_sms_enabled=True, is_finance_enabled=True))

        # Headteacher user
        ht = User(school_id=demo.id, email="head@demo.smartschool.com",
                  role=UserRole.HEADTEACHER)
        ht.set_password("head123")
        db.session.add(ht)

        # School Admin user
        adm = User(school_id=demo.id, email="admin@demo.smartschool.com",
                   role=UserRole.ADMIN)
        adm.set_password("admin123")
        db.session.add(adm)

        # Teacher user
        tch = User(school_id=demo.id, email="teacher@demo.smartschool.com",
                   role=UserRole.TEACHER)
        tch.set_password("teacher123")
        db.session.add(tch)

        # Academic Year + Terms
        ay = AcademicYear(school_id=demo.id, name="2025/2026",
                          start_date=date(2025, 9, 1), end_date=date(2026, 7, 31),
                          is_current=True)
        db.session.add(ay)
        db.session.flush()

        for i, tn in enumerate(["First Term", "Second Term", "Third Term"], 1):
            t = Term(academic_year_id=ay.id, name=tn, term_number=i,
                     start_date=date(2025, 9 + (i-1)*4, 1),
                     end_date=date(2025, 12 + (i-1)*4, 20) if i < 3 else date(2026, 7, 20),
                     is_current=(i == 2))
            db.session.add(t)

        db.session.commit()

        print()
        print("=" * 60)
        print("PRODUCTION SEED COMPLETE — Credentials:")
        print("=" * 60)
        print(f"  {'Super Admin':<14} superadmin@smartschool.com       smart_saas_2026")
        print(f"  {'Headteacher':<14} head@demo.smartschool.com        head123")
        print(f"  {'School Admin':<14} admin@demo.smartschool.com       admin123")
        print(f"  {'Teacher':<14} teacher@demo.smartschool.com     teacher123")
        print("=" * 60)

    # ── APScheduler: scheduled jobs (only if flask_apscheduler is installed) ──
    if _scheduler_available and scheduler:
        app.config['SCHEDULER_API_ENABLED'] = False
        scheduler.init_app(app)

        @scheduler.task('cron', id='weekly_briefing', day_of_week='fri', hour=16, minute=0,
                        misfire_grace_time=900)
        def weekly_briefing_job():
            """Every Friday 4 PM: send weekly vitals to each school's headteacher."""
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
