"""
Notification service (Phase 2) — multi-tenant email + SMS.

Mirrors the slidein pattern (every send recorded in notification_logs; a stub
'logged' status when no provider is configured) but adapted for multi-tenancy:

  Email: per-school SMTP if the school enabled it, else the platform SMTP
         fallback, else stub-log.
  SMS:   Vynfy via the platform's bridge URL + API key (shared by all tenants),
         with each school's own sender ID. Mirrors slidein's phone normalisation
         (233..., no '+') and the known bridge quirk where a store_message /
         "Internal Bridge Error" response still means the SMS was dispatched.

Sends are best-effort and NEVER raise into the caller — a failed notification
must not break the action that triggered it (publishing results, etc.).
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

from extensions import db
from models.notifications import (
    SchoolNotificationSettings, NotificationLog,
)
from services import secrets_box, platform_settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def send_email(school_id, to, subject, body):
    """Send an email for a school (per-school SMTP -> platform -> stub)."""
    entry = NotificationLog(school_id=school_id, channel='email', recipient=to,
                            subject=subject, message=body, status='queued')
    db.session.add(entry)
    try:
        cfg = _email_config(school_id)
        if cfg is None:
            entry.provider = 'stub'
            entry.status = 'logged'
            log.info('[EMAIL stub] -> %s: %s', to, subject)
        else:
            entry.provider = cfg['provider']
            _smtp_send(cfg, to, subject, body)
            entry.status = 'sent'
    except Exception as e:  # noqa: BLE001 — never raise into caller
        entry.status = 'failed'
        entry.error = str(e)[:500]
        log.exception('Email send failed')
    _commit()
    return entry


def send_sms(school_id, phone, message):
    """Send an SMS for a school via the Vynfy bridge (-> stub if unconfigured)."""
    phone = _normalize_phone(phone)
    entry = NotificationLog(school_id=school_id, channel='sms', recipient=phone,
                            message=message, status='queued')
    db.session.add(entry)
    try:
        cfg = _sms_config(school_id)
        if cfg is None:
            entry.provider = 'stub'
            entry.status = 'logged'
            log.info('[SMS stub] -> %s: %s', phone, message)
        else:
            entry.provider = 'vynfy'
            result = _vynfy_send(cfg, phone, message)
            if isinstance(result, dict):
                data = result.get('data') or {}
                entry.provider_message_id = (data.get('job_id')
                                             or data.get('task_id'))
            entry.status = 'sent'
    except Exception as e:  # noqa: BLE001
        entry.status = 'failed'
        entry.error = str(e)[:500]
        log.exception('SMS send failed')
    _commit()
    return entry


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------
def _email_config(school_id):
    """Resolve effective SMTP config: per-school -> platform -> None (stub)."""
    s = (SchoolNotificationSettings.query.filter_by(school_id=school_id).first()
         if school_id else None)
    if s and s.smtp_enabled and s.smtp_host:
        return {
            'provider': 'smtp', 'host': s.smtp_host, 'port': s.smtp_port or 587,
            'use_tls': bool(s.smtp_use_tls), 'username': s.smtp_username,
            'password': secrets_box.decrypt(s.smtp_password_enc),
            'from_email': s.smtp_from_email or s.smtp_username,
            'from_name': s.smtp_from_name,
        }
    # Platform fallback.
    host = platform_settings.get('smtp_host')
    if host:
        return {
            'provider': 'platform_smtp', 'host': host,
            'port': int(platform_settings.get('smtp_port') or 587),
            'use_tls': (platform_settings.get('smtp_use_tls') or '1') not in
                       ('0', 'false', 'False', ''),
            'username': platform_settings.get('smtp_username'),
            'password': platform_settings.get('smtp_password'),
            'from_email': (platform_settings.get('smtp_from_email')
                           or platform_settings.get('smtp_username')),
            'from_name': platform_settings.get('smtp_from_name'),
        }
    return None


def _sms_config(school_id):
    """Vynfy config: platform bridge URL + key, per-school sender id."""
    api_key = platform_settings.get('vynfy_api_key')
    base_url = (platform_settings.get('vynfy_base_url')
                or 'https://sms.vynfy.com').rstrip('/')
    if not api_key:
        return None
    sender = platform_settings.get('vynfy_sender_id') or 'SchoolBrn'
    if school_id:
        s = SchoolNotificationSettings.query.filter_by(
            school_id=school_id).first()
        if s and s.sms_enabled and s.sms_sender_id:
            sender = s.sms_sender_id
        elif s and not s.sms_enabled:
            return None  # school explicitly hasn't enabled SMS
    return {'api_key': api_key, 'base_url': base_url, 'sender': sender[:11]}


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------
def _smtp_send(cfg, to, subject, body):
    if not cfg.get('host'):
        raise ValueError('SMTP host not configured.')
    from_email = cfg.get('from_email') or cfg.get('username')
    from_name = cfg.get('from_name')
    from_header = f'{from_name} <{from_email}>' if from_name else from_email

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_header
    msg['To'] = to
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(cfg['host'], cfg.get('port', 587), timeout=20) as server:
        server.ehlo()
        if cfg.get('use_tls', True):
            server.starttls()
            server.ehlo()
        if cfg.get('username') and cfg.get('password'):
            server.login(cfg['username'], cfg['password'])
        server.sendmail(from_email, [to], msg.as_string())


def _vynfy_send(cfg, phone, message):
    """POST to the Vynfy bridge. Mirrors slidein incl. the bridge-quirk handling."""
    url = f"{cfg['base_url']}/api/v1/send"
    headers = {'X-API-Key': cfg['api_key'], 'Content-Type': 'application/json'}
    payload = {'message': message, 'recipients': [phone], 'sender': cfg['sender']}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if not resp.ok:
        try:
            err = resp.json()
        except Exception:
            err = {}
        detail = err.get('detail', '') if isinstance(err, dict) else ''
        # Known bridge bug: logging step fails but the SMS was dispatched.
        if 'store_message' in detail or 'Internal Bridge Error' in detail:
            log.warning('Vynfy bridge error (SMS likely sent): %s', detail)
            return {'ok': True, 'warning': detail}
        raise Exception(f'Vynfy error: {resp.text[:300]}')
    return resp.json()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _normalize_phone(phone):
    """
    Ghana E.164-ish for Vynfy: 233XXXXXXXXX (12 digits, no leading +).
    A Ghana mobile is 233 + 9 national digits. Accepts the common inputs:
      0XXXXXXXXX (local)        -> drop the 0, prepend 233
      +233XXXXXXXXX / 233...    -> strip + (already international)
      XXXXXXXXX (bare 9 digits) -> prepend 233
    """
    if not phone:
        return phone
    p = ''.join(ch for ch in str(phone) if ch.isdigit())  # digits only (drops +)
    if p.startswith('233'):
        return p
    p = p.lstrip('0')          # drop ANY leading zero(s), not just for len==10
    return '233' + p


def _commit():
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# Test-send (used by the settings "send test" buttons)
# ---------------------------------------------------------------------------
def test_email(school_id, to):
    return send_email(school_id, to, 'SchoolBrain test email',
                      'This is a test email from SchoolBrain. If you received '
                      'it, your email settings work.')


def test_sms(school_id, phone):
    return send_sms(school_id, phone,
                    'SchoolBrain test SMS — your SMS settings work.')


# ---------------------------------------------------------------------------
# High-level triggers (best-effort; never raise into the caller)
# ---------------------------------------------------------------------------
def notify_results_published(school_id, class_id, term_id):
    """
    Notify the guardians of students in a class+term that results are out.
    Uses guardian_phone (SMS) and linked parent users' email. Returns a count
    of messages attempted.
    """
    from models.operational import (
        Student, TermResult, ParentStudent, User,
    )
    from models.config_tables import Term, Class
    try:
        term = Term.query.filter_by(school_id=school_id, id=term_id).first()
        klass = Class.query.filter_by(school_id=school_id, id=class_id).first()
        term_name = term.name if term else 'this term'
        class_name = klass.name if klass else ''
    except Exception:
        term_name, class_name = 'this term', ''

    # Students in this class with at least one published result this term.
    student_ids = {
        sid for (sid,) in TermResult.query
        .with_entities(TermResult.student_id)
        .filter_by(school_id=school_id, class_id=class_id, term_id=term_id,
                   is_published=True).all()
    }
    count = 0
    for sid in student_ids:
        student = db.session.get(Student, sid)
        if student is None:
            continue
        msg = (f'Results for {student.first_name} ({class_name}) for '
               f'{term_name} have been published. Log in to SchoolBrain to view.')
        # SMS to guardian phone (if any).
        if student.guardian_phone:
            send_sms(school_id, student.guardian_phone, msg)
            count += 1
        # Email to each linked parent user with an email.
        links = ParentStudent.query.filter_by(
            school_id=school_id, student_id=sid).all()
        for link in links:
            parent = db.session.get(User, link.parent_user_id)
            if parent and parent.email:
                send_email(school_id, parent.email,
                           f'Results published — {term_name}', msg)
                count += 1
    return count


def notify_absentees(school_id, class_id, on_date, marks):
    """
    SMS guardians of students marked absent on a given day. `marks` is the
    {student_id: status} dict that was just saved. Best-effort.
    """
    from models.operational import Student
    count = 0
    for student_id, status in marks.items():
        if status != 'absent':
            continue
        try:
            student = db.session.get(Student, int(student_id))
        except (TypeError, ValueError):
            continue
        if student and student.school_id == school_id and student.guardian_phone:
            send_sms(school_id, student.guardian_phone,
                     f'{student.first_name} {student.last_name} was marked '
                     f'absent on {on_date}. Please contact the school if this '
                     f'is unexpected.')
            count += 1
    return count


def notify_payment_received(school_id, amount_ghs, plan_name=None):
    """
    Email the school's admins confirming a subscription payment. Best-effort.
    """
    from models.operational import User
    from models.enums import UserRole
    try:
        admins = User.query.filter_by(
            school_id=school_id, role=UserRole.school_admin,
            is_active=True).all()
        plan_line = f' for the {plan_name} plan' if plan_name else ''
        body = (f'We received your payment of GHS {amount_ghs:.2f}{plan_line}. '
                f'Your subscription is now active. Thank you.')
        for a in admins:
            if a.email:
                send_email(school_id, a.email,
                           'Payment received — SchoolBrain', body)
    except Exception:  # noqa: BLE001
        log.exception('payment-received notification failed')


def notify_account_created(school_id, user, plaintext_password=None):
    """Send a welcome email/SMS with login info when a user is created."""
    try:
        if not user or not user.email:
            return
        pw_line = (f'\nTemporary password: {plaintext_password}'
                   if plaintext_password else '')
        body = (f'Hello {user.name},\n\nAn account has been created for you on '
                f'SchoolBrain.\nEmail: {user.email}{pw_line}\n\n'
                f'Please log in and change your password.')
        send_email(school_id, user.email, 'Your SchoolBrain account', body)
    except Exception:  # noqa: BLE001
        log.exception('account-created notification failed')
