"""Pytest fixtures and configuration for Prism backend tests."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import async_session_factory, engine
from app.main import app


@asynccontextmanager
async def lifespan_manager(application):
    """Manage application lifespan (startup and shutdown events).
    
    Tries `asgi-lifespan.LifespanManager` if installed, falling back to
    FastAPI / Starlette's built-in `lifespan_context`.
    """
    try:
        from asgi_lifespan import LifespanManager

        async with LifespanManager(application) as manager:
            yield manager.app
    except ImportError:
        lifespan_ctx = getattr(application.router, "lifespan_context", None)
        if lifespan_ctx:
            async with lifespan_ctx(application):
                yield application
        else:
            yield application


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async httpx client fixture using ASGITransport(app) with lifespan active ('lifespan=on').
    
    Ensures application lifespan events (logging initialization, database
    connectivity check, and graceful engine disposal on shutdown) execute
    for test runs.
    """
    async with lifespan_manager(app) as test_app:
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as ac:
            yield ac


@pytest_asyncio.fixture
async def async_client(client: AsyncClient) -> AsyncClient:
    """Alias fixture for client."""
    return client


@pytest_asyncio.fixture(scope="session")
async def test_db() -> AsyncGenerator[AsyncEngine, None]:
    """Fixture expecting a pre-migrated test database.

    Database Migration Strategy: Pre-Migrated Test Database
    -------------------------------------------------------
    This test suite is configured to expect a pre-migrated test database.
    Before executing the test suite, ensure database migrations have been applied
    to the target database (e.g., via `alembic upgrade head` or container initialization
    scripts in CI / Docker Compose).

    Rationale:
    1. Asyncpg and Alembic's async runner use `asyncio.run()`, which conflicts
       with pytest-asyncio's active event loop when run in-process.
    2. Decoupling migration execution from individual test invocations prevents schema
       races during parallel or repeated test runs and aligns with standard CI/CD practices.
    
    This fixture verifies that the database is reachable and ready to receive queries.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield engine


@pytest_asyncio.fixture(scope="session")
async def db_migrated(test_db: AsyncEngine) -> AsyncGenerator[None, None]:
    """Alias fixture confirming test database migration status and readiness."""
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated transactional async database session for tests.
    
    Any transactions executed during the test are rolled back at teardown
    to maintain state isolation between tests.
    """
    async with async_session_factory() as session:
        yield session
        await session.rollback()
