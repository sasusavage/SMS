"""
Symmetric encryption for secrets stored at rest (SMTP passwords, API keys).

Uses Fernet with a key derived from ENCRYPTION_KEY if set, otherwise from
SECRET_KEY. Storing third-party credentials in plaintext would be a real
liability, so anything sensitive goes through here before hitting the DB.

NOTE: the derivation is deterministic from the configured key — rotating
SECRET_KEY/ENCRYPTION_KEY will invalidate previously-encrypted values, which is
the correct security behaviour (re-enter the credentials after a key rotation).
"""
import base64
import hashlib

from flask import current_app
from cryptography.fernet import Fernet, InvalidToken


def _fernet():
    key_material = (current_app.config.get('ENCRYPTION_KEY')
                    or current_app.config.get('SECRET_KEY') or 'dev-secret')
    # Derive a stable 32-byte urlsafe key from the configured secret.
    digest = hashlib.sha256(key_material.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext):
    """Return an encrypted token (str) for a plaintext secret, or None."""
    if plaintext in (None, ''):
        return None
    return _fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt(token):
    """Return the plaintext for a stored token, or None if missing/invalid."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return None
