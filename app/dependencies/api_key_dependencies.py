"""
API key authentication dependencies.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.api_key import APIKey
from app.models.user import User
from app.services.api_key_service import APIKeyService


async def get_api_key_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> tuple[User, list[str]]:
    """
    Dependency to authenticate via API key and return user + permissions.

    Checks x-api-key header, validates the key, and returns user with permissions.

    Args:
        request: FastAPI request object.
        db: Database session.

    Returns:
        tuple: (User object, list of permissions)

    Raises:
        HTTPException: If API key is invalid, expired, revoked, etc.
    """
    api_key_header = request.headers.get("x-api-key")
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required in x-api-key header"
        )

    # Validate the API key
    api_key_obj, user = await APIKeyService.validate_api_key(api_key_header, db)

    if not api_key_obj or not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Check if key is active and user has permissions
    if not api_key_obj.is_active():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is inactive"
        )

    return user, api_key_obj.permissions
