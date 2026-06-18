"""
Fee invoicing models (Phase 2) — parents/students paying schools.

Distinct from subscription billing (schools paying the platform). All
tenant-owned. Configuration-over-code: fee amounts are data per school/level/
term, never hardcoded.

  FeeStructure  — a named fee for a level + term (e.g. Tuition, Basic 1, Term 1).
  Invoice       — issued to a student for a term; total + status.
  InvoiceItem   — line items on an invoice (from fee structures or ad-hoc).
  FeePayment    — a payment against an invoice (manual or Paystack); supports
                  partial payments, so balance = total - sum(payments).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Text, Numeric, Boolean, DateTime, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import mapped_column, relationship

from extensions import db
from models.mixins import TenantMixin, TimestampMixin, utcnow


class FeeStructure(db.Model, TenantMixin, TimestampMixin):
    """A reusable fee definition for a level + term."""
    __tablename__ = 'fee_structures'
    __table_args__ = (
        UniqueConstraint('school_id', 'level_id', 'term_id', 'name',
                         name='uq_fee_structure'),
    )

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(120), nullable=False)        # "Tuition"
    level_id = mapped_column(
        Integer, ForeignKey('levels.id', ondelete='CASCADE'),
        nullable=True, index=True)                            # null = all levels
    term_id = mapped_column(
        Integer, ForeignKey('terms.id', ondelete='CASCADE'),
        nullable=False, index=True)
    amount = mapped_column(Numeric(10, 2), nullable=False, default=0)
    is_active = mapped_column(Boolean, default=True, nullable=False)

    level = relationship('Level', foreign_keys=[level_id])
    term = relationship('Term', foreign_keys=[term_id])


class Invoice(db.Model, TenantMixin, TimestampMixin):
    """A bill issued to a student for a term."""
    __tablename__ = 'invoices'
    __table_args__ = (
        UniqueConstraint('school_id', 'student_id', 'term_id',
                         name='uq_invoice_student_term'),
    )

    id = mapped_column(Integer, primary_key=True)
    student_id = mapped_column(
        Integer, ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False, index=True)
    term_id = mapped_column(
        Integer, ForeignKey('terms.id', ondelete='CASCADE'),
        nullable=False, index=True)
    total_amount = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # status: unpaid | partial | paid (derived from payments; cached here)
    status = mapped_column(String(20), default='unpaid', nullable=False,
                           index=True)
    note = mapped_column(Text)

    student = relationship('Student', foreign_keys=[student_id])
    term = relationship('Term', foreign_keys=[term_id])
    items = relationship('InvoiceItem', back_populates='invoice',
                         cascade='all, delete-orphan')
    payments = relationship('FeePayment', back_populates='invoice',
                            cascade='all, delete-orphan')


class InvoiceItem(db.Model, TenantMixin):
    """A line on an invoice."""
    __tablename__ = 'invoice_items'

    id = mapped_column(Integer, primary_key=True)
    invoice_id = mapped_column(
        Integer, ForeignKey('invoices.id', ondelete='CASCADE'),
        nullable=False, index=True)
    description = mapped_column(String(255), nullable=False)
    amount = mapped_column(Numeric(10, 2), nullable=False, default=0)

    invoice = relationship('Invoice', back_populates='items')


class FeePayment(db.Model, TenantMixin):
    """A payment against an invoice. method: cash | momo | paystack | other."""
    __tablename__ = 'fee_payments'

    id = mapped_column(Integer, primary_key=True)
    invoice_id = mapped_column(
        Integer, ForeignKey('invoices.id', ondelete='CASCADE'),
        nullable=False, index=True)
    amount = mapped_column(Numeric(10, 2), nullable=False)
    method = mapped_column(String(20), default='cash', nullable=False)
    reference = mapped_column(String(100), index=True)  # Paystack ref if online
    recorded_by = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow,
                               nullable=False)

    invoice = relationship('Invoice', back_populates='payments')
