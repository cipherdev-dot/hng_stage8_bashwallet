

import random
import string
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.wallet import Wallet


async def generate_unique_wallet_number(db: AsyncSession) -> str:
    """
    Generate a unique 10-character wallet number.

    Format: WAL + 6 random alphanumeric characters
    Example: WAL12A3B4C

    Args:
        db: Database session for uniqueness check.

    Returns:
        str: Unique wallet number.
    """
    max_attempts = 100  # Prevent infinite loop
    attempts = 0

    while attempts < max_attempts:
        # Generate 6 random alphanumeric characters
        chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        wallet_number = f"WAL{chars}"

        # Check if wallet number already exists
        result = await db.execute(
            select(Wallet).where(Wallet.wallet_number == wallet_number)
        )
        existing_wallet = result.scalars().first()

        if not existing_wallet:
            return wallet_number

        attempts += 1

    # Fallback if we can't generate a unique number
    raise ValueError("Unable to generate unique wallet number after maximum attempts")


def format_wallet_balance(balance: Decimal) -> str:
    """
    Format wallet balance for display.

    Args:
        balance: Balance as Decimal.

    Returns:
        str: Formatted balance string.
    """
    return f"{balance:.2f}"


def validate_wallet_amount(amount: Decimal) -> bool:
    """
    Validate wallet transaction amount.

    Args:
        amount: Amount to validate.

    Returns:
        bool: True if amount is valid for transactions.
    """
    # Must be positive and not too large
    if amount <= 0:
        return False

    # Maximum transaction amount (adjust as needed)
    max_amount = Decimal('1000000.00')  # 1 million
    if amount > max_amount:
        return False

    # Check decimal places (max 2)
    if amount.quantize(Decimal('0.01')) != amount:
        return False

    return True
