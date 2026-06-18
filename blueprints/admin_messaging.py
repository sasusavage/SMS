"""
/admin/messaging — notification log viewer, retry, bulk SMS, fee reminders.
school_admin only, tenant-scoped.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
)
from flask_login import login_required

from extensions import db
from auth.security import require_role
from services.tenant import tenant_query
from services.audit import log_action
from services import notify
from models.config_tables import Class, Term

messaging_bp = Blueprint('admin_messaging', __name__, url_prefix='/admin/messaging')


@messaging_bp.before_request
@login_required
@require_role('school_admin')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


@messaging_bp.route('/')
def index():
    sid = _sid()
    channel = request.args.get('channel') or None
    status = request.args.get('status') or None
    logs = notify.recent_logs(sid, limit=200, channel=channel, status=status)
    return render_template('admin/messaging/index.html', logs=logs,
                           channel=channel, status=status)


@messaging_bp.route('/<int:log_id>/retry', methods=['POST'])
def retry(log_id):
    entry = notify.retry_log(_sid(), log_id)
    if entry is None:
        flash('Log not found.', 'danger')
    elif entry.status == 'sent':
        flash('Resent successfully.', 'success')
    elif entry.status == 'logged':
        flash('No provider configured — logged only.', 'warning')
    else:
        flash(f'Retry failed: {entry.error}', 'danger')
    log_action('retry_notification', 'notification_log', log_id)
    db.session.commit()
    return redirect(url_for('admin_messaging.index'))


@messaging_bp.route('/bulk', methods=['GET', 'POST'])
def bulk():
    sid = _sid()
    classes = tenant_query(Class).order_by(Class.name).all()
    if request.method == 'POST':
        message = (request.form.get('message') or '').strip()
        target = request.form.get('target')  # 'class:<id>' or 'all'
        if not message:
            flash('Enter a message.', 'danger')
        elif target == 'all':
            n = notify.bulk_sms_all_guardians(sid, message)
            log_action('bulk_sms', 'school', sid, meta={'target': 'all', 'count': n})
            db.session.commit()
            flash(f'Queued {n} SMS to all guardians.', 'success')
        elif target and target.startswith('class:'):
            class_id = _int(target.split(':', 1)[1])
            # tenant check
            if tenant_query(Class).filter_by(id=class_id).first() is None:
                abort(404)
            n = notify.bulk_sms_to_class(sid, class_id, message)
            log_action('bulk_sms', 'class', class_id, meta={'count': n})
            db.session.commit()
            flash(f'Queued {n} SMS to that class.', 'success')
        else:
            flash('Pick a target.', 'warning')
        return redirect(url_for('admin_messaging.index'))
    return render_template('admin/messaging/bulk.html', classes=classes)


@messaging_bp.route('/fee-reminders', methods=['GET', 'POST'])
def fee_reminders():
    sid = _sid()
    terms = tenant_query(Term).order_by(Term.sequence).all()
    if request.method == 'POST':
        term_id = _int(request.form.get('term_id'))
        n = notify.send_fee_reminders(sid, term_id=term_id)
        log_action('fee_reminders', 'school', sid,
                   meta={'term_id': term_id, 'count': n})
        db.session.commit()
        flash(f'Sent {n} fee reminder(s).', 'success')
        return redirect(url_for('admin_messaging.index'))
    return render_template('admin/messaging/fee_reminders.html', terms=terms)


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None
