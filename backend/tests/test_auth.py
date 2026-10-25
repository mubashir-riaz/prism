"""Unit and integration tests for auth dependencies and endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, require_role
from app.core.security import create_access_token
from app.exceptions import AuthError, ConflictError, NotFoundError, TokenError
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import TokenResponse


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _dummy_user(
    role: UserRole = UserRole.MEMBER,
    is_active: bool = True,
    email: str = "test@example.com",
) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email=email,
        full_name="Test User",
        role=role,
        is_active=is_active,
        hashed_password="somehashvalue",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Dependency: get_current_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_valid_token() -> None:
    """get_current_user returns active User when token is valid and user exists."""
    user = _dummy_user()
    token = create_access_token(
        subject=str(user.id),
        org_id=str(user.organization_id),
        role=user.role.value,
    )

    mock_db = MagicMock()
    with patch("app.api.deps.UserRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=user)
        mock_repo_cls.return_value = mock_repo

        result = await get_current_user(token=token, db=mock_db)
        assert result.id == user.id
        assert result.email == user.email
        mock_repo.get_by_id.assert_awaited_once_with(user.id)


@pytest.mark.asyncio
async def test_get_current_user_missing_sub() -> None:
    """get_current_user raises TokenError if subject claim is missing."""
    mock_db = MagicMock()
    with patch("app.api.deps.decode_access_token", return_value={"org": "org-id"}):
        with pytest.raises(TokenError, match="missing subject claim"):
            await get_current_user(token="mock-token", db=mock_db)


@pytest.mark.asyncio
async def test_get_current_user_invalid_uuid() -> None:
    """get_current_user raises TokenError if subject is not a valid UUID."""
    mock_db = MagicMock()
    with patch("app.api.deps.decode_access_token", return_value={"sub": "not-a-uuid"}):
        with pytest.raises(TokenError, match="valid UUID"):
            await get_current_user(token="mock-token", db=mock_db)


@pytest.mark.asyncio
async def test_get_current_user_user_not_found() -> None:
    """get_current_user raises AuthError if user is not in repository."""
    mock_db = MagicMock()
    valid_uuid = uuid.uuid4()
    with patch("app.api.deps.decode_access_token", return_value={"sub": str(valid_uuid)}), \
         patch("app.api.deps.UserRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        with pytest.raises(AuthError, match="User not found"):
            await get_current_user(token="mock-token", db=mock_db)


@pytest.mark.asyncio
async def test_get_current_user_inactive_user() -> None:
    """get_current_user raises AuthError if user is_active is False."""
    user = _dummy_user(is_active=False)
    mock_db = MagicMock()
    with patch("app.api.deps.decode_access_token", return_value={"sub": str(user.id)}), \
         patch("app.api.deps.UserRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=user)
        mock_repo_cls.return_value = mock_repo

        with pytest.raises(AuthError, match="User is inactive"):
            await get_current_user(token="mock-token", db=mock_db)


# ---------------------------------------------------------------------------
# Dependency: require_role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_role_allowed() -> None:
    """require_role returns user when current user has one of required roles."""
    admin_user = _dummy_user(role=UserRole.ADMIN)
    checker = require_role(UserRole.ADMIN, UserRole.OWNER)
    result = await checker(current_user=admin_user)
    assert result.id == admin_user.id


@pytest.mark.asyncio
async def test_require_role_forbidden() -> None:
    """require_role raises AuthError('insufficient permissions') when role is not in roles."""
    member_user = _dummy_user(role=UserRole.MEMBER)
    checker = require_role(UserRole.ADMIN, UserRole.OWNER)
    with pytest.raises(AuthError, match="insufficient permissions"):
        await checker(current_user=member_user)


# ---------------------------------------------------------------------------
# Endpoints: POST /v1/auth/register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_register_success() -> None:
    """POST /v1/auth/register returns 201 and UserRead on successful registration."""
    user = _dummy_user(email="newuser@example.com")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.api.v1.auth.AuthService") as mock_auth_service_cls:
            mock_svc = MagicMock()
            mock_svc.register = AsyncMock(return_value=user)
            mock_auth_service_cls.return_value = mock_svc

            payload = {
                "email": "newuser@example.com",
                "password": "strongpassword123",
                "full_name": "Test User",
                "organization_slug": "acme-corp",
                "role": "member",
            }
            response = await client.post("/v1/auth/register", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == str(user.id)
            assert data["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_endpoint_register_org_not_found() -> None:
    """POST /v1/auth/register returns 404 when organization does not exist."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.api.v1.auth.AuthService") as mock_auth_service_cls:
            mock_svc = MagicMock()
            mock_svc.register = AsyncMock(side_effect=NotFoundError("Organization not found."))
            mock_auth_service_cls.return_value = mock_svc

            payload = {
                "email": "user@example.com",
                "password": "strongpassword123",
                "organization_slug": "missing-org",
            }
            response = await client.post("/v1/auth/register", json=payload)
            assert response.status_code == 404
            assert response.json()["error"]["type"] == "NotFoundError"


