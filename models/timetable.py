"""
Timetabling models (Phase 3). Tenant-owned, configuration-over-code: periods
(time slots) are defined per school, not hardcoded.

  Period        — a named time slot (e.g. "Period 1", 08:00-08:40), ordered.
  TimetableSlot — for a class on a weekday + period: which subject, which teacher.
                  Uniqueness: one slot per (class, day, period). Conflict checks
                  (teacher/class double-booking) live in the service layer.
"""
from sqlalchemy import (
    Integer, String, Time, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import mapped_column, relationship

from extensions import db
from models.mixins import TenantMixin, TimestampMixin


class Period(db.Model, TenantMixin, TimestampMixin):
    __tablename__ = 'periods'
    __table_args__ = (
        UniqueConstraint('school_id', 'name', name='uq_period_name'),
    )

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(60), nullable=False)        # "Period 1"
    sequence = mapped_column(Integer, nullable=False, default=0)
    start_time = mapped_column(Time)
    end_time = mapped_column(Time)


class TimetableSlot(db.Model, TenantMixin, TimestampMixin):
    """A single cell of a class's weekly timetable."""
    __tablename__ = 'timetable_slots'
    __table_args__ = (
        UniqueConstraint('school_id', 'class_id', 'day_of_week', 'period_id',
                         name='uq_timetable_cell'),
    )

    id = mapped_column(Integer, primary_key=True)
    class_id = mapped_column(
        Integer, ForeignKey('classes.id', ondelete='CASCADE'),
        nullable=False, index=True)
    day_of_week = mapped_column(Integer, nullable=False)    # 0=Mon .. 4=Fri
    period_id = mapped_column(
        Integer, ForeignKey('periods.id', ondelete='CASCADE'),
        nullable=False, index=True)
    subject_id = mapped_column(
        Integer, ForeignKey('subjects.id', ondelete='CASCADE'),
        nullable=False, index=True)
    teacher_user_id = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True, index=True)

    klass = relationship('Class', foreign_keys=[class_id])
    period = relationship('Period', foreign_keys=[period_id])
    subject = relationship('Subject', foreign_keys=[subject_id])
    teacher = relationship('User', foreign_keys=[teacher_user_id])
