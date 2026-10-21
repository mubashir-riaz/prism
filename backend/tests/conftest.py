"""Pytest fixtures and configuration for Prism backend tests."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import async_session_factory, engine, get_db
from app.main import app as fastapi_app
import app.models as _models  # Ensure all SQLAlchemy models are registered
from app.models.api_key import APIKey
from app.models.enums import EnvironmentName, UserRole
from app.models.environment import Environment
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService

_test_engine: Optional[AsyncEngine] = None
_test_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


async def _init_test_engine() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    global _test_engine, _test_session_factory
    if _test_engine is not None and _test_session_factory is not None:
        return _test_engine, _test_session_factory

    # Try connecting to the configured PostgreSQL database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _test_engine = engine
        _test_session_factory = async_session_factory
        return _test_engine, _test_session_factory
    except Exception:
        pass

    # Fall back to SQLite in-memory engine with all tables created
    _test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _test_session_factory = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return _test_engine, _test_session_factory


@asynccontextmanager
async def lifespan_manager(application):
    """Manage application lifespan (startup and shutdown events)."""
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


@pytest_asyncio.fixture(scope="session")
async def test_db() -> AsyncGenerator[AsyncEngine, None]:
    """Provide the test database engine."""
    test_eng, _ = await _init_test_engine()
    yield test_eng


@pytest_asyncio.fixture(scope="session")
async def db_migrated(test_db: AsyncEngine) -> AsyncGenerator[None, None]:
    """Confirm database readiness for tests."""
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session per test with clean teardown."""
    test_eng, session_fac = await _init_test_engine()
    async with session_fac() as session:
        yield session

    # Teardown: clean tables after test
    async with test_eng.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async httpx client fixture wired to the test database session."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        async with lifespan_manager(fastapi_app) as test_app:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as ac:
                yield ac
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def async_client(client: AsyncClient) -> AsyncClient:
    """Alias fixture for client."""
    return client


# ---------------------------------------------------------------------------
# Domain Fixtures
# ---------------------------------------------------------------------------


class SeededOrg:
    """Encapsulates a seeded organization, owner user, and plaintext password."""

    def __init__(self, org: Organization, owner: User, password: str) -> None:
        self.org = org
        self.owner = owner
        self.password = password
        self.org_id = org.id
        self.owner_id = owner.id
        self.slug = str(org.slug)
        self.email = str(owner.email)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __iter__(self):
        yield self.org
        yield self.owner
        yield self.password


@pytest_asyncio.fixture
async def seeded_org(db_session: AsyncSession) -> SeededOrg:
    """Creates an org + owner user with a real hashed password."""
    org_repo = OrganizationRepository(db_session)
    user_repo = UserRepository(db_session)

    unique_suffix = uuid.uuid4().hex[:8]
    org = await org_repo.create(
        name=f"Test Org {unique_suffix}",
        slug=f"test-org-{unique_suffix}",
    )

    plain_password = "Password123!"
    hashed = hash_password(plain_password)

    owner = await user_repo.create(
        organization_id=org.id,
        email=f"owner_{unique_suffix}@example.com",
        hashed_password=hashed,
        full_name="Owner User",
        role=UserRole.OWNER,
        is_active=True,
    )
    await db_session.commit()
    return SeededOrg(org=org, owner=owner, password=plain_password)


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, seeded_org: SeededOrg) -> AsyncGenerator[AsyncClient, None]:
    """httpx client with a valid Authorization: Bearer <token> header for the OWNER."""
    token = create_access_token(
        subject=str(seeded_org.owner.id),
        org_id=str(seeded_org.org.id),
        role=seeded_org.owner.role.value,
    )
    async with AsyncClient(
        transport=client._transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx client with valid Bearer token for an ADMIN user."""
    user_repo = UserRepository(db_session)
    unique_suffix = uuid.uuid4().hex[:8]
    admin_user = await user_repo.create(
        organization_id=seeded_org.org.id,
        email=f"admin_{unique_suffix}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    await db_session.commit()
    token = create_access_token(
        subject=str(admin_user.id),
        org_id=str(seeded_org.org.id),
        role=admin_user.role.value,
    )
    async with AsyncClient(
        transport=client._transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def member_client(
    client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx client with valid Bearer token for a MEMBER user."""
    user_repo = UserRepository(db_session)
    unique_suffix = uuid.uuid4().hex[:8]
    member_user = await user_repo.create(
        organization_id=seeded_org.org.id,
        email=f"member_{unique_suffix}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Member User",
        role=UserRole.MEMBER,
        is_active=True,
    )
    await db_session.commit()
    token = create_access_token(
        subject=str(member_user.id),
        org_id=str(seeded_org.org.id),
        role=member_user.role.value,
    )
    async with AsyncClient(
        transport=client._transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def viewer_client(
    client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx client with valid Bearer token for a VIEWER user."""
    user_repo = UserRepository(db_session)
    unique_suffix = uuid.uuid4().hex[:8]
    viewer_user = await user_repo.create(
        organization_id=seeded_org.org.id,
        email=f"viewer_{unique_suffix}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Viewer User",
        role=UserRole.VIEWER,
        is_active=True,
    )
    await db_session.commit()
    token = create_access_token(
        subject=str(viewer_user.id),
        org_id=str(seeded_org.org.id),
        role=viewer_user.role.value,
    )
    async with AsyncClient(
        transport=client._transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac


class APIKeyHeaders(dict):
    """Dictionary holding headers and metadata for a created test API key."""

    def __init__(
        self,
        headers: dict[str, str],
        key_record: APIKey,
        plaintext: str,
        project: Project,
        environment: Environment,
    ) -> None:
        super().__init__(headers)
        self.key_record = key_record
        self.plaintext = plaintext
        self.project = project
        self.environment = environment


@pytest_asyncio.fixture
async def api_key_headers(
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> APIKeyHeaders:
    """A valid X-API-Key header for a freshly created key."""
    proj_svc = ProjectService(db_session)
    unique_suffix = uuid.uuid4().hex[:8]
    project = await proj_svc.create_project(
        ProjectCreate(
            organization_id=seeded_org.org.id,
            name=f"Key Project {unique_suffix}",
            slug=f"key-proj-{unique_suffix}",
        )
    )
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)
    key_svc = APIKeyService(db_session)
    record, plaintext = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name=f"api-key-{unique_suffix}",
        actor_user_id=seeded_org.owner.id,
    )
    await db_session.commit()
    return APIKeyHeaders(
        headers={"X-API-Key": plaintext},
        key_record=record,
        plaintext=plaintext,
        project=project,
        environment=dev_env,
    )
