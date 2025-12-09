

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import argon2
from jose import JWTError, jwt

from app.core.config import settings


# Set up argon2 hasher
ph = argon2.PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

logger = logging.getLogger(__name__)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in the token (usually user ID/sub).
        expires_delta: Optional custom expiration time.

    Returns:
        str: Encoded JWT token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token to verify.

    Returns:
        Optional[dict]: Decoded token payload or None if invalid.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


def generate_api_key() -> str:
    """
    Generate a new secure API key with prefix.

    Creates a live/test key with format: sk_live_<32-char-secret> or sk_test_<32-char-secret>

    Returns:
        str: Generated API key (not hashed yet).
    """
    # Generate 32-character secure random string
    secret_part = secrets.token_urlsafe(32)

    # For now, generate live keys (can be made configurable)
    prefix = "sk_live_"

    return f"{prefix}{secret_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using bcrypt (via argon2).

    Args:
        api_key: The raw API key to hash.

    Returns:
        str: Bcrypt hash of the API key.
    """
    try:
        hashed = ph.hash(api_key)
        return hashed
    except Exception as e:
        logger.error(f"Failed to hash API key: {e}")
        raise


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its hash using constant-time comparison.

    Args:
        plain_key: The plain API key.
        hashed_key: The stored hash.

    Returns:
        bool: True if the key matches the hash.
    """
    try:
        ph.verify(hashed_key, plain_key)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False
    except Exception as e:
        logger.error(f"Failed to verify API key: {e}")
        return False
