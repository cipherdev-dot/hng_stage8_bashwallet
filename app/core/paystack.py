
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class PaystackClient:
    """
    HTTP client wrapper for Paystack API integration.

    Handles authentication, rate limiting, error handling, and common Paystack operations.
    """

    def __init__(self):
        """Initialize Paystack client with base configuration."""
        self.base_url = settings.paystack_base_url
        self.secret_key = settings.paystack_secret_key
        self.public_key = settings.paystack_public_key

        # HTTP client configuration
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0, 
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle Paystack API response with error checking.

        Args:
            response: HTTP response from Paystack.

        Returns:
            Dict containing response data.

        Raises:
            Exception: If API returned error status.
        """
        try:
            data = response.json()
        except Exception:
            logger.error(f"Invalid JSON response from Paystack: {response.text}")
            raise Exception("Invalid response from Paystack API")

        if not response.is_success:
            error_msg = data.get("message", "Unknown Paystack error")
            logger.error(f"Paystack API error ({response.status_code}): {error_msg}")
            raise Exception(f"Paystack API error: {error_msg}")

        if not data.get("status", False):
            error_msg = data.get("message", "Paystack request failed")
            logger.error(f"Paystack request failed: {error_msg}")
            raise Exception(f"Paystack request failed: {error_msg}")

        return data

    async def post(self, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make POST request to Paystack API.

        Args:
            endpoint: API endpoint (without base URL).
            data: Request payload data.

        Returns:
            Dict: Response data from Paystack.
        """
        url = endpoint.lstrip('/')  
        logger.info(f"Making POST request to Paystack: {url}")

        try:
            response = await self.client.post(url, json=data or {})
            return self._handle_response(response)
        except httpx.TimeoutException:
            logger.error(f"Timeout making POST request to {url}")
            raise Exception("Paystack API request timed out")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error making POST request to {url}: {e}")
            raise Exception(f"Paystack HTTP error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error making POST request to {url}: {e}")
            raise

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make GET request to Paystack API.

        Args:
            endpoint: API endpoint (without base URL).
            params: Query parameters.

        Returns:
            Dict: Response data from Paystack.
        """
        url = endpoint.lstrip('/')
        logger.info(f"Making GET request to Paystack: {url}")

        try:
            response = await self.client.get(url, params=params or {})
            return self._handle_response(response)
        except httpx.TimeoutException:
            logger.error(f"Timeout making GET request to {url}")
            raise Exception("Paystack API request timed out")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error making GET request to {url}: {e}")
            raise Exception(f"Paystack HTTP error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error making GET request to {url}: {e}")
            raise

    async def initialize_transaction(
        self,
        amount: int,
        email: str,
        reference: str,
        callback_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a Paystack transaction.

        Args:
            amount: Transaction amount in kobo (smallest currency unit).
            email: Customer email address.
            reference: Unique transaction reference.
            callback_url: Optional callback URL for transaction.
            metadata: Optional metadata for transaction.

        Returns:
            Dict: Transaction initialization response with authorization URL.
        """
        endpoint = "/transaction/initialize"
        data = {
            "amount": amount,
            "email": email,
            "reference": reference,
            "currency": "NGN",  
        }

        if callback_url:
            data["callback_url"] = callback_url

        if metadata:
            data["metadata"] = metadata

        return await self.post(endpoint, data)

    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """
        Verify a Paystack transaction by reference.

        Args:
            reference: Transaction reference to verify.

        Returns:
            Dict: Transaction verification data.
        """
        endpoint = f"/transaction/verify/{reference}"
        return await self.get(endpoint)

    async def list_transactions(
        self,
        reference: Optional[str] = None,
        per_page: int = 50,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        List Paystack transactions with optional filtering.

        Args:
            reference: Optional reference filter.
            per_page: Number of transactions per page.
            page: Page number.

        Returns:
            Dict: Paginated transaction list.
        """
        endpoint = "/transaction"
        params = {
            "perPage": per_page,   
            "page": page,
        }

        if reference:
            params["reference"] = reference

        return await self.get(endpoint, params)

    def is_test_mode(self) -> bool:
        """
        Check if client is configured for test mode.

        Returns:
            bool: True if using test keys.
        """
        return self.secret_key.startswith("sk_test_")

    def is_live_mode(self) -> bool:
        """
        Check if client is configured for live mode.

        Returns:
            bool: True if using live keys.
        """
        return self.secret_key.startswith("sk_live_")


# Singleton instance for application-wide use
_paystack_client = None

def get_paystack_client() -> PaystackClient:
    """
    Get singleton Paystack client instance.

    Returns:
        PaystackClient: Configured Paystack client.
    """
    global _paystack_client
    if _paystack_client is None:
        _paystack_client = PaystackClient()
    return _paystack_client
