"""
Authentication & authorization primitives.

Two distinct identity types share one Flask-Login session, distinguished by the
get_id() prefix:
  - "user:<id>"     -> models.User      (in-school: school_admin/teacher/...)
  - "platform:<id>" -> models.PlatformUser (super admin, cross-tenant)

Tenant isolation is enforced by:
  - resolving g.current_school_id from the logged-in *user's* school_id only
    (never from the URL),
  - @require_role to gate by role,
  - @require_same_school to verify a fetched resource belongs to the request's
    school (defence in depth on top of tenant_query()).
"""
from functools import wraps

from flask import g, abort
from flask_login import current_user

from extensions import login_manager, bcrypt, db
from models.operational import User
from models.platform import PlatformUser


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(plaintext):
    return bcrypt.generate_password_hash(plaintext).decode('utf-8')


def verify_password(password_hash, plaintext):
    if not password_hash:
        return False
    return bcrypt.check_password_hash(password_hash, plaintext)


# ---------------------------------------------------------------------------
# Flask-Login user loader
# ---------------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    """
    user_id is the value from get_id(): "user:<id>" or "platform:<id>".
    PlatformUser needs is_authenticated/get_id from UserMixin-like behaviour;
    we provide a thin wrapper below.
    """
    try:
        kind, raw_id = user_id.split(':', 1)
        obj_id = int(raw_id)
    except (ValueError, AttributeError):
        return None

    if kind == 'user':
        user = db.session.get(User, obj_id)
        return user if (user and user.is_active) else None
    if kind == 'platform':
        pu = db.session.get(PlatformUser, obj_id)
        if pu and pu.is_active:
            return PlatformIdentity(pu)
    return None


class PlatformIdentity:
    """
    Flask-Login identity wrapper for a super admin. Kept separate from User so
    a super admin can never accidentally satisfy an in-school role check or be
    bound to a single school_id.
    """
    is_super_admin = True
    role = 'super_admin'
    school_id = None

    def __init__(self, platform_user):
        self._pu = platform_user
        self.id = platform_user.id
        self.email = platform_user.email
        self.name = platform_user.name

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self._pu.is_active

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return f'platform:{self.id}'


def is_platform_user(user=None):
    user = user or current_user
    return getattr(user, 'is_super_admin', False) is True


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------
def require_role(*roles):
    """
    Allow only the given in-school roles. Super admins are NOT granted in-school
    roles by default (spec: no access to grades/students by default) — they use
    the /platform blueprint. Pass 'super_admin' explicitly to allow them.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            user_role = getattr(current_user, 'role', None)
            user_role = user_role.value if hasattr(user_role, 'value') else user_role
            if user_role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def platform_only(view):
    """Restrict a view to super admins (the /platform blueprint)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not is_platform_user():
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def require_same_school(*model_kwarg_pairs):
    """
    Verify that resources named in the URL belong to g.current_school_id.

    Usage:
        @require_same_school((Student, 'student_id'), (Class, 'class_id'))
        def view(student_id, class_id): ...

    For each (Model, kwarg) it loads Model by the kwarg's value scoped to the
    current school; a mismatch returns 404 (not 403) so we don't leak the
    existence of other tenants' resources.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            school_id = getattr(g, 'current_school_id', None)
            if school_id is None:
                abort(403)
            for model, kwarg in model_kwarg_pairs:
                obj_id = kwargs.get(kwarg)
                if obj_id is None:
                    continue
                obj = model.query.filter(
                    model.id == obj_id, model.school_id == school_id
                ).first()
                if obj is None:
                    abort(404)
            return view(*args, **kwargs)
        return wrapper
    return decorator
