"""
Platform tables — NOT tenant-owned (no school_id discriminator).

These describe the SaaS platform itself: the schools (tenants), the pricing
plans, their subscriptions, and the platform super admins.
"""
from sqlalchemy import (
    Integer, String, Text, Date, Numeric, Enum as SAEnum, ForeignKey,
)
from sqlalchemy.orm import mapped_column, relationship

from extensions import db
from models.enums import SchoolStatus
from models.mixins import TimestampMixin


class School(db.Model, TimestampMixin):
    """A tenant. Everything tenant-owned FKs back to here via school_id."""
    __tablename__ = 'schools'

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(255), nullable=False)
    slug = mapped_column(String(100), nullable=False, unique=True, index=True)
    country = mapped_column(String(100))
    address = mapped_column(Text)
    phone = mapped_column(String(50))
    email = mapped_column(String(255))
    logo_path = mapped_column(String(500))
    # Informational only — records which template seeded the school. The school
    # is free to diverge from it entirely afterwards.
    curriculum_template_used = mapped_column(String(100))
    status = mapped_column(
        SAEnum(SchoolStatus, name='school_status'),
        nullable=False, default=SchoolStatus.trial,
    )

    # Relationships
    subscriptions = relationship('Subscription', back_populates='school',
                                 cascade='all, delete-orphan')
    users = relationship('User', back_populates='school',
                         cascade='all, delete-orphan')

    def __repr__(self):
        return f'<School {self.slug}>'


class Plan(db.Model):
    """SaaS pricing plan. Seeded: Free Trial, Basic, Pro."""
    __tablename__ = 'plans'

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False, unique=True)
    price_ghs = mapped_column(Numeric(10, 2), nullable=False, default=0)
    max_students = mapped_column(Integer)  # null = unlimited
    billing_cycle = mapped_column(String(20), default='monthly')  # monthly/annual

    subscriptions = relationship('Subscription', back_populates='plan')

    def __repr__(self):
        return f'<Plan {self.name}>'


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = mapped_column(Integer, primary_key=True)
    school_id = mapped_column(
        Integer, ForeignKey('schools.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    plan_id = mapped_column(Integer, ForeignKey('plans.id'), nullable=False)
    starts_on = mapped_column(Date)
    ends_on = mapped_column(Date)
    status = mapped_column(String(20), default='active')  # active/expired/cancelled
    paystack_ref = mapped_column(String(255))

    school = relationship('School', back_populates='subscriptions')
    plan = relationship('Plan', back_populates='subscriptions')

    def __repr__(self):
        return f'<Subscription school={self.school_id} plan={self.plan_id}>'


class PlatformUser(db.Model, TimestampMixin):
    """Super admins only — the platform owner(s). No tenant scope."""
    __tablename__ = 'platform_users'

    id = mapped_column(Integer, primary_key=True)
    email = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash = mapped_column(String(255), nullable=False)
    name = mapped_column(String(255), nullable=False)
    is_active = mapped_column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f'<PlatformUser {self.email}>'
