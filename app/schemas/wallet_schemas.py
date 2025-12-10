from datetime import datetime
from decimal import Decimal
from typing import List, Optional

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


class TransferRequest(BaseModel):
    """Request model for wallet transfer."""
    recipient_wallet_number: str
    amount: Decimal
    description: Optional[str] = None


class TransferResponse(BaseModel):
    """Response model for transfer completion."""
    transaction_id: str
    sender_wallet: str
    recipient_wallet: str
    amount: Decimal
    description: Optional[str] = None
    message: str


class TransactionResponse(BaseModel):
    """Response model for transaction details."""
    id: str
    user_id: str
    transaction_type: str
    amount: str
    description: Optional[str] = None
    status: str
    reference: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionHistoryResponse(BaseModel):
    """Response model for transaction history."""
    total: int
    transactions: List[TransactionResponse]


class WebhookResponse(BaseModel):
    """Response model for webhook processing."""

    status: str
