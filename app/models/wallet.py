
from decimal import Decimal
import uuid
from sqlalchemy import Column, Boolean, String, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Wallet(Base):
    """
    Wallet model representing a user's financial account.

    One-to-one relationship with User. Maintains account balance
    and generates unique wallet numbers for identification.
    """

    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    wallet_number = Column(String(10), unique=True, nullable=False, index=True)  # e.g., "WAL123456"
    balance = Column(Numeric(precision=15, scale=2), default=Decimal('0.00'), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # One-to-one relationship with User
    user = relationship("User", backref="wallet", uselist=False)

    def has_sufficient_balance(self, amount: Decimal) -> bool:
        """
        Check if wallet has sufficient balance for an amount.

        Args:
            amount: Amount to check against balance.

        Returns:
            bool: True if balance >= amount.
        """
        return self.balance >= amount

    def credit_balance(self, amount: Decimal) -> None:
        """
        Credit amount to wallet balance.

        Args:
            amount: Amount to credit.
        """
        self.balance += amount

    def debit_balance(self, amount: Decimal) -> None:
        """
        Debit amount from wallet balance.

        Args:
            amount: Amount to debit.

        Raises:
            ValueError: If insufficient balance.
        """
        if not self.has_sufficient_balance(amount):
            raise ValueError("Insufficient wallet balance")
        self.balance -= amount
