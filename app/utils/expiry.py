
import re
from datetime import datetime, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta


def parse_expiry(expiry: str) -> datetime:
    """
    Parse expiry string (1H, 1D, 1M, 1Y) into datetime object.

    Args:
        expiry: Expiry format string (e.g., "1H", "30D", "6M", "2Y")

    Returns:
        datetime: Expiry datetime in UTC.

    Raises:
        ValueError: If expiry format is invalid.
    """
    if not expiry:
        raise ValueError("Expiry string cannot be empty")

    # Match pattern like 1H, 30D, 6M, 2Y (case insensitive)
    match = re.match(r'^(\d+)([HD MY])$', expiry.upper())
    if not match:
        raise ValueError("Invalid expiry format. Use: 1H, 2D, 3M, 4Y")

    amount = int(match.group(1))
    unit = match.group(2).upper()

    now = datetime.utcnow()

    if unit == 'H':
        return now + timedelta(hours=amount)
    elif unit == 'D':
        return now + timedelta(days=amount)
    elif unit == 'M':
        return now + relativedelta(months=amount)
    elif unit == 'Y':
        return now + relativedelta(years=amount)
    else:
        raise ValueError(f"Unsupported expiry unit: {unit}")


def validate_expiry_format(expiry: str) -> bool:
    """
    Validate expiry format without converting.

    Args:
        expiry: Expiry format string.

    Returns:
        bool: True if format is valid.
    """
    try:
        parse_expiry(expiry)
        return True
    except ValueError:
        return False


def get_expiry_description(expiry: str) -> str:
    """
    Get human-readable description of expiry.

    Args:
        expiry: Expiry format string.

    Returns:
        str: Human-readable description.

    Raises:
        ValueError: If expiry format is invalid.
    """
    match = re.match(r'^(\d+)([HD MY])$', expiry.upper())
    if not match:
        raise ValueError("Invalid expiry format")

    amount = int(match.group(1))
    unit = match.group(2).upper()

    unit_names = {
        'H': 'hour' if amount == 1 else 'hours',
        'D': 'day' if amount == 1 else 'days',
        'M': 'month' if amount == 1 else 'months',
        'Y': 'year' if amount == 1 else 'years'
    }

    return f"{amount} {unit_names[unit]}"
