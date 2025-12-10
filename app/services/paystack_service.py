

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paystack import get_paystack_client
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user import User
from app.models.wallet import Wallet
from app.utils.wallet import validate_wallet_amount


logger = logging.getLogger(__name__)


class PaystackService:
    """
    Service class for Paystack payment operations.

    Handles deposit transactions, webhook processing, and Paystack integration
    for wallet operations.
    """

    @staticmethod
    def generate_transaction_reference(user_id: str) -> str:
        """
        Generate a unique transaction reference for Paystack.

        Format: user_id + timestamp + random_uuid

        Args:
            user_id: User ID for reference generation.

        Returns:
            str: Unique transaction reference.
        """
        timestamp = str(int(uuid.uuid1().time))
        random_part = str(uuid.uuid4())[:8]
        reference = f"{user_id}_{timestamp}_{random_part}"

        
        if len(reference) > 50:
            reference = reference[:50]

        return reference

    @staticmethod
    def convert_naira_to_kobo(amount: Decimal) -> int:
        """
        Convert Naira to kobo for Paystack API.

        Args:
            amount: Amount in Naira.

        Returns:
            int: Amount in kobo.
        """
        return int(amount * 100) 

    @staticmethod
    def convert_kobo_to_naira(amount: int) -> Decimal:
        """
        Convert kobo to Naira.

        Args:
            amount: Amount in kobo.

        Returns:
            Decimal: Amount in Naira.
        """
        return Decimal(amount) / 100

    @staticmethod
    async def initialize_deposit(
        user: User,
        amount: Decimal,
        db: AsyncSession,
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initialize a deposit transaction with Paystack.

        Args:
            user: User requesting deposit.
            amount: Deposit amount in Naira.
            db: Database session.
            callback_url: Optional callback URL.

        Returns:
            Dict: Paystack initialization response with authorization URL.

        Raises:
            Exception: If validation fails or Paystack error occurs.
        """
        # Validate amount
        if not validate_wallet_amount(amount):
            raise Exception("Invalid deposit amount")

        # Check minimum deposit amount
        min_deposit = Decimal('50.00')
        if amount < min_deposit:
            raise Exception(f"Minimum deposit amount is ₦{min_deposit}")

        # Generate unique reference
        reference = PaystackService.generate_transaction_reference(str(user.id))

        # Convert amount to kobo
        amount_kobo = PaystackService.convert_naira_to_kobo(amount)

        # Create pending transaction in our database
        transaction = Transaction(
            user_id=user.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            reference=reference,
            status=TransactionStatus.PENDING,
            transaction_metadata={
                "paystack_amount_kobo": amount_kobo,
                "user_email": user.email,
                "description": "Wallet deposit via Paystack"
            }
        )

        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)

        # Initialize with Paystack
        paystack_client = get_paystack_client()

        try:
            paystack_response = await paystack_client.initialize_transaction(
                amount=amount_kobo,
                email=user.email,
                reference=reference,
                callback_url=callback_url,
                metadata={
                    "transaction_id": str(transaction.id),
                    "user_id": str(user.id),
                    "wallet_number": None  # We'll get this from the endpoint
                }
            )

            logger.info(f"Initialized Paystack deposit for user {user.id}: ref {reference}")
            return paystack_response

        except Exception as e:
            # Mark transaction as failed if Paystack initialization fails
            transaction.status = TransactionStatus.FAILED
            transaction.transaction_metadata = {
                **transaction.transaction_metadata,
                "failure_reason": str(e)
            }
            await db.commit()

            logger.error(f"Failed to initialize Paystack deposit for user {user.id}: {e}")
            raise Exception(f"Deposit initialization failed: {str(e)}")

    @staticmethod
    async def verify_deposit_transaction(
        reference: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Verify a deposit transaction with Paystack.

        Args:
            reference: Transaction reference to verify.
            db: Database session.

        Returns:
            Dict: Paystack verification response.

        Raises:
            Exception: If verification fails.
        """
        paystack_client = get_paystack_client()

        verification_response = await paystack_client.verify_transaction(reference)

        # Log verification (webhook will handle the actual processing)
        logger.info(f"Verified Paystack transaction: {reference}")
        return verification_response

    @staticmethod
    async def process_deposit_webhook(
        webhook_data: Dict[str, Any],
        db: AsyncSession
    ) -> bool:
        """
        Process Paystack webhook for deposit completion.


        Args:
            webhook_data: Webhook payload from Paystack.
            db: Database session.

        Returns:
            bool: True if processed successfully.
        """
        # Extract webhook event data
        event = webhook_data.get("event")
        data = webhook_data.get("data", {})

        # Only process charge.success events
        if event != "charge.success":
            logger.info(f"Ignoring webhook event: {event}")
            return True

        # Extract transaction reference
        reference = data.get("reference")
        if not reference:
            logger.error("Webhook missing transaction reference")
            return False

        # Find our transaction by reference
        from sqlalchemy.future import select

        result = await db.execute(
            select(Transaction).where(Transaction.reference == reference)
        )
        transaction = result.scalars().first()

        if not transaction:
            logger.error(f"Transaction not found for reference: {reference}")
            return False

        # Check if already processed 
        if transaction.status == TransactionStatus.COMPLETED:
            logger.info(f"Transaction {reference} already processed")
            return True

        # Verify transaction details
        paystack_amount_kobo = data.get("amount")
        paystack_amount_naira = PaystackService.convert_kobo_to_naira(paystack_amount_kobo)

        if paystack_amount_naira != transaction.amount:
            logger.error(f"Amount mismatch for transaction {reference}: expected {transaction.amount}, got {paystack_amount_naira}")
            transaction.status = TransactionStatus.FAILED
            transaction.transaction_metadata = {
                **transaction.transaction_metadata,
                "failure_reason": "Amount mismatch",
                "webhook_data": webhook_data
            }
            await db.commit()
            return False

        # Find user's wallet
        result = await db.execute(
            select(Wallet).where(Wallet.user_id == transaction.user_id)
        )
        wallet = result.scalars().first()

        if not wallet:
            logger.error(f"Wallet not found for user {transaction.user_id}")
            transaction.status = TransactionStatus.FAILED
            await db.commit()
            return False

        # Credit wallet balance
        try:
            wallet.credit_balance(transaction.amount)
            transaction.mark_completed()

            # Update metadata with webhook data
            transaction.transaction_metadata = {
                **transaction.transaction_metadata,
                "webhook_processed": True,
                "paystack_data": data
            }

            await db.commit()

            logger.info(f"Successfully processed deposit webhook for {reference}: credited ₦{transaction.amount} to wallet {wallet.wallet_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to credit wallet for transaction {reference}: {e}")
            transaction.status = TransactionStatus.FAILED
            await db.commit()
            return False

    @staticmethod
    async def get_transaction_details(
        transaction_id: str,
        db: AsyncSession
    ) -> Optional[Transaction]:
        """
        Get transaction details by ID.

        Args:
            transaction_id: Transaction UUID.
            db: Database session.

        Returns:
            Optional[Transaction]: Transaction if found.
        """
        from sqlalchemy.future import select

        result = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_transaction_by_reference(
        reference: str,
        db: AsyncSession
    ) -> Optional[Transaction]:
        """
        Get transaction details by Paystack reference.

        Args:
            reference: Paystack reference.
            db: Database session.

        Returns:
            Optional[Transaction]: Transaction if found.
        """
        from sqlalchemy.future import select

        result = await db.execute(
            select(Transaction).where(Transaction.reference == reference)
        )
        return result.scalars().first()
