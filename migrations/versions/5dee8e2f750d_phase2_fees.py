"""Phase 2: fee invoicing tables.

Adds fee_structures, invoices, invoice_items, fee_payments. Hand-written +
inspector-guarded (initial Phase 1 migration uses create_all).

Revision ID: 5dee8e2f750d
Revises: 0caea30ccb02
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa


revision = '5dee8e2f750d'
down_revision = '0caea30ccb02'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if 'fee_structures' not in existing:
        op.create_table(
            'fee_structures',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(),
                      sa.ForeignKey('schools.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.Column('level_id', sa.Integer(),
                      sa.ForeignKey('levels.id', ondelete='CASCADE')),
            sa.Column('term_id', sa.Integer(),
                      sa.ForeignKey('terms.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False,
                      server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.UniqueConstraint('school_id', 'level_id', 'term_id', 'name',
                                name='uq_fee_structure'),
        )
        op.create_index('ix_fee_structures_school_id', 'fee_structures',
                        ['school_id'])
        op.create_index('ix_fee_structures_term_id', 'fee_structures',
                        ['term_id'])
        op.create_index('ix_fee_structures_level_id', 'fee_structures',
                        ['level_id'])

    if 'invoices' not in existing:
        op.create_table(
            'invoices',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(),
                      sa.ForeignKey('schools.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('student_id', sa.Integer(),
                      sa.ForeignKey('students.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('term_id', sa.Integer(),
                      sa.ForeignKey('terms.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('total_amount', sa.Numeric(10, 2), nullable=False,
                      server_default='0'),
            sa.Column('status', sa.String(length=20), nullable=False,
                      server_default='unpaid'),
            sa.Column('note', sa.Text()),
            sa.UniqueConstraint('school_id', 'student_id', 'term_id',
                                name='uq_invoice_student_term'),
        )
        op.create_index('ix_invoices_school_id', 'invoices', ['school_id'])
        op.create_index('ix_invoices_student_id', 'invoices', ['student_id'])
        op.create_index('ix_invoices_term_id', 'invoices', ['term_id'])
        op.create_index('ix_invoices_status', 'invoices', ['status'])

    if 'invoice_items' not in existing:
        op.create_table(
            'invoice_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(),
                      sa.ForeignKey('schools.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('invoice_id', sa.Integer(),
                      sa.ForeignKey('invoices.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('description', sa.String(length=255), nullable=False),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False,
                      server_default='0'),
        )
        op.create_index('ix_invoice_items_school_id', 'invoice_items',
                        ['school_id'])
        op.create_index('ix_invoice_items_invoice_id', 'invoice_items',
                        ['invoice_id'])

    if 'fee_payments' not in existing:
        op.create_table(
            'fee_payments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(),
                      sa.ForeignKey('schools.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('invoice_id', sa.Integer(),
                      sa.ForeignKey('invoices.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('method', sa.String(length=20), nullable=False,
                      server_default='cash'),
            sa.Column('reference', sa.String(length=100)),
            sa.Column('recorded_by', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_fee_payments_school_id', 'fee_payments',
                        ['school_id'])
        op.create_index('ix_fee_payments_invoice_id', 'fee_payments',
                        ['invoice_id'])
        op.create_index('ix_fee_payments_reference', 'fee_payments',
                        ['reference'])


def downgrade():
    op.drop_table('fee_payments')
    op.drop_table('invoice_items')
    op.drop_table('invoices')
    op.drop_table('fee_structures')
