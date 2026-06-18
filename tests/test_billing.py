"""Phase 2 tests: Paystack billing — service, activation, webhook, routes."""
import hmac
import hashlib
import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from services import billing, paystack
from services.billing import BillingError
from models.platform import Plan, Payment, Subscription, School
from models.enums import UserRole, SchoolStatus
from tests.factories import make_school, make_user


def _plan(db, name='Pro', price=400, cycle='monthly'):
    p = Plan(name=name, price_ghs=price, billing_cycle=cycle)
    db.session.add(p)
    db.session.flush()
    return p


# --- paystack helpers -------------------------------------------------------
def test_to_pesewas_rounding(app):
    assert paystack.to_pesewas(400) == 40000
    assert paystack.to_pesewas(Decimal('19.99')) == 1999
    assert paystack.to_pesewas('0.1') == 10


def test_webhook_signature(app):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test_xyz'
    with app.test_request_context():
        body = b'{"event":"charge.success"}'
        sig = hmac.new(b'sk_test_xyz', body, hashlib.sha512).hexdigest()
        assert paystack.verify_webhook_signature(body, sig) is True
        assert paystack.verify_webhook_signature(body, 'bad') is False
        assert paystack.verify_webhook_signature(body, '') is False


def test_is_configured(app):
    app.config['PAYSTACK_SECRET_KEY'] = ''
    with app.test_request_context():
        assert paystack.is_configured() is False
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    with app.test_request_context():
        assert paystack.is_configured() is True


# --- start_checkout ---------------------------------------------------------
def test_start_checkout_creates_pending_payment(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')
    p = _plan(db)
    db.session.commit()
    with patch('services.paystack.initialize',
               return_value={'ok': True, 'url': 'https://pay/x', 'reference': 'R'}):
        out = billing.start_checkout(s.id, p.id, 'a@s.test', 'http://cb')
    db.session.commit()
    assert out['url'] == 'https://pay/x'
    pay = Payment.query.filter_by(school_id=s.id).first()
    assert pay.status == 'pending' and pay.amount_pesewas == 40000


def test_start_checkout_unconfigured_raises(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = ''
    s = make_school(db, slug='s')
    p = _plan(db)
    db.session.commit()
    with pytest.raises(BillingError, match='not configured'):
        billing.start_checkout(s.id, p.id, 'a@s.test', 'http://cb')


def test_start_checkout_init_failure_marks_failed(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')
    p = _plan(db)
    db.session.commit()
    with patch('services.paystack.initialize',
               return_value={'ok': False, 'error': 'bad key', 'code': 'http'}):
        with pytest.raises(BillingError, match='bad key'):
            billing.start_checkout(s.id, p.id, 'a@s.test', 'http://cb')
    assert Payment.query.filter_by(school_id=s.id).first().status == 'failed'


# --- complete_payment (activation) ------------------------------------------
def _pending_payment(db, school, plan):
    pay = Payment(school_id=school.id, plan_id=plan.id, reference='REF1',
                  amount_pesewas=40000, currency='GHS', status='pending')
    db.session.add(pay)
    db.session.flush()
    return pay


def test_complete_payment_success_activates(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')
    p = _plan(db)
    _pending_payment(db, s, p)
    db.session.commit()
    with patch('services.paystack.verify',
               return_value={'ok': True, 'status': 'success', 'amount': 40000}):
        pay = billing.complete_payment('REF1')
    db.session.commit()
    assert pay.status == 'success' and pay.activated is True
    assert Subscription.query.filter_by(school_id=s.id, status='active').count() == 1


def test_complete_payment_idempotent(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')
    p = _plan(db)
    _pending_payment(db, s, p)
    db.session.commit()
    with patch('services.paystack.verify',
               return_value={'ok': True, 'status': 'success', 'amount': 40000}):
        billing.complete_payment('REF1')
        billing.complete_payment('REF1')  # second call must not double-activate
    db.session.commit()
    assert Subscription.query.filter_by(school_id=s.id).count() == 1


def test_complete_payment_amount_mismatch_rejected(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')
    p = _plan(db)
    _pending_payment(db, s, p)
    db.session.commit()
    with patch('services.paystack.verify',
               return_value={'ok': True, 'status': 'success', 'amount': 100}):  # underpaid
        pay = billing.complete_payment('REF1')
    db.session.commit()
    assert pay.status == 'failed' and pay.paystack_status == 'amount_mismatch'
    assert Subscription.query.filter_by(school_id=s.id).count() == 0


def test_complete_payment_activates_school(app, db):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')   # trial by default
    p = _plan(db)
    _pending_payment(db, s, p)
    db.session.commit()
    with patch('services.paystack.verify',
               return_value={'ok': True, 'status': 'success', 'amount': 40000}):
        billing.complete_payment('REF1')
    db.session.commit()
    assert db.session.get(School, s.id).status == SchoolStatus.active


# --- Routes -----------------------------------------------------------------
def _login(client, slug, email):
    return client.post('/auth/login', data={'school_slug': slug,
                                            'email': email, 'password': 'pw'})


def test_billing_page_admin_only(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    make_user(db, s, email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get('/admin/billing').status_code == 403
    client.post('/auth/logout')
    _login(client, 's', 'a@s.test')
    assert client.get('/admin/billing').status_code == 200


def test_webhook_rejects_bad_signature(app, db, client):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    r = client.post('/billing/webhook', data=b'{}',
                    headers={'x-paystack-signature': 'wrong'},
                    content_type='application/json')
    assert r.status_code == 400


def test_webhook_accepts_valid_signature(app, db, client):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s = make_school(db, slug='s')
    p = _plan(db)
    _pending_payment(db, s, p)
    db.session.commit()
    body = json.dumps({'event': 'charge.success',
                       'data': {'reference': 'REF1'}}).encode()
    sig = hmac.new(b'sk_test', body, hashlib.sha512).hexdigest()
    with patch('services.paystack.verify',
               return_value={'ok': True, 'status': 'success', 'amount': 40000}):
        r = client.post('/billing/webhook', data=body,
                        headers={'x-paystack-signature': sig},
                        content_type='application/json')
    assert r.status_code == 200
    assert Subscription.query.filter_by(school_id=s.id, status='active').count() == 1
