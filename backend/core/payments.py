"""HitPay online payments for facility bookings and season parking (each condominium uses its own HitPay account).

Flow: the booking creates a HitPay payment request and the resident pays on HitPay's page (PayNow,
cards…). HitPay then redirects back to ``/v1/payments/hitpay/return/`` and calls the webhook. Neither
is trusted on its own: both only prompt us to read the payment request's status from HitPay's API,
which is what confirms the booking.
"""
import hashlib
import hmac
import logging

import requests

log = logging.getLogger(__name__)

LIVE = "https://api.hit-pay.com/v1"
SANDBOX = "https://api.sandbox.hit-pay.com/v1"
TIMEOUT = 15


class PaymentError(Exception):
    pass


def _base(settings):
    return SANDBOX if settings.sandbox else LIVE


def _headers(settings):
    return {"X-BUSINESS-API-KEY": settings.hitpay_api_key, "X-Requested-With": "XMLHttpRequest"}


def create_request(settings, *, amount, currency, reference, purpose, user, redirect_url, webhook_url):
    """Create a HitPay payment request; returns (payment request id, checkout url). ``reference`` is ours
    (``booking-12``, ``parking-3``) and comes back in the webhook."""
    data = {
        "amount": f"{amount:.2f}",
        "currency": currency,
        "reference_number": reference,
        "purpose": purpose[:255],
        "redirect_url": redirect_url,
        "webhook": webhook_url,
        "name": (user.get_full_name() or user.get_username()) if user else "",
        "email": user.email if user and user.email else "",
        "allow_repeated_payments": "false",
    }
    try:
        response = requests.post(f"{_base(settings)}/payment-requests", data={k: v for k, v in data.items() if v},
                                 headers=_headers(settings), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise PaymentError(f"Could not reach HitPay: {exc}") from exc
    if response.status_code >= 400:
        log.warning("HitPay refused payment request %s: %s %s", reference, response.status_code, response.text[:500])
        raise PaymentError("The payment provider refused the request. Please contact the management office.")
    body = response.json()
    return body["id"], body["url"]


def fetch_status(settings, request_id):
    """HitPay's status of a payment request: ``pending``, ``completed``, ``failed``, ``expired``… ('' if unknown)."""
    try:
        response = requests.get(f"{_base(settings)}/payment-requests/{request_id}", headers=_headers(settings), timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("HitPay status check failed for %s: %s", request_id, exc)
        return ""
    if response.status_code >= 400:
        log.warning("HitPay status check for %s answered %s", request_id, response.status_code)
        return ""
    return str(response.json().get("status", "")).lower()


def valid_form_webhook(settings, data):
    """HitPay's payment-request webhook (form fields + ``hmac``): HMAC-SHA256 of the sorted key+value pairs."""
    fields = {k: v for k, v in data.items() if k != "hmac"}
    signature = data.get("hmac", "")
    if not settings.hitpay_salt or not signature:
        return False
    message = "".join(f"{k}{fields[k]}" for k in sorted(fields))
    expected = hmac.new(settings.hitpay_salt.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def valid_json_webhook(settings, raw_body, signature):
    """HitPay's event webhook (JSON body, ``Hitpay-Signature`` header): HMAC-SHA256 of the raw body."""
    if not settings.hitpay_salt or not signature:
        return False
    expected = hmac.new(settings.hitpay_salt.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
