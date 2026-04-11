"""Add totp fields to users

Revision ID: df3e0bddcaab
Revises:
Create Date: 2026-04-11 04:58:07.219053

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df3e0bddcaab'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('totp_secret', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('totp_enabled', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('totp_enabled')
        batch_op.drop_column('totp_secret')
