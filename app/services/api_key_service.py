
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import generate_api_key, hash_api_key, verify_api_key
from app.models.api_key import APIKey
from app.models.user import User
from app.utils.expiry import parse_expiry, validate_expiry_format


logger = logging.getLogger(__name__)


class APIKeyService:
    """Service class for API key operations."""

    MAX_ACTIVE_KEYS = 5

    @staticmethod
    async def get_active_api_keys_count(user_id: UUID, db: AsyncSession) -> int:
        """
        Count the number of active API keys for a user.

        Args:
            user_id: User ID to count keys for.
            db: Database session.

        Returns:
            int: Number of active (non-revoked, non-expired) API keys.
        """
        from datetime import datetime, timezone
        # Use timezone-aware UTC time for consistent comparison
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(APIKey).where(
                APIKey.user_id == user_id,
                APIKey.revoked == False,
                APIKey.expires_at > now
            )
        )
        return len(result.scalars().all())

    @staticmethod
    async def create_api_key(
        user_id: UUID,
        name: str,
        permissions: List[str],
        expiry: str,
        db: AsyncSession
    ) -> tuple[APIKey, str]:
        """
        Create a new API key for a user.

        Args:
            user_id: User ID to create key for.
            name: Human-readable name for the key.
            permissions: List of permission strings.
            expiry: Expiry format (1H, 1D, 1M, 1Y).
            db: Database session.

        Returns:
            tuple: (APIKey object, plain API key string)

        Raises:
            HTTPException: If user exceeds max active keys or invalid expiry.
        """
        # Validate expiry format
        if not validate_expiry_format(expiry):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid expiry format. Use: 1H, 2D, 3M, 4Y"
            )

        # Check max active keys limit
        active_count = await APIKeyService.get_active_api_keys_count(user_id, db)
        if active_count >= APIKeyService.MAX_ACTIVE_KEYS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum of {APIKeyService.MAX_ACTIVE_KEYS} active API keys allowed"
            )

        # Generate and hash the key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        # Parse expiry to datetime
        expires_at = parse_expiry(expiry)

        # Create API key record
        api_key = APIKey(
            user_id=user_id,
            name=name,
            hashed_key=hashed_key,
            permissions=permissions,
            expires_at=expires_at
        )

        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

        logger.info(f"Created API key for user {user_id}: {api_key.id}")
        return api_key, plain_key

    @staticmethod
    async def rollover_api_key(
        user_id: UUID,
        expired_key_id: UUID,
        expiry: str,
        db: AsyncSession
    ) -> tuple[APIKey, str]:
        """
        Create a new API key using the same permissions as an expired key.

        Args:
            user_id: User ID to rollover key for.
            expired_key_id: ID of the expired key to reuse permissions from.
            expiry: Expiry format for new key (1H, 1D, 1M, 1Y).
            db: Database session.

        Returns:
            tuple: (new APIKey object, plain API key string)

        Raises:
            HTTPException: If expired key not found, not owned by user, or not truly expired.
        """
        # Validate expiry format
        if not validate_expiry_format(expiry):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid expiry format. Use: 1H, 2D, 3M, 4Y"
            )

        # Find the expired key
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == expired_key_id,
                APIKey.user_id == user_id
            )
        )
        expired_key = result.scalars().first()

        if not expired_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expired API key not found"
            )

        # Check if the key is truly expired
        if not expired_key.is_expired():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Key must be expired to rollover"
            )

        # Check max active keys limit
        active_count = await APIKeyService.get_active_api_keys_count(user_id, db)
        if active_count >= APIKeyService.MAX_ACTIVE_KEYS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum of {APIKeyService.MAX_ACTIVE_KEYS} active API keys exceeded. Cannot rollover."
            )

        # Generate and hash the new key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        # Parse expiry to datetime
        expires_at = parse_expiry(expiry)

        # Create new API key with same permissions
        new_key = APIKey(
            user_id=user_id,
            name=f"{expired_key.name} (rolled over)",
            hashed_key=hashed_key,
            permissions=expired_key.permissions,  # Reuse permissions
            expires_at=expires_at
        )

        db.add(new_key)
        await db.commit()
        await db.refresh(new_key)

        logger.info(f"Rolled over API key for user {user_id}: {expired_key.id} -> {new_key.id}")
        return new_key, plain_key

    @staticmethod
    async def revoke_api_key(
        user_id: UUID,
        key_id: UUID,
        db: AsyncSession
    ) -> APIKey:
        """
        Revoke an API key owned by the user.

        Args:
            user_id: User ID owning the key.
            key_id: ID of the key to revoke.
            db: Database session.

        Returns:
            APIKey: The revoked API key.

        Raises:
            HTTPException: If key not found or not owned by user.
        """
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == key_id,
                APIKey.user_id == user_id
            )
        )
        api_key = result.scalars().first()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )

        if not api_key.revoked:
            api_key.revoke()
            await db.commit()
            logger.info(f"Revoked API key {key_id} for user {user_id}")

        return api_key

    @staticmethod
    async def get_user_api_keys(user_id: UUID, db: AsyncSession) -> List[APIKey]:
        """
        Get all API keys for a user.

        Args:
            user_id: User ID.
            db: Database session.

        Returns:
            List[APIKey]: All API keys for the user (with status information).
        """
        result = await db.execute(
            select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def validate_api_key(
        api_key: str,
        db: AsyncSession
    ) -> tuple[Optional[APIKey], Optional[User]]:
        """
        Validate an API key and return associated key and user.

        Args:
            api_key: The plain API key to validate.
            db: Database session.

        Returns:
            tuple: (APIKey object or None, User object or None)
        """
        from datetime import datetime

        from datetime import timezone

        # Find the API key by matching hash
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(APIKey).where(
                APIKey.revoked == False,
                APIKey.expires_at > now
            )
        )
        api_keys = result.scalars().all()

        # Check each key's hash
        for key_obj in api_keys:
            if verify_api_key(api_key, key_obj.hashed_key):
                # Update last used timestamp
                key_obj.last_used_at = datetime.now(timezone.utc)

                # Get the user
                user_result = await db.execute(
                    select(User).where(User.id == key_obj.user_id)
                )
                user = user_result.scalars().first()

                await db.commit()
                logger.info(f"Validated API key for user {user.id if user else 'unknown'}")
                return key_obj, user

        return None, None
