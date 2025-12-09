"""
API key management endpoints.

Handles creation, rollover, revocation, and listing of API keys.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.api_key_dependencies import get_api_key_user
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.api_key_schemas import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyResponse,
    APIKeyRevokeResponse,
    APIKeyRollover
)
from app.services.api_key_service import APIKeyService


logger = logging.getLogger(__name__)

keys_router = APIRouter()


@keys_router.post("/create", response_model=APIKeyCreateResponse)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new API key for the authenticated user.

    Enforces maximum of 5 active keys per user.

    Args:
        key_data: API key creation data with name, permissions, expiry.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        APIKeyCreateResponse: New API key details with secret (shown once).
    """
    try:
        api_key, plain_key = await APIKeyService.create_api_key(
            user_id=current_user.id,
            name=key_data.name,
            permissions=key_data.permissions,
            expiry=key_data.expiry,
            db=db
        )

       
        key_response = APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            permissions=api_key.permissions,
            expires_at=api_key.expires_at,
            revoked=api_key.revoked,
            revoked_at=api_key.revoked_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at
        )

        return APIKeyCreateResponse(key=key_response, secret=plain_key)

    except Exception as e:
        logger.error(f"Failed to create API key for user {current_user.id}: {e}")
        raise


@keys_router.post("/rollover", response_model=APIKeyCreateResponse)
async def rollover_api_key(
    rollover_data: APIKeyRollover,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new API key using permissions from an expired key.

    The expired key must truly be expired, and permissions are reused.

    Args:
        rollover_data: Rollover data with expired key ID and new expiry.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        APIKeyCreateResponse: New API key details with secret.
    """
    try:
        api_key, plain_key = await APIKeyService.rollover_api_key(
            user_id=current_user.id,
            expired_key_id=rollover_data.expired_key_id,
            expiry=rollover_data.expiry,
            db=db
        )

        # Convert to response format
        key_response = APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            permissions=api_key.permissions,
            expires_at=api_key.expires_at,
            revoked=api_key.revoked,
            revoked_at=api_key.revoked_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at
        )

        return APIKeyCreateResponse(key=key_response, secret=plain_key)

    except Exception as e:
        logger.error(f"Failed to rollover API key for user {current_user.id}: {e}")
        raise


@keys_router.post("/{key_id}/revoke", response_model=APIKeyRevokeResponse)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke an API key owned by the authenticated user.

    Args:
        key_id: UUID string of the key to revoke.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        APIKeyRevokeResponse: Revocation confirmation.
    """
    try:
        key_uuid = UUID(key_id)
        api_key = await APIKeyService.revoke_api_key(
            user_id=current_user.id,
            key_id=key_uuid,
            db=db
        )

        # Convert to response format
        key_response = APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            permissions=api_key.permissions,
            expires_at=api_key.expires_at,
            revoked=api_key.revoked,
            revoked_at=api_key.revoked_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at
        )

        return APIKeyRevokeResponse(
            message="API key revoked successfully",
            key=key_response
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID format")
    except Exception as e:
        logger.error(f"Failed to revoke API key {key_id}: {e}")
        raise


@keys_router.get("", response_model=APIKeyListResponse)
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all API keys for the authenticated user.

    Args:
        current_user: Authenticated user.
        db: Database session.

    Returns:
        APIKeyListResponse: List of all user's API keys.
    """
    try:
        api_keys = await APIKeyService.get_user_api_keys(current_user.id, db)

        # Convert to response format
        keys_response = []
        for key in api_keys:
            key_response = APIKeyResponse(
                id=key.id,
                name=key.name,
                permissions=key.permissions,
                expires_at=key.expires_at,
                revoked=key.revoked,
                revoked_at=key.revoked_at,
                last_used_at=key.last_used_at,
                created_at=key.created_at
            )
            keys_response.append(key_response)

        return APIKeyListResponse(keys=keys_response)

    except Exception as e:
        logger.error(f"Failed to list API keys for user {current_user.id}: {e}")
        raise


@keys_router.get("/protected/service")
async def protected_service_endpoint(
    user: User = Depends(get_api_key_user)
):
    """
    Protected endpoint accessible via API key authentication.

    Tests API key auth and shows user info.

    Args:
        user: User authenticated via API key.

    Returns:
        dict: User and authentication info.
    """
    user_obj, permissions = user
    return {
        "user_id": str(user_obj.id),
        "email": user_obj.email,
        "permissions": permissions,
        "message": "Authenticated via API key"
    }
