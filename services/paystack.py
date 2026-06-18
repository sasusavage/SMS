"""
Paystack helpers for subscription billing — one robust path for initialize /
verify / webhook-signature so every caller behaves the same and failures are
visible, not swallowed. Mirrors the proven slidein pattern (retries with
backoff, correct pesewas rounding, exact error logging, amount verification).

Keys come from config (PAYSTACK_SECRET_KEY), set via env in Coolify.
"""
import hmac
import hashlib
import logging
import time
from decimal import Decimal, ROUND_HALF_UP

import requests
from flask import current_app

log = logging.getLogger(__name__)

_INIT_URL = 'https://api.paystack.co/transaction/initialize'
_VERIFY_URL = 'https://api.paystack.co/transaction/verify/{ref}'
_TIMEOUT = 15
_RETRIES = 2  # total attempts = _RETRIES + 1


def secret_key():
    return (current_app.config.get('PAYSTACK_SECRET_KEY') or '').strip()


def is_configured():
    return bool(secret_key())


def to_pesewas(amount):
    """GHS (float/Decimal) -> integer pesewas, rounded correctly."""
    cents = (Decimal(str(amount)) * 100).quantize(Decimal('1'),
                                                   rounding=ROUND_HALF_UP)
    return int(cents)


def initialize(*, amount, email, reference, callback_url, metadata=None):
    """
    Initialize a transaction. Returns:
      {'ok': True, 'url': <authorization_url>, 'reference': ref}
      {'ok': False, 'error': str, 'code': 'config|http|network|no_url'}
    """
    secret = secret_key()
    if not secret:
        log.error('paystack.initialize: PAYSTACK_SECRET_KEY not set')
        return {'ok': False, 'error': 'Billing is not configured.', 'code': 'config'}

    payload = {
        'email': email,
        'amount': to_pesewas(amount),
        'reference': reference,
        'currency': 'GHS',
        'callback_url': callback_url,
        'metadata': metadata or {},
    }
    headers = {'Authorization': f'Bearer {secret}',
               'Content-Type': 'application/json'}
    last_err = ''
    for attempt in range(_RETRIES + 1):
        try:
            r = requests.post(_INIT_URL, json=payload, headers=headers,
                              timeout=_TIMEOUT)
            if r.status_code == 200:
                url = ((r.json() or {}).get('data') or {}).get('authorization_url')
                if url:
                    return {'ok': True, 'url': url, 'reference': reference}
                return {'ok': False, 'error': 'Paystack returned no link.',
                        'code': 'no_url'}
            msg = _msg(r)
            last_err = f'HTTP {r.status_code}: {msg}'
            log.error('paystack.initialize failed (try %d) ref=%s — %s',
                      attempt + 1, reference, last_err)
            if 400 <= r.status_code < 500:
                return {'ok': False, 'error': msg, 'code': 'http'}
        except requests.RequestException as e:
            last_err = str(e)
            log.warning('paystack.initialize network error (try %d) — %s',
                        attempt + 1, e)
        if attempt < _RETRIES:
            time.sleep(1.5 * (attempt + 1))
    return {'ok': False, 'error': last_err or 'Network error', 'code': 'network'}


def verify(reference):
    """
    Verify a transaction. Returns:
      {'ok': True, 'status': 'success'|..., 'amount': <pesewas>, 'raw': {...}}
      {'ok': False, 'error': str, 'code': '...'}
    """
    secret = secret_key()
    if not secret:
        return {'ok': False, 'error': 'Billing is not configured.', 'code': 'config'}
    headers = {'Authorization': f'Bearer {secret}'}
    last_err = ''
    for attempt in range(_RETRIES + 1):
        try:
            r = requests.get(_VERIFY_URL.format(ref=reference), headers=headers,
                             timeout=_TIMEOUT)
            if r.status_code == 200:
                data = (r.json() or {}).get('data') or {}
                return {'ok': True, 'status': data.get('status'),
                        'amount': data.get('amount'), 'raw': data}
            msg = _msg(r)
            last_err = f'HTTP {r.status_code}: {msg}'
            log.error('paystack.verify failed (try %d) ref=%s — %s',
                      attempt + 1, reference, last_err)
            if 400 <= r.status_code < 500:
                return {'ok': False, 'error': msg, 'code': 'http'}
        except requests.RequestException as e:
            last_err = str(e)
            log.warning('paystack.verify network error (try %d) — %s',
                        attempt + 1, e)
        if attempt < _RETRIES:
            time.sleep(1.5 * (attempt + 1))
    return {'ok': False, 'error': last_err or 'Network error', 'code': 'network'}


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Paystack signs the webhook body with HMAC-SHA512 of the secret key."""
    secret = secret_key()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode('utf-8'), raw_body,
                        hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def _msg(resp):
    try:
        return (resp.json() or {}).get('message', resp.text[:200])
    except Exception:
        return resp.text[:200]
