from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL must be configured.")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

AsyncSessionLocal = async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session and ensure it is closed after request completion."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
