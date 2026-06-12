"""
Audit log helper.

Records who did what to which entity. Works for both in-school users and
platform super admins (school_id left None for platform actions).
"""
from flask import g, request, has_request_context

from extensions import db
from models.operational import AuditLog


def log_action(action, entity=None, entity_id=None, meta=None,
               school_id=None, user_id=None, commit=False):
    """
    Append an audit entry.

    By default it reads the current school/user from `g` (set per-request in
    the app factory), but callers may override — e.g. during signup, before a
    user context exists, or for platform actions.

    commit=False: the entry is added to the session and flushed with the
    surrounding transaction. Pass commit=True for standalone logging.
    """
    if school_id is None:
        school_id = getattr(g, 'current_school_id', None)
    if user_id is None:
        user_id = getattr(g, 'current_user_id', None)

    if meta is None:
        meta = {}
    if has_request_context():
        meta.setdefault('ip', request.remote_addr)
        meta.setdefault('path', request.path)

    entry = AuditLog(
        school_id=school_id,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        meta=meta,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
