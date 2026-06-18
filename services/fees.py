"""
Fee invoicing service — fee structures, invoice generation, payments, balances.

Tenant-scoped (explicit school_id). Balance is always derived from payments
(total_amount - sum(payments)); invoice.status is a cached convenience flag
recomputed whenever payments change.
"""
from decimal import Decimal

from extensions import db
from models.fees import FeeStructure, Invoice, InvoiceItem, FeePayment
from models.operational import Student
from models.config_tables import Level, Term, Class

ZERO = Decimal('0')


class FeeError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _dec(v):
    try:
        return Decimal(str(v))
    except Exception:
        raise FeeError(f'Invalid amount: {v!r}.')


# ---------------------------------------------------------------------------
# Fee structures
# ---------------------------------------------------------------------------
def create_fee_structure(school_id, *, name, term_id, amount, level_id=None):
    name = (name or '').strip()
    if not name:
        raise FeeError('Fee name is required.')
    if Term.query.filter_by(school_id=school_id, id=term_id).first() is None:
        raise FeeError('Term not found.')
    if level_id and Level.query.filter_by(school_id=school_id,
                                          id=level_id).first() is None:
        raise FeeError('Level not found.')
    amt = _dec(amount)
    if amt < ZERO:
        raise FeeError('Amount cannot be negative.')
    fs = FeeStructure(school_id=school_id, name=name, term_id=term_id,
                      level_id=level_id, amount=amt, is_active=True)
    db.session.add(fs)
    db.session.flush()
    return fs


def delete_fee_structure(school_id, fee_id):
    fs = FeeStructure.query.filter_by(school_id=school_id, id=fee_id).first()
    if fs is None:
        raise FeeError('Fee structure not found.')
    db.session.delete(fs)
    db.session.flush()


def fee_structures_for_class(school_id, klass, term_id):
    """Active fee structures that apply to a class's level for a term
    (level-specific + 'all levels' where level_id is null)."""
    return FeeStructure.query.filter(
        FeeStructure.school_id == school_id,
        FeeStructure.term_id == term_id,
        FeeStructure.is_active.is_(True),
        db.or_(FeeStructure.level_id == klass.level_id,
               FeeStructure.level_id.is_(None)),
    ).all()


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------
def generate_invoices(school_id, class_id, term_id):
    """
    Create one invoice per student in the class for the term, with line items
    from the applicable fee structures. Skips students who already have an
    invoice for that term (idempotent). Returns {'created': n, 'skipped': n}.
    """
    klass = Class.query.filter_by(school_id=school_id, id=class_id).first()
    if klass is None:
        raise FeeError('Class not found.')
    if Term.query.filter_by(school_id=school_id, id=term_id).first() is None:
        raise FeeError('Term not found.')

    structures = fee_structures_for_class(school_id, klass, term_id)
    if not structures:
        raise FeeError('No fee structures defined for this class/term yet.')

    students = Student.query.filter_by(
        school_id=school_id, current_class_id=class_id).all()
    existing = {
        sid for (sid,) in Invoice.query
        .with_entities(Invoice.student_id)
        .filter_by(school_id=school_id, term_id=term_id).all()
    }

    created = skipped = 0
    for st in students:
        if st.id in existing:
            skipped += 1
            continue
        total = sum((Decimal(str(s.amount)) for s in structures), ZERO)
        inv = Invoice(school_id=school_id, student_id=st.id, term_id=term_id,
                      total_amount=total, status='unpaid')
        db.session.add(inv)
        db.session.flush()
        for s in structures:
            db.session.add(InvoiceItem(
                school_id=school_id, invoice_id=inv.id,
                description=s.name, amount=Decimal(str(s.amount))))
        created += 1
    db.session.flush()
    return {'created': created, 'skipped': skipped}


# ---------------------------------------------------------------------------
# Payments + balance
# ---------------------------------------------------------------------------
def amount_paid(school_id, invoice_id):
    rows = FeePayment.query.filter_by(
        school_id=school_id, invoice_id=invoice_id).all()
    return sum((Decimal(str(p.amount)) for p in rows), ZERO)


def balance(school_id, invoice):
    return Decimal(str(invoice.total_amount)) - amount_paid(school_id, invoice.id)


def _recompute_status(school_id, invoice):
    paid = amount_paid(school_id, invoice.id)
    total = Decimal(str(invoice.total_amount))
    if paid <= ZERO:
        invoice.status = 'unpaid'
    elif paid < total:
        invoice.status = 'partial'
    else:
        invoice.status = 'paid'
    db.session.flush()
    return invoice.status


def record_payment(school_id, invoice_id, amount, *, method='cash',
                   reference=None, recorded_by=None):
    invoice = Invoice.query.filter_by(school_id=school_id, id=invoice_id).first()
    if invoice is None:
        raise FeeError('Invoice not found.')
    amt = _dec(amount)
    if amt <= ZERO:
        raise FeeError('Payment amount must be positive.')
    # Idempotency for online payments: skip if this reference already recorded.
    if reference:
        dup = FeePayment.query.filter_by(
            school_id=school_id, reference=reference).first()
        if dup is not None:
            return dup
    pay = FeePayment(school_id=school_id, invoice_id=invoice_id, amount=amt,
                     method=method, reference=reference, recorded_by=recorded_by)
    db.session.add(pay)
    db.session.flush()
    _recompute_status(school_id, invoice)
    return pay


def get_invoice(school_id, invoice_id):
    inv = Invoice.query.filter_by(school_id=school_id, id=invoice_id).first()
    if inv is None:
        raise FeeError('Invoice not found.')
    return inv


def student_invoices(school_id, student_id):
    return (Invoice.query.filter_by(school_id=school_id, student_id=student_id)
            .order_by(Invoice.id.desc()).all())
