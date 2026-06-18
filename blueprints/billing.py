"""
/admin/billing — school subscription billing via Paystack.

  GET  /admin/billing                school_admin: current subscription + plans
  POST /admin/billing/checkout       start a Paystack checkout for a plan
  GET  /billing/callback             Paystack redirects here (?reference=...)
  POST /billing/webhook              Paystack server-to-server (signed; CSRF-exempt)

Subscription activation is idempotent (services.billing.complete_payment), so a
missed callback is still covered by the webhook and vice-versa.
"""
import logging

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
    current_app,
)
from flask_login import login_required, current_user

from extensions import db, csrf
from auth.security import require_role
from services import billing, paystack
from services.billing import BillingError
from services.audit import log_action
from models.platform import Plan, Subscription, Payment

log = logging.getLogger(__name__)
billing_bp = Blueprint('billing', __name__)


# ---------------------------------------------------------------------------
# School-facing billing (school_admin)
# ---------------------------------------------------------------------------
@billing_bp.route('/admin/billing')
@login_required
@require_role('school_admin')
def index():
    if g.get('current_school_id') is None:
        abort(403)
    sid = g.current_school_id
    plans = Plan.query.order_by(Plan.price_ghs).all()
    current = (Subscription.query.filter_by(school_id=sid)
               .order_by(Subscription.id.desc()).first())
    payments = (Payment.query.filter_by(school_id=sid)
                .order_by(Payment.id.desc()).limit(10).all())
    return render_template('billing/index.html', plans=plans, current=current,
                           payments=payments,
                           configured=paystack.is_configured())


@billing_bp.route('/admin/billing/checkout', methods=['POST'])
@login_required
@require_role('school_admin')
def checkout():
    if g.get('current_school_id') is None:
        abort(403)
    sid = g.current_school_id
    plan_id = _int(request.form.get('plan_id'))
    email = (request.form.get('email') or current_user.email or '').strip()
    callback = url_for('billing.callback', _external=True)
    try:
        out = billing.start_checkout(sid, plan_id, email, callback)
        log_action('billing_checkout', entity='school', entity_id=sid,
                   meta={'plan_id': plan_id, 'reference': out['reference']})
        db.session.commit()
        return redirect(out['url'])
    except BillingError as e:
        db.session.rollback()
        flash(e.message, 'danger')
        return redirect(url_for('billing.index'))


@billing_bp.route('/billing/callback')
@login_required
def callback():
    """Paystack redirects the user back here after payment."""
    reference = request.args.get('reference') or request.args.get('trxref')
    if not reference:
        flash('No payment reference returned.', 'warning')
        return redirect(url_for('billing.index'))

    # Fee payment (parent paying a student invoice) — route by prefix.
    if reference.startswith('FEE-'):
        try:
            pay = billing.complete_fee_payment(reference)
            if pay is not None:
                flash('Payment received — thank you.', 'success')
            else:
                flash('Payment not completed. If you were charged, it will be '
                      'confirmed shortly.', 'warning')
        except Exception:  # noqa: BLE001
            flash('Could not confirm the payment yet — it will update shortly.',
                  'warning')
        # Send the user back to the fee page if we can derive the student.
        try:
            student_id = int(reference.split('-')[2 + 1])  # FEE-school-INVOICE-...
        except (ValueError, IndexError):
            student_id = None
        return redirect(url_for('dashboard.index'))

    try:
        payment = billing.complete_payment(reference)
        if payment.status == 'success':
            flash('Payment successful — your subscription is active.', 'success')
        else:
            flash('Payment was not completed. If you were charged, it will be '
                  'confirmed shortly.', 'warning')
    except BillingError as e:
        flash(e.message, 'danger')
    return redirect(url_for('billing.index'))


# ---------------------------------------------------------------------------
# Paystack webhook (server-to-server, signed) — CSRF exempt
# ---------------------------------------------------------------------------
@billing_bp.route('/billing/webhook', methods=['POST'])
@csrf.exempt
def webhook():
    raw = request.get_data()
    signature = request.headers.get('x-paystack-signature', '')
    if not paystack.verify_webhook_signature(raw, signature):
        log.warning('Rejected Paystack webhook: bad signature')
        abort(400)
    event = request.get_json(silent=True) or {}
    if event.get('event') == 'charge.success':
        reference = (event.get('data') or {}).get('reference')
        if reference:
            try:
                # Route by reference prefix: FEE-... = student fee, else subscription.
                if reference.startswith('FEE-'):
                    billing.complete_fee_payment(reference)
                else:
                    billing.complete_payment(reference)
            except Exception:  # noqa: BLE001
                log.exception('webhook payment completion failed')
    return ('', 200)


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None
