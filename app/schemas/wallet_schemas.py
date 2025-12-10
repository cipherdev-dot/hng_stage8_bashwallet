from decimal import Decimal

from pydantic import BaseModel


class DepositRequest(BaseModel):
    """Request model for wallet deposit."""

    amount: Decimal  # Amount in Naira


class DepositResponse(BaseModel):
    """Response model for deposit initialization."""

    transaction_id: str
    reference: str
    authorization_url: str
    amount: Decimal
    message: str


class BalanceResponse(BaseModel):
    """Response model for wallet balance."""

    wallet_number: str
    balance: str
    currency: str = "NGN"
    is_active: bool


class WebhookResponse(BaseModel):
    """Response model for webhook processing."""

    status: str
