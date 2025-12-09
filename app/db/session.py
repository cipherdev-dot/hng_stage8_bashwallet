

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.base import Base


# Async database engine
engine = create_async_engine(settings.database_url, echo=False)

# Async session factory
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get async database session.

    Yields an async database session and ensures it's closed after use.

    Yields:
        AsyncSession: Database session for the request lifespan.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Initialize database and create all tables.

    Creates all tables defined in the models if they don't exist.
    Should be called during application startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
