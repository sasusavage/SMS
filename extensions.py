"""
Shared Flask extension singletons.

Kept in their own module to avoid circular imports between the app factory,
models, and blueprints.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()

# Rate limiter — used to blunt login brute-force. Default in-memory storage is
# per-worker; for strict limits across multiple gunicorn workers, point
# RATELIMIT_STORAGE_URI at Redis. No global default limits (opt-in per route).
limiter = Limiter(key_func=get_remote_address, default_limits=[])

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'warning'
