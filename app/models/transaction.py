

from decimal import Decimal
from datetime import datetime
import enum
import uuid

from sqlalchemy import Column, Enum, String, Numeric, ForeignKey, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TransactionType(enum.Enum):
    """Enumeration of transaction types."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    FEE = "fee"
    REFUND = "refund"


class TransactionStatus(enum.Enum):
    """Enumeration of transaction statuses."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Transaction(Base):
    """
    Transaction model for recording all wallet operations.

    Tracks deposits, transfers, fees, and other financial operations
    with full audit trail and metadata storage.
    """

    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Transaction details
    transaction_type = Column(Enum(TransactionType), nullable=False, index=True)
    amount = Column(Numeric(precision=15, scale=2), nullable=False)
    description = Column(String(255), nullable=True)

    # Status tracking
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False, index=True)

    # Reference fields for external tracking
    reference = Column(String(100), nullable=True, index=True)  
    external_reference = Column(String(100), nullable=True, index=True) 

    # Wallet relationships 
    source_wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True, index=True)
    destination_wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True, index=True)

    # Fee tracking
    fee_amount = Column(Numeric(precision=10, scale=2), default=Decimal('0.00'), nullable=False)

    # Metadata storage (JSON for flexible data like Paystack response, transfer details, etc.)
    transaction_metadata = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="transactions")
    source_wallet = relationship("Wallet", foreign_keys=[source_wallet_id], backref="sent_transactions")
    destination_wallet = relationship("Wallet", foreign_keys=[destination_wallet_id], backref="received_transactions")

    def mark_completed(self) -> None:
        """
        Mark transaction as completed with timestamp.
        """
        self.status = TransactionStatus.COMPLETED
        from datetime import timezone
        self.completed_at = datetime.now(timezone.utc)

    def mark_failed(self, reason: str = None) -> None:
        """
        Mark transaction as failed.

        Args:
            reason: Optional reason for failure.
        """
        self.status = TransactionStatus.FAILED
        if reason and self.transaction_metadata:
            self.transaction_metadata = {**self.transaction_metadata, "failure_reason": reason}
        elif reason:
            self.transaction_metadata = {"failure_reason": reason}

    def mark_cancelled(self) -> None:
        """
        Mark transaction as cancelled.
        """
        self.status = TransactionStatus.CANCELLED

    def is_completed(self) -> bool:
        """Check if transaction is completed."""
        return self.status == TransactionStatus.COMPLETED

    def is_pending(self) -> bool:
        """Check if transaction is pending."""
        return self.status == TransactionStatus.PENDING

    def is_deposit(self) -> bool:
        """Check if transaction is a deposit."""
        return self.transaction_type == TransactionType.DEPOSIT

    def is_transfer(self) -> bool:
        """Check if transaction is a transfer."""
        return self.transaction_type == TransactionType.TRANSFER

    def get_net_amount(self) -> Decimal:
        """
        Get net amount 

        Returns:
            Decimal: Net amount after fees.
        """
        return self.amount - self.fee_amount
