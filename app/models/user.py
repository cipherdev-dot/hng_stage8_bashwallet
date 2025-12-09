

import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    """
    User model representing a Google authenticated user.

    Uses Google sub (subject) as unique identifier instead of email/password.
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    google_sub = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
