"""Phase 2 fee invoicing service tests."""
from decimal import Decimal

import pytest

from services import fees
from services.fees import FeeError
from models.fees import FeeStructure, Invoice, InvoiceItem, FeePayment
from tests.factories import make_school, make_student, make_class
from models.config_tables import Term, Level


def _setup(db, slug='s', n_students=2):
    s = make_school(db, slug=slug)
    klass = make_class(db, s, name='B1 A')  # creates level + ay
    level = Level.query.filter_by(school_id=s.id).first()
    term = Term.query.filter_by(school_id=s.id).first() or \
        Term(school_id=s.id, academic_year_id=klass.academic_year_id,
             name='T1', sequence=1)
    if term.id is None:
        db.session.add(term)
    db.session.flush()
    students = [make_student(db, s, admission_no=f'A{i}', current_class_id=klass.id)
                for i in range(n_students)]
    db.session.flush()
    return dict(school=s, klass=klass, level=level, term=term, students=students)


# --- Fee structures ---------------------------------------------------------
def test_create_fee_structure(app, db):
    ctx = _setup(db)
    fs = fees.create_fee_structure(ctx['school'].id, name='Tuition',
                                   term_id=ctx['term'].id, amount=500,
                                   level_id=ctx['level'].id)
    db.session.commit()
    assert fs.id and fs.amount == Decimal('500')


def test_create_fee_negative_rejected(app, db):
    ctx = _setup(db)
    with pytest.raises(FeeError, match='negative'):
        fees.create_fee_structure(ctx['school'].id, name='X',
                                  term_id=ctx['term'].id, amount=-5)


# --- Invoice generation -----------------------------------------------------
def test_generate_invoices(app, db):
    ctx = _setup(db, n_students=3)
    fees.create_fee_structure(ctx['school'].id, name='Tuition',
                              term_id=ctx['term'].id, amount=500,
                              level_id=ctx['level'].id)
    fees.create_fee_structure(ctx['school'].id, name='Books',
                              term_id=ctx['term'].id, amount=100, level_id=None)
    db.session.commit()
    out = fees.generate_invoices(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    assert out == {'created': 3, 'skipped': 0}
    inv = Invoice.query.filter_by(school_id=ctx['school'].id).first()
    assert inv.total_amount == Decimal('600')   # 500 + 100
    assert InvoiceItem.query.filter_by(invoice_id=inv.id).count() == 2


def test_generate_invoices_idempotent(app, db):
    ctx = _setup(db, n_students=2)
    fees.create_fee_structure(ctx['school'].id, name='Tuition',
                              term_id=ctx['term'].id, amount=500,
                              level_id=ctx['level'].id)
    db.session.commit()
    fees.generate_invoices(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    out = fees.generate_invoices(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    assert out == {'created': 0, 'skipped': 2}
    assert Invoice.query.filter_by(school_id=ctx['school'].id).count() == 2


def test_generate_no_structures_raises(app, db):
    ctx = _setup(db)
    db.session.commit()
    with pytest.raises(FeeError, match='No fee structures'):
        fees.generate_invoices(ctx['school'].id, ctx['klass'].id, ctx['term'].id)


# --- Payments + balance -----------------------------------------------------
def _one_invoice(db, ctx, amount=600):
    fees.create_fee_structure(ctx['school'].id, name='Tuition',
                              term_id=ctx['term'].id, amount=amount,
                              level_id=ctx['level'].id)
    db.session.commit()
    fees.generate_invoices(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    return Invoice.query.filter_by(school_id=ctx['school'].id).first()


def test_partial_then_full_payment(app, db):
    ctx = _setup(db, n_students=1)
    inv = _one_invoice(db, ctx, amount=600)
    fees.record_payment(ctx['school'].id, inv.id, 200, method='cash')
    db.session.commit()
    assert fees.balance(ctx['school'].id, inv) == Decimal('400')
    assert db.session.get(Invoice, inv.id).status == 'partial'
    fees.record_payment(ctx['school'].id, inv.id, 400, method='cash')
    db.session.commit()
    assert fees.balance(ctx['school'].id, inv) == Decimal('0')
    assert db.session.get(Invoice, inv.id).status == 'paid'


def test_payment_zero_rejected(app, db):
    ctx = _setup(db, n_students=1)
    inv = _one_invoice(db, ctx)
    with pytest.raises(FeeError, match='positive'):
        fees.record_payment(ctx['school'].id, inv.id, 0)


def test_payment_idempotent_by_reference(app, db):
    ctx = _setup(db, n_students=1)
    inv = _one_invoice(db, ctx, amount=600)
    fees.record_payment(ctx['school'].id, inv.id, 600, method='paystack',
                        reference='PSREF1')
    db.session.commit()
    # same reference again -> no double payment
    fees.record_payment(ctx['school'].id, inv.id, 600, method='paystack',
                        reference='PSREF1')
    db.session.commit()
    assert FeePayment.query.filter_by(invoice_id=inv.id).count() == 1


def test_cross_school_invoice_blocked(app, db):
    a = _setup(db, slug='a', n_students=1)
    b = _setup(db, slug='b', n_students=1)
    b_inv = _one_invoice(db, b)
    with pytest.raises(FeeError, match='Invoice not found'):
        fees.record_payment(a['school'].id, b_inv.id, 100)
