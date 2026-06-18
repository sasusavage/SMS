"""
Subscription billing — ties Paystack payments to school subscriptions.

Flow: start_checkout() creates a pending Payment + Paystack init -> checkout
URL. On return, complete_payment(reference) verifies with Paystack and, if
successful, activates the subscription ONCE (idempotent via Payment.activated),
so the callback and the webhook can both fire safely.
"""
import secrets as _secrets
from datetime import date, timedelta, datetime, timezone

from extensions import db
from models.platform import School, Plan, Subscription, Payment
from models.enums import SchoolStatus
from services import paystack


class BillingError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _cycle_days(billing_cycle):
    return 365 if (billing_cycle or 'monthly') == 'annual' else 30


def start_checkout(school_id, plan_id, email, callback_url):
    """
    Create a pending Payment and a Paystack checkout URL.
    Returns {'url': ...} or raises BillingError.
    """
    if not paystack.is_configured():
        raise BillingError('Billing is not configured. Contact the platform admin.')
    school = db.session.get(School, school_id)
    if school is None:
        raise BillingError('School not found.')
    plan = db.session.get(Plan, plan_id)
    if plan is None:
        raise BillingError('Plan not found.')
    if not email:
        raise BillingError('A billing email is required.')

    reference = f'SB-{school_id}-{plan_id}-{_secrets.token_hex(6)}'
    amount = plan.price_ghs or 0
    payment = Payment(
        school_id=school_id, plan_id=plan_id, reference=reference,
        amount_pesewas=paystack.to_pesewas(amount), currency='GHS',
        status='pending', activated=False)
    db.session.add(payment)
    db.session.flush()

    result = paystack.initialize(
        amount=amount, email=email, reference=reference,
        callback_url=callback_url,
        metadata={'school_id': school_id, 'plan_id': plan_id,
                  'school': school.name, 'plan': plan.name})
    if not result.get('ok'):
        payment.status = 'failed'
        payment.paystack_status = result.get('code')
        db.session.commit()
        raise BillingError(result.get('error') or 'Could not start payment.')

    db.session.commit()
    return {'url': result['url'], 'reference': reference}


def complete_payment(reference):
    """
    Verify a payment with Paystack and activate the subscription if successful.
    Idempotent: safe to call from both the callback and the webhook.
    Returns the Payment (updated).
    """
    payment = Payment.query.filter_by(reference=reference).first()
    if payment is None:
        raise BillingError('Unknown payment reference.')
    if payment.activated:
        return payment  # already applied

    result = paystack.verify(reference)
    if not result.get('ok'):
        payment.status = 'failed'
        payment.paystack_status = result.get('error', '')[:40]
        db.session.commit()
        return payment

    payment.paystack_status = result.get('status')
    if result.get('status') != 'success':
        payment.status = 'failed'
        db.session.commit()
        return payment

    # Defence: confirm the amount paid matches what we asked for.
    paid = result.get('amount')
    if paid is not None and int(paid) < payment.amount_pesewas:
        payment.status = 'failed'
        payment.paystack_status = 'amount_mismatch'
        db.session.commit()
        return payment

    # Success -> activate subscription (once).
    payment.status = 'success'
    payment.paid_at = datetime.now(timezone.utc)
    _activate_subscription(payment)
    payment.activated = True
    db.session.commit()

    # Notify school admins (best-effort).
    try:
        from services import notify
        plan = db.session.get(Plan, payment.plan_id)
        notify.notify_payment_received(
            payment.school_id, payment.amount_pesewas / 100,
            plan_name=plan.name if plan else None)
    except Exception:  # noqa: BLE001
        pass
    return payment


def start_fee_checkout(school_id, invoice_id, email, callback_url, amount=None):
    """
    Start a Paystack checkout for a school FEE invoice (parent paying the
    school). Uses the fee reference scheme FEE-<school>-<invoice>-<rand> so the
    callback/webhook can route it to record_payment. Returns {'url','reference'}.
    """
    from services import fees
    if not paystack.is_configured():
        raise BillingError('Online payment is not configured.')
    invoice = fees.get_invoice(school_id, invoice_id)
    bal = fees.balance(school_id, invoice)
    pay_amount = bal if amount is None else min(_to_dec(amount), bal)
    if pay_amount <= 0:
        raise BillingError('Nothing to pay — this invoice is settled.')
    if not email:
        raise BillingError('A billing email is required.')

    reference = f'FEE-{school_id}-{invoice_id}-{_secrets.token_hex(6)}'
    result = paystack.initialize(
        amount=pay_amount, email=email, reference=reference,
        callback_url=callback_url,
        metadata={'kind': 'fee', 'school_id': school_id,
                  'invoice_id': invoice_id})
    if not result.get('ok'):
        raise BillingError(result.get('error') or 'Could not start payment.')
    return {'url': result['url'], 'reference': reference, 'amount': pay_amount}


def complete_fee_payment(reference):
    """
    Verify a fee payment with Paystack and record it against the invoice.
    Idempotent (record_payment dedupes by reference). Parses the school+invoice
    from the FEE-<school>-<invoice>-... reference. Returns the FeePayment or None.
    """
    from services import fees
    parts = reference.split('-')
    if len(parts) < 4 or parts[0] != 'FEE':
        return None
    try:
        school_id = int(parts[1])
        invoice_id = int(parts[2])
    except ValueError:
        return None

    result = paystack.verify(reference)
    if not result.get('ok') or result.get('status') != 'success':
        return None
    amount_ghs = _to_dec(result.get('amount') or 0) / 100  # pesewas -> GHS
    pay = fees.record_payment(school_id, invoice_id, amount_ghs,
                              method='paystack', reference=reference)
    db.session.commit()
    return pay


def _to_dec(v):
    from decimal import Decimal
    return Decimal(str(v))


def _activate_subscription(payment):
    plan = db.session.get(Plan, payment.plan_id)
    days = _cycle_days(plan.billing_cycle if plan else 'monthly')
    today = date.today()
    sub = Subscription(
        school_id=payment.school_id, plan_id=payment.plan_id,
        starts_on=today, ends_on=today + timedelta(days=days),
        status='active', paystack_ref=payment.reference)
    db.session.add(sub)
    # A paid school should be active (lift trial/suspension on payment).
    school = db.session.get(School, payment.school_id)
    if school is not None and school.status != SchoolStatus.active:
        school.status = SchoolStatus.active
    db.session.flush()
