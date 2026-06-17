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

# Rate limiter — used to blunt login brute-force. Storage URI comes from config
# (RATELIMIT_STORAGE_URI / REDIS_URL, else memory://). No global default limits
# (opt-in per route). in_memory_fallback_enabled keeps logins working if Redis
# is briefly unreachable (fail-open) instead of locking everyone out.
limiter = Limiter(key_func=get_remote_address, default_limits=[],
                  in_memory_fallback_enabled=True)

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'warning'
