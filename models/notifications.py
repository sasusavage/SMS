"""
Notification settings + log models (Phase 2).

SchoolNotificationSettings — per-school outbound channels (SMTP email + an
optional SMS sender ID), tenant-owned, so each school emails from its own
mailbox. PlatformSetting — key/value store the super admin owns for
platform-level config (the platform's own SMTP used for signup/billing email,
and the Vynfy bridge URL + API key shared by all tenants).

NotificationLog — records every send (channel/recipient/message/provider/
status) so admins can see exactly what went out (mirrors the slidein pattern).

Secret fields (SMTP/API passwords) are stored ENCRYPTED via
services.secrets_box; *_enc columns hold ciphertext, never plaintext.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Boolean, Text, DateTime, UniqueConstraint, ForeignKey,
)
from sqlalchemy.orm import mapped_column

from extensions import db
from models.mixins import TenantMixin, TimestampMixin


class SchoolNotificationSettings(db.Model, TenantMixin, TimestampMixin):
    """Per-school outbound email (SMTP) + SMS sender. One row per school."""
    __tablename__ = 'school_notification_settings'
    __table_args__ = (
        UniqueConstraint('school_id', name='uq_notif_settings_school'),
    )

    id = mapped_column(Integer, primary_key=True)

    # --- Email (SMTP) ---
    smtp_enabled = mapped_column(Boolean, default=False, nullable=False)
    smtp_host = mapped_column(String(255))
    smtp_port = mapped_column(Integer, default=587)
    smtp_use_tls = mapped_column(Boolean, default=True, nullable=False)
    smtp_username = mapped_column(String(255))
    smtp_password_enc = mapped_column(Text)        # encrypted at rest
    smtp_from_email = mapped_column(String(255))
    smtp_from_name = mapped_column(String(255))

    # --- SMS (Vynfy) ---
    sms_enabled = mapped_column(Boolean, default=False, nullable=False)
    sms_sender_id = mapped_column(String(11))       # Vynfy sender IDs max 11 chars


class PlatformSetting(db.Model, TimestampMixin):
    """
    Key/value platform-level settings (NOT tenant-scoped), owned by the super
    admin: platform SMTP (fallback for schools + platform email) and the Vynfy
    bridge URL/API key shared by all tenants. Secret values -> value_enc.
    """
    __tablename__ = 'platform_settings'

    id = mapped_column(Integer, primary_key=True)
    key = mapped_column(String(100), nullable=False, unique=True, index=True)
    value = mapped_column(Text)        # plaintext (non-secret)
    value_enc = mapped_column(Text)    # encrypted (secret)


class NotificationLog(db.Model):
    """
    Record of every notification send. school_id nullable for platform-level
    sends. status: queued | sent | failed | logged (logged = no provider
    configured, so it was only recorded, not actually delivered).
    """
    __tablename__ = 'notification_logs'

    id = mapped_column(Integer, primary_key=True)
    school_id = mapped_column(
        Integer, ForeignKey('schools.id', ondelete='SET NULL'),
        nullable=True, index=True)
    channel = mapped_column(String(20), nullable=False)   # 'email' | 'sms'
    recipient = mapped_column(String(255), nullable=False)
    subject = mapped_column(String(255))
    message = mapped_column(Text)
    provider = mapped_column(String(40))
    provider_message_id = mapped_column(String(120))
    status = mapped_column(String(20), default='queued', nullable=False,
                           index=True)
    error = mapped_column(Text)
    created_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
