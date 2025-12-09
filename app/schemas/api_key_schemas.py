
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class APIKeyBase(BaseModel):
    """Base API key schema with common fields."""
    name: str
    permissions: List[str]


class APIKeyCreate(APIKeyBase):
    """Schema for creating a new API key."""
    expiry: str  # Format: 1H, 1D, 1M, 1Y


class APIKeyRollover(BaseModel):
    """Schema for rolling over an expired API key."""
    expired_key_id: UUID
    expiry: str  # Format: 1H, 1D, 1M, 1Y


class APIKeyResponse(BaseModel):
    """Schema for API key response."""
    id: UUID
    name: str
    permissions: List[str]
    expires_at: datetime
    revoked: bool
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime


class APIKeyCreateResponse(BaseModel):
    """Schema for API key creation response."""
    key: APIKeyResponse
    secret: str  


class APIKeyListResponse(BaseModel):
    """Schema for listing API keys."""
    keys: List[APIKeyResponse]


class APIKeyRevokeResponse(BaseModel):
    """Schema for API key revocation response."""
    message: str
    key: APIKeyResponse
