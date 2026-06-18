"""
Platform (super admin) blueprint — Step 8.

CROSS-TENANT super-admin area: platform dashboard/metrics, schools list with
suspend/activate, per-school detail, manual subscriptions, and plans CRUD.
Gated entirely by @platform_only (super admins only) — there is no tenant
scope here. All state-changing routes are CSRF-protected and audited.

Paystack billing is Phase 2; subscriptions are marked manually.
"""
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort,
)
from flask_login import current_user

from extensions import db
from auth.security import platform_only
from services import platform as plat
from services.platform import PlatformError
from services.audit import log_action
from models.platform import School, Plan

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


@platform_bp.before_request
@platform_only
def _guard():
    pass


def _audit(action, entity=None, entity_id=None, meta=None):
    log_action(action, entity=entity, entity_id=entity_id, meta=meta,
               user_id=getattr(current_user, 'id', None))


# ---------------------------------------------------------------------------
# Dashboard + schools list
# ---------------------------------------------------------------------------
@platform_bp.route('/')
def index():
    metrics = plat.platform_metrics()
    schools = School.query.order_by(School.created_at.desc()).all()
    return render_template('platform/index.html', metrics=metrics,
                           schools=schools)


@platform_bp.route('/schools/<int:school_id>')
def school_detail(school_id):
    try:
        detail = plat.school_detail(school_id)
    except PlatformError:
        abort(404)
    plans = Plan.query.order_by(Plan.price_ghs).all()
    return render_template('platform/school_detail.html', plans=plans, **detail)


@platform_bp.route('/schools/<int:school_id>/suspend', methods=['POST'])
def suspend(school_id):
    try:
        plat.suspend_school(school_id)
        _audit('suspend_school', entity='school', entity_id=school_id)
        db.session.commit()
        flash('School suspended. Its users can no longer sign in.', 'info')
    except PlatformError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('platform.school_detail', school_id=school_id))


@platform_bp.route('/schools/<int:school_id>/activate', methods=['POST'])
def activate(school_id):
    try:
        plat.activate_school(school_id)
        _audit('activate_school', entity='school', entity_id=school_id)
        db.session.commit()
        flash('School activated.', 'success')
    except PlatformError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('platform.school_detail', school_id=school_id))


# ---------------------------------------------------------------------------
# Subscriptions (manual)
# ---------------------------------------------------------------------------
@platform_bp.route('/schools/<int:school_id>/subscription', methods=['POST'])
def set_subscription(school_id):
    try:
        plat.set_subscription(
            school_id, _int(request.form.get('plan_id')),
            starts_on=_date(request.form.get('starts_on')),
            ends_on=_date(request.form.get('ends_on')),
            status=request.form.get('status') or 'active')
        _audit('set_subscription', entity='school', entity_id=school_id)
        db.session.commit()
        flash('Subscription updated.', 'success')
    except PlatformError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('platform.school_detail', school_id=school_id))


# ---------------------------------------------------------------------------
# Plans CRUD
# ---------------------------------------------------------------------------
@platform_bp.route('/plans', methods=['GET', 'POST'])
def plans():
    if request.method == 'POST':
        try:
            plat.create_plan(
                name=request.form.get('name'),
                price_ghs=_dec(request.form.get('price_ghs')) or 0,
                max_students=_int(request.form.get('max_students')),
                billing_cycle=request.form.get('billing_cycle') or 'monthly')
            _audit('create_plan', entity='plan')
            db.session.commit()
            flash('Plan created.', 'success')
        except PlatformError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('platform.plans'))
    all_plans = Plan.query.order_by(Plan.price_ghs).all()
    return render_template('platform/plans.html', plans=all_plans)


