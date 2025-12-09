

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user."""
    google_sub: str


class UserUpdate(UserBase):
    """Schema for updating user information."""
    pass


class UserInDB(UserBase):
    """Schema for user data from database."""
    id: UUID
    google_sub: str
    created_at: datetime


class UserResponse(UserBase):
    """Schema for user response to client."""
    id: UUID
    google_sub: str
    created_at: datetime


class AuthResponse(BaseModel):
    """Schema for authentication response with JWT."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
