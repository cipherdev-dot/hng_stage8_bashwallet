
import hashlib
import hmac
import logging

from app.core.config import settings


logger = logging.getLogger(__name__)


def verify_paystack_webhook_signature(request_body: bytes, signature_header: str) -> bool:
    """
    Verify Paystack webhook signature for security.

    Args:
        request_body: Raw request body bytes.
        signature_header: X-Paystack-Signature header value.

    Returns:
        bool: True if signature is valid.
    """
    if not settings.paystack_secret_key:
        logger.error("Paystack secret key not configured")
        return False

    # Create expected signature using HMAC SHA512
    expected_signature = hmac.new(
        settings.paystack_secret_key.encode('utf-8'),
        request_body,
        hashlib.sha512
    ).hexdigest()

    # Compare with provided signature 
    return hmac.compare_digest(expected_signature, signature_header)
