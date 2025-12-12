

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.wallet_schemas import TransferResponse
from app.utils.wallet import validate_wallet_amount


logger = logging.getLogger(__name__)


class TransferService:
    """
    Service for handling wallet transfers with atomic balance updates.
    """

    @staticmethod
    async def find_recipient_wallet(
        recipient_wallet_number: str,
        db: AsyncSession
    ) -> Optional[Wallet]:
        """
        Find recipient wallet by wallet number.

        Args:
            recipient_wallet_number: Wallet number to search for.
            db: Database session.

        Returns:
            Optional[Wallet]: Recipient's wallet if found, None otherwise.
        """
        result = await db.execute(
            select(Wallet).where(Wallet.wallet_number == recipient_wallet_number)
        )
        return result.scalars().first()

    @staticmethod
    async def create_transfer_transaction(
        sender_wallet: Wallet,
        recipient_wallet: Wallet,
        amount: Decimal,
        description: str = None,
        db: AsyncSession = None
    ) -> tuple[Transaction, Transaction]:
        """
        Create debit and credit transactions for a transfer.

        Args:
            sender_wallet: Sender's wallet.
            recipient_wallet: Recipient's wallet.
            amount: Transfer amount.
            description: Optional transfer description.
            db: Database session.

        Returns:
            Tuple of (debit_transaction, credit_transaction).
        """
        # Generate unique reference for the transfer
        import uuid
        transfer_reference = f"transfer_{uuid.uuid4().hex[:16]}"

        # Create debit transaction (sender)
        debit_transaction = Transaction(
            user_id=sender_wallet.user_id,
            transaction_type=TransactionType.TRANSFER,
            amount=amount,
            description=description or "Wallet transfer sent",
            reference=transfer_reference,
            status=TransactionStatus.PENDING,
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=recipient_wallet.id,
            transaction_metadata={
                "recipient_wallet": recipient_wallet.wallet_number,
                "transfer_type": "debit"
            }
        )

        # Create credit transaction (recipient)
        credit_transaction = Transaction(
            user_id=recipient_wallet.user_id,
            transaction_type=TransactionType.TRANSFER,
            amount=amount,
            description=description or "Wallet transfer received",
            reference=transfer_reference,
            status=TransactionStatus.PENDING,
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=recipient_wallet.id,
            transaction_metadata={
                "sender_wallet": sender_wallet.wallet_number,
                "transfer_type": "credit"
            }
        )

        db.add(debit_transaction)
        db.add(credit_transaction)
        await db.commit()
        await db.refresh(debit_transaction)
        await db.refresh(credit_transaction)

        return debit_transaction, credit_transaction

    @staticmethod
    async def execute_transfer(
        sender_wallet: Wallet,
        recipient_wallet: Wallet,
        amount: Decimal,
        description: str = None,
        db: AsyncSession = None
    ) -> TransferResponse:
        """
        Execute wallet transfer with atomic balance updates.

        Args:
            sender_wallet: Sender's wallet.
            recipient_wallet: Recipient's wallet.
            amount: Transfer amount.
            description: Optional transfer description.
            db: Database session.

        Returns:
            TransferResponse: Transfer completion details.

        Raises:
            Exception: If transfer validation fails or execution fails.
        """
        logger.info(f"Transfer request: {sender_wallet.wallet_number} → {recipient_wallet.wallet_number}, ₦{amount}")

        # Validate amount
        if not validate_wallet_amount(amount):
            raise Exception("Invalid transfer amount")

        if amount <= Decimal('0'):
            raise Exception("Transfer amount must be greater than zero")

        if amount > sender_wallet.balance:
            raise Exception(f"Insufficient balance. Available: ₦{sender_wallet.balance}")

        if sender_wallet.id == recipient_wallet.id:
            raise Exception("Cannot transfer to your own wallet")

        try:
            # Create transfer transactions
            debit_transaction, credit_transaction = await TransferService.create_transfer_transaction(
                sender_wallet=sender_wallet,
                recipient_wallet=recipient_wallet,
                amount=amount,
                description=description,
                db=db
            )

            # Execute the transfer
            sender_wallet.debit_balance(amount)
            recipient_wallet.credit_balance(amount)

            # Mark transactions as completed
            debit_transaction.mark_completed()
            credit_transaction.mark_completed()

            # Note: Let the FastAPI dependency handle commit/rollback
            logger.info(f"Transfer completed: {sender_wallet.wallet_number} sent ₦{amount} to {recipient_wallet.wallet_number}")

            return TransferResponse(
                transaction_id=str(debit_transaction.id),
                sender_wallet=sender_wallet.wallet_number,
                recipient_wallet=recipient_wallet.wallet_number,
                amount=amount,
                description=description,
                message=f"Successfully transferred ₦{amount} to {recipient_wallet.wallet_number}"
            )

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            raise Exception(f"Transfer failed: {str(e)}")

    @staticmethod
    async def get_user_transactions(
        user_id: str,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[int, list[Transaction]]:
        """
        Get transaction history for a user.

        Args:
            user_id: User ID to get transactions for.
            db: Database session.
            skip: Number of transactions to skip.
            limit: Maximum number of transactions to return.

        Returns:
            Tuple of (total_count, list_of_transactions).
        """
        # Get total count
        count_result = await db.execute(
            select(Transaction).where(Transaction.user_id == user_id)
        )
        total = len(count_result.scalars().all())

        # Get transactions with pagination
        result = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        transactions = result.scalars().all()

        return total, transactions
