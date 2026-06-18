"""Phase 2: payments table (Paystack subscription transactions).

Adds the `payments` table. Hand-written + inspector-guarded for the same reason
as the notifications migration (initial Phase 1 migration uses create_all()).

Revision ID: 0caea30ccb02
Revises: ed1b8bd275c0
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa


revision = '0caea30ccb02'
down_revision = 'ed1b8bd275c0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'payments' in set(insp.get_table_names()):
        return
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(),
                  sa.ForeignKey('schools.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('plan_id', sa.Integer(),
                  sa.ForeignKey('plans.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=False),
        sa.Column('amount_pesewas', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=10)),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='pending'),
        sa.Column('activated', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('paystack_status', sa.String(length=40)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('reference', name='uq_payments_reference'),
    )
    op.create_index('ix_payments_school_id', 'payments', ['school_id'])
    op.create_index('ix_payments_reference', 'payments', ['reference'],
                    unique=True)
    op.create_index('ix_payments_status', 'payments', ['status'])


def downgrade():
    op.drop_index('ix_payments_status', table_name='payments')
    op.drop_index('ix_payments_reference', table_name='payments')
    op.drop_index('ix_payments_school_id', table_name='payments')
    op.drop_table('payments')
