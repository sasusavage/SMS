"""
Reusable column mixins.

TenantMixin — every tenant-owned table includes school_id (FK, indexed,
NOT NULL). This is the multi-tenancy discriminator. The TenantQueryMixin that
auto-filters by g.current_school_id lives in services/tenant.py; this mixin
only declares the column so models stay free of query concerns.
"""
from datetime import datetime, timezone

from sqlalchemy import ForeignKey
from sqlalchemy.orm import declared_attr, mapped_column

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds created_at (UTC)."""

    @declared_attr
    def created_at(cls):
        return mapped_column(db.DateTime(timezone=True), default=utcnow,
                             nullable=False)


class TenantMixin:
    """
    Adds school_id FK -> schools.id, indexed and NOT NULL.

    Using declared_attr so each subclass gets its own column definition while
    sharing the FK target and index requirement.
    """

    @declared_attr
    def school_id(cls):
        return mapped_column(
            db.Integer,
            ForeignKey('schools.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        )