@pytest.mark.asyncio
async def test_endpoint_register_conflict() -> None:
    """POST /v1/auth/register returns 409 on duplicate email."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.api.v1.auth.AuthService") as mock_auth_service_cls:
            mock_svc = MagicMock()
            mock_svc.register = AsyncMock(side_effect=ConflictError("Email already registered."))
            mock_auth_service_cls.return_value = mock_svc

            payload = {
                "email": "dup@example.com",
                "password": "strongpassword123",
                "organization_slug": "acme-corp",
            }
            response = await client.post("/v1/auth/register", json=payload)
            assert response.status_code == 409
            assert response.json()["error"]["type"] == "ConflictError"


@pytest.mark.asyncio
async def test_endpoint_register_short_password() -> None:
    """POST /v1/auth/register returns 422 if password < 8 characters."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "email": "user@example.com",
            "password": "short",
            "organization_slug": "acme-corp",
        }
        response = await client.post("/v1/auth/register", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Endpoints: POST /v1/auth/login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_login_success() -> None:
    """POST /v1/auth/login returns 200 and TokenResponse on valid credentials."""
    user = _dummy_user(email="login@example.com")
    token_resp = TokenResponse(
        access_token="test.jwt.token",
        token_type="bearer",
        expires_in=86400,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.api.v1.auth.AuthService") as mock_auth_service_cls:
            mock_svc = MagicMock()
            mock_svc.authenticate = AsyncMock(return_value=user)
            mock_svc.issue_token = MagicMock(return_value=token_resp)
            mock_auth_service_cls.return_value = mock_svc

            payload = {
                "email": "login@example.com",
                "password": "correctpassword123",
            }
            response = await client.post("/v1/auth/login", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "test.jwt.token"
            assert data["token_type"] == "bearer"
            assert data["expires_in"] == 86400


@pytest.mark.asyncio
async def test_endpoint_login_invalid_credentials() -> None:
    """POST /v1/auth/login returns 401 when authenticate raises AuthError."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.api.v1.auth.AuthService") as mock_auth_service_cls:
            mock_svc = MagicMock()
            mock_svc.authenticate = AsyncMock(side_effect=AuthError("Invalid credentials."))
            mock_auth_service_cls.return_value = mock_svc

            payload = {
                "email": "wrong@example.com",
                "password": "wrongpassword123",
            }
            response = await client.post("/v1/auth/login", json=payload)
            assert response.status_code == 401
            assert response.json()["error"]["type"] == "AuthError"


# ---------------------------------------------------------------------------
# Endpoints: GET /v1/auth/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_get_me_success() -> None:
    """GET /v1/auth/me returns 200 and MeResponse when authenticated."""
    user = _dummy_user(email="me@example.com")

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/auth/me")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(user.id)
            assert data["email"] == "me@example.com"
            assert data["organization_id"] == str(user.organization_id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_endpoint_get_me_unauthorized() -> None:
    """GET /v1/auth/me returns 401 when Authorization header is absent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/auth/me")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_endpoint_get_me_invalid_token() -> None:
    """GET /v1/auth/me returns 401 when invalid Bearer token is provided."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/auth/me",
            headers={"Authorization": "Bearer badtoken"},
        )
        assert response.status_code == 401
