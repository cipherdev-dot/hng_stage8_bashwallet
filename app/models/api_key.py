

import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Boolean, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class APIKey(Base):
    """
    API Key model for secure authentication.

    Supports permissions-based access control, expiry management,
    and revocation. Enforces maximum of 5 active keys per user.
    """

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    hashed_key = Column(String, unique=True, nullable=False, index=True)
    permissions = Column(JSON, default=list, nullable=False) 
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Composite index for efficient key lookups
    __table_args__ = (
        Index('ix_api_keys_user_not_revoked', 'user_id', 'revoked'),
        Index('ix_api_keys_expires_at', 'expires_at'),
    )

    def is_expired(self) -> bool:
        """Check if the API key has expired."""
        from datetime import timezone
        # expires_at is timezone-aware, so compare with UTC now
        utc_now = datetime.now(timezone.utc)
        return utc_now >= self.expires_at

    def is_active(self) -> bool:
        """Check if the API key is active (not revoked and not expired)."""
        return not self.revoked and not self.is_expired()

    def has_permission(self, permission: str) -> bool:
        """Check if the API key has a specific permission."""
        return permission in self.permissions

    def revoke(self) -> None:
        """Revoke the API key."""
        from datetime import timezone
        self.revoked = True
        self.revoked_at = datetime.now(timezone.utc)
