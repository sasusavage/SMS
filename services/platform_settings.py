"""
Typed accessors for PlatformSetting (super-admin key/value store).

Secret values are transparently encrypted/decrypted via secrets_box. Keys used:
  smtp_host, smtp_port, smtp_use_tls, smtp_username, smtp_from_email,
  smtp_from_name              -> plaintext
  smtp_password               -> secret
  vynfy_base_url, vynfy_sender_id -> plaintext
  vynfy_api_key               -> secret
"""
from extensions import db
from models.notifications import PlatformSetting
from services import secrets_box

SECRET_KEYS = {'smtp_password', 'vynfy_api_key'}


def get(key, default=None):
    row = PlatformSetting.query.filter_by(key=key).first()
    if row is None:
        return default
    if key in SECRET_KEYS:
        return secrets_box.decrypt(row.value_enc) or default
    return row.value if row.value is not None else default


def set(key, value):
    row = PlatformSetting.query.filter_by(key=key).first()
    if row is None:
        row = PlatformSetting(key=key)
        db.session.add(row)
    if key in SECRET_KEYS:
        # Empty value clears the secret; otherwise (re)encrypt.
        row.value_enc = secrets_box.encrypt(value) if value else None
    else:
        row.value = value
    db.session.flush()
    return row


def get_all_plain():
    """Non-secret settings as a dict for rendering forms (secrets excluded)."""
    out = {}
    for row in PlatformSetting.query.all():
        if row.key not in SECRET_KEYS:
            out[row.key] = row.value
    return out


def has_secret(key):
    """True if a secret is set (without revealing it)."""
    row = PlatformSetting.query.filter_by(key=key).first()
    return bool(row and row.value_enc)
