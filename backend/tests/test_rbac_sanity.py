"""Tests for RBAC sanity check endpoint (GET /v1/admin/ping).

DEV-ONLY: Validates that require_role(UserRole.OWNER, UserRole.ADMIN) permits only
owner and admin users and denies member, viewer, and unauthenticated callers.
"""

from datetime import datetime, timezone
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.main import app
from app.models.enums import UserRole
from app.models.user import User


def _dummy_user(role: UserRole) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email=f"{role.value}@example.com",
        full_name=f"Test {role.value.capitalize()}",
        role=role,
        is_active=True,
        hashed_password="hashed_pw_test",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_admin_ping_owner_success() -> None:
    """GET /v1/admin/ping allows OWNER and returns {'pong': True, 'role': 'owner'}."""
    user = _dummy_user(role=UserRole.OWNER)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/admin/ping")
            assert response.status_code == 200
            data = response.json()
            assert data["pong"] is True
            assert data["role"] == "owner"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_ping_admin_success() -> None:
    """GET /v1/admin/ping allows ADMIN and returns {'pong': True, 'role': 'admin'}."""
    user = _dummy_user(role=UserRole.ADMIN)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/admin/ping")
            assert response.status_code == 200
            data = response.json()
            assert data["pong"] is True
            assert data["role"] == "admin"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_ping_member_forbidden() -> None:
    """GET /v1/admin/ping denies MEMBER with 401 insufficient permissions."""
    user = _dummy_user(role=UserRole.MEMBER)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/admin/ping")
            assert response.status_code == 401
            data = response.json()
            assert data["error"]["type"] == "AuthError"
            assert "insufficient permissions" in data["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_ping_viewer_forbidden() -> None:
    """GET /v1/admin/ping denies VIEWER with 401 insufficient permissions."""
    user = _dummy_user(role=UserRole.VIEWER)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/admin/ping")
            assert response.status_code == 401
            data = response.json()
            assert data["error"]["type"] == "AuthError"
            assert "insufficient permissions" in data["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_ping_unauthenticated() -> None:
    """GET /v1/admin/ping returns 401 when unauthenticated (no token)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/admin/ping")
        assert response.status_code == 401
