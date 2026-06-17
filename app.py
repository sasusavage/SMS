"""
SchoolBrain — Flask application factory.

Wires extensions, registers blueprints, and installs the per-request tenant
resolution that powers multi-tenant isolation.
"""
import os

from flask import Flask, g, render_template
from flask_login import current_user
from dotenv import load_dotenv

from config import config
from extensions import db, migrate, login_manager, bcrypt, csrf, limiter

load_dotenv()


def create_app(config_name=None):
    config_name = config_name or os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Import models so they register on db.metadata (needed for migrations and
    # the user loader), then install the tenant query descriptor.
    with app.app_context():
        import models  # noqa: F401
        import auth.security  # noqa: F401  (registers @login_manager.user_loader)
        from services.tenant import install_tenant_query_descriptor
        install_tenant_query_descriptor()

    _register_request_hooks(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_misc(app)

    return app


def _register_request_hooks(app):
    @app.context_processor
    def inject_role():
        """Expose the current user's role as a plain string to all templates."""
        role = None
        if current_user.is_authenticated:
            r = getattr(current_user, 'role', None)
            role = r.value if hasattr(r, 'value') else r
        return {'current_role': role}

    @app.before_request
    def resolve_tenant():
        """
        Resolve the active tenant for this request from the logged-in user —
        NEVER from URL params. Super admins have no tenant (school_id None);
        they operate via the /platform blueprint.
        """
        g.current_school_id = None
        g.current_user_id = None
        if current_user.is_authenticated:
            g.current_user_id = getattr(current_user, 'id', None)
            # PlatformIdentity.school_id is None by design.
            g.current_school_id = getattr(current_user, 'school_id', None)
            # If an in-school user's tenant gets suspended mid-session, log them
            # out on their next request. Super admins (no school_id) are exempt.
            redirect_resp = _enforce_school_active()
            if redirect_resp is not None:
                return redirect_resp

    def _enforce_school_active():
        from flask import request, redirect, url_for, flash
        from flask_login import logout_user
        from models.enums import SchoolStatus
        from models.platform import School

        sid = g.current_school_id
        if sid is None:
            return None
        # Allow auth endpoints so the logout/login redirect itself works.
        if (request.endpoint or '').startswith('auth.') or \
                (request.endpoint or '') == 'static':
            return None
        school = db.session.get(School, sid)
        if school is not None and school.status == SchoolStatus.suspended:
            logout_user()
            flash('Your school has been suspended. Please contact your '
                  'administrator.', 'danger')
            g.current_school_id = None
            g.current_user_id = None
            return redirect(url_for('auth.login'))
        return None


def _register_blueprints(app):
    from auth.routes import auth_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.platform import platform_bp
    from blueprints.admin_config import config_bp
    from blueprints.onboarding import onboarding_bp
    from blueprints.admin_people import people_bp
    from blueprints.teacher import teacher_bp
    from blueprints.admin_results import results_bp
    from blueprints.reports import reports_bp
    from blueprints.portal import portal_bp
    from blueprints.media import media_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(platform_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(people_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(media_bp)


def _register_error_handlers(app):
    @app.errorhandler(401)
    def unauthorized(e):
        return render_template('errors/error.html', code=401,
                               message='Please log in.'), 401

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/error.html', code=403,
                               message='You do not have access to this.'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/error.html', code=404,
                               message='Not found.'), 404

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template('errors/error.html', code=429,
                               message='Too many requests. Please slow down and '
                                       'try again shortly.'), 429

    @app.errorhandler(500)
    def server_error(e):
        # Roll back any half-finished transaction so the session is usable
        # again, and never leak a stack trace to the user.
        db.session.rollback()
        app.logger.exception('Unhandled server error')
        return render_template('errors/error.html', code=500,
                               message='Something went wrong on our end.'), 500


def _register_misc(app):
    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        return resp

    @app.route('/health')
    def health():
        """Lightweight health check for Coolify. Pings the DB cheaply."""
        try:
            db.session.execute(db.text('SELECT 1'))
            return {'status': 'ok'}, 200
        except Exception:
            return {'status': 'degraded'}, 503


# Module-level app for `flask` CLI (flask db ...) and gunicorn.
app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
