"""Phase 3: timetabling tables (periods, timetable_slots).

Hand-written + inspector-guarded (initial Phase 1 migration uses create_all).

Revision ID: a6f6d9ce44f5
Revises: 5dee8e2f750d
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa


revision = 'a6f6d9ce44f5'
down_revision = '5dee8e2f750d'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if 'periods' not in existing:
        op.create_table(
            'periods',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(),
                      sa.ForeignKey('schools.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('name', sa.String(length=60), nullable=False),
            sa.Column('sequence', sa.Integer(), nullable=False,
                      server_default='0'),
            sa.Column('start_time', sa.Time()),
            sa.Column('end_time', sa.Time()),
            sa.UniqueConstraint('school_id', 'name', name='uq_period_name'),
        )
        op.create_index('ix_periods_school_id', 'periods', ['school_id'])

    if 'timetable_slots' not in existing:
        op.create_table(
            'timetable_slots',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(),
                      sa.ForeignKey('schools.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('class_id', sa.Integer(),
                      sa.ForeignKey('classes.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('day_of_week', sa.Integer(), nullable=False),
            sa.Column('period_id', sa.Integer(),
                      sa.ForeignKey('periods.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('subject_id', sa.Integer(),
                      sa.ForeignKey('subjects.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('teacher_user_id', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.UniqueConstraint('school_id', 'class_id', 'day_of_week',
                                'period_id', name='uq_timetable_cell'),
        )
        for col in ('school_id', 'class_id', 'period_id', 'subject_id',
                    'teacher_user_id'):
            op.create_index(f'ix_timetable_slots_{col}', 'timetable_slots', [col])


def downgrade():
    op.drop_table('timetable_slots')
    op.drop_table('periods')
