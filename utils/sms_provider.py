"""
SMS Provider Wrapper — Hubtel / Arkesel Ghanaian Gateway.

Usage:
    SMSProvider.send_sms(school_id, phone, message)

In development (no API key set) messages are printed to stdout.
"""
import os
import requests


class SMSProvider:
    """Class-based wrapper so callers can use SMSProvider.send_sms(...)."""

    @staticmethod
    def send_sms(school_id, phone, message):
        """
        Dispatches an SMS.  Falls back to console output when API key is absent.

        Args:
            school_id: Used to fetch per-school sender ID (future: per-tenant keys).
            phone:     Recipient phone number (Ghana format, e.g. 0244123456).
            message:   Plain-text SMS body (max ~160 chars for a single SMS).
        """
        api_key   = os.environ.get('ARKESEL_SMS_KEY') or os.environ.get('SMS_API_KEY')
        sender_id = os.environ.get('ARKESEL_SMS_SENDER_ID') or os.environ.get('SMS_SENDER_ID', 'SmartSch')

        if not api_key:
            # Development / test mode — print instead of calling the gateway
            print(f"[SMS DEV] → {phone} [{sender_id}] | {message}")
            return True

        try:
            url = (
                f"https://sms.arkesel.com/sms/api"
                f"?action=send-sms&api_key={api_key}"
                f"&to={phone}&from={sender_id}"
                f"&sms={requests.utils.quote(message)}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as exc:
            print(f"[SMS ERROR] Failed to send to {phone}: {exc}")
            return False


# ---------------------------------------------------------------------------
# Module-level shim so legacy callers (`from utils.sms_provider import send_sms`)
# continue to work without changes.
# ---------------------------------------------------------------------------
def send_sms(phone, message, school_id=None):
    return SMSProvider.send_sms(school_id, phone, message)
