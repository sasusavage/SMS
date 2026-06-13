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
from extensions import db, migrate, login_manager, bcrypt, csrf

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

    return app


def _register_request_hooks(app):
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


def _register_blueprints(app):
    from auth.routes import auth_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.platform import platform_bp
    from blueprints.admin_config import config_bp
    from blueprints.onboarding import onboarding_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(platform_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(onboarding_bp)


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


# Module-level app for `flask` CLI (flask db ...) and gunicorn.
app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
