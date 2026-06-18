"""
Per-school notification settings (SMTP + SMS) helpers. Tenant-scoped.
SMTP password is encrypted at rest via secrets_box.
"""
from extensions import db
from models.notifications import SchoolNotificationSettings
from services import secrets_box


def get_or_create(school_id):
    s = SchoolNotificationSettings.query.filter_by(school_id=school_id).first()
    if s is None:
        s = SchoolNotificationSettings(school_id=school_id)
        db.session.add(s)
        db.session.flush()
    return s


def update_smtp(school_id, *, enabled, host, port, use_tls, username,
                password, from_email, from_name):
    s = get_or_create(school_id)
    s.smtp_enabled = bool(enabled)
    s.smtp_host = (host or '').strip() or None
    s.smtp_port = int(port) if str(port).strip().isdigit() else 587
    s.smtp_use_tls = bool(use_tls)
    s.smtp_username = (username or '').strip() or None
    # Only overwrite the password if a new one was supplied (blank = keep old).
    if password:
        s.smtp_password_enc = secrets_box.encrypt(password)
    s.smtp_from_email = (from_email or '').strip() or None
    s.smtp_from_name = (from_name or '').strip() or None
    db.session.flush()
    return s


def update_sms(school_id, *, enabled, sender_id):
    s = get_or_create(school_id)
    s.sms_enabled = bool(enabled)
    s.sms_sender_id = (sender_id or '').strip()[:11] or None
    db.session.flush()
    return s