@platform_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """Platform SMTP (fallback) + Vynfy bridge config."""
    from services import platform_settings as ps
    from services import notify
    if request.method == 'POST':
        section = request.form.get('section')
        if section == 'smtp':
            ps.set('smtp_host', (request.form.get('smtp_host') or '').strip())
            ps.set('smtp_port', (request.form.get('smtp_port') or '587').strip())
            ps.set('smtp_use_tls', '1' if request.form.get('smtp_use_tls') else '0')
            ps.set('smtp_username', (request.form.get('smtp_username') or '').strip())
            ps.set('smtp_from_email', (request.form.get('smtp_from_email') or '').strip())
            ps.set('smtp_from_name', (request.form.get('smtp_from_name') or '').strip())
            if request.form.get('smtp_password'):  # blank = keep existing
                ps.set('smtp_password', request.form.get('smtp_password'))
            _audit('update', entity='platform_smtp')
            db.session.commit()
            flash('Platform SMTP saved.', 'success')
        elif section == 'vynfy':
            ps.set('vynfy_base_url', (request.form.get('vynfy_base_url') or '').strip())
            ps.set('vynfy_sender_id', (request.form.get('vynfy_sender_id') or '').strip())
            if request.form.get('vynfy_api_key'):
                ps.set('vynfy_api_key', request.form.get('vynfy_api_key'))
            _audit('update', entity='platform_vynfy')
            db.session.commit()
            flash('Vynfy SMS settings saved.', 'success')
        elif section == 'test-email':
            to = (request.form.get('to') or '').strip()
            entry = notify.test_email(None, to) if to else None
            if entry and entry.status == 'sent':
                flash(f'Test email sent to {to}.', 'success')
            elif entry and entry.status == 'logged':
                flash('No platform SMTP configured — logged only.', 'warning')
            elif entry:
                flash(f'Test email failed: {entry.error}', 'danger')
            else:
                flash('Enter a recipient.', 'warning')
        elif section == 'test-tenant':
            # Super admin tests a school's email/SMS using THAT school's settings
            # (with platform fallback), exactly as the school would send.
            school_id = _int(request.form.get('school_id'))
            channel = request.form.get('channel')
            to = (request.form.get('to') or '').strip()
            school = db.session.get(School, school_id) if school_id else None
            if not school or not to:
                flash('Pick a school and enter a recipient.', 'warning')
            else:
                if channel == 'sms':
                    entry = notify.test_sms(school.id, to)
                else:
                    entry = notify.test_email(school.id, to)
                label = f'{channel.upper()} for {school.name}'
                if entry.status == 'sent':
                    flash(f'Test {label} sent to {to}.', 'success')
                elif entry.status == 'logged':
                    flash(f'{label}: no provider configured for that school — '
                          'logged only.', 'warning')
                else:
                    flash(f'Test {label} failed: {entry.error}', 'danger')
        return redirect(url_for('platform.settings'))

    return render_template('platform/settings.html',
                           plain=ps.get_all_plain(),
                           has_smtp_pw=ps.has_secret('smtp_password'),
                           has_vynfy_key=ps.has_secret('vynfy_api_key'),
                           schools=School.query.order_by(School.name).all())


@platform_bp.route('/plans/<int:plan_id>/edit', methods=['POST'])
def edit_plan(plan_id):
    try:
        plat.update_plan(
            plan_id, name=request.form.get('name'),
            price_ghs=_dec(request.form.get('price_ghs')),
            max_students=_int(request.form.get('max_students')),
            billing_cycle=request.form.get('billing_cycle'))
        _audit('update_plan', entity='plan', entity_id=plan_id)
        db.session.commit()
        flash('Plan updated.', 'success')
    except PlatformError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('platform.plans'))


@platform_bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
def delete_plan(plan_id):
    try:
        plat.delete_plan(plan_id)
        _audit('delete_plan', entity='plan', entity_id=plan_id)
        db.session.commit()
        flash('Plan deleted.', 'info')
    except PlatformError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('platform.plans'))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _dec(v):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(v)) if v not in (None, '') else None
    except (InvalidOperation, TypeError):
        return None


def _date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        return None
