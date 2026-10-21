"""Tests for Role-Based Access Control (RBAC) enforcement on protected routes."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_require_role_blocks_member_from_admin_ping(
    member_client: AsyncClient,
) -> None:
    """require_role blocks MEMBER from /v1/admin/ping and returns standard error body shape."""
    response = await member_client.get("/v1/admin/ping")
    assert response.status_code == 401

    body = response.json()
    assert "error" in body
    assert body["error"]["type"] == "AuthError"
    assert body["error"]["message"] == "insufficient permissions"
    assert isinstance(body["error"]["details"], dict)


@pytest.mark.asyncio
async def test_require_role_allows_owner_on_admin_ping(
    auth_client: AsyncClient,
) -> None:
    """require_role allows OWNER on /v1/admin/ping and returns 200 with role."""
    response = await auth_client.get("/v1/admin/ping")
    assert response.status_code == 200

    body = response.json()
    assert body == {"pong": True, "role": "owner"}


@pytest.mark.asyncio
async def test_require_role_allows_admin_on_admin_ping(
    admin_client: AsyncClient,
) -> None:
    """require_role allows ADMIN on /v1/admin/ping and returns 200 with role."""
    response = await admin_client.get("/v1/admin/ping")
    assert response.status_code == 200

    body = response.json()
    assert body == {"pong": True, "role": "admin"}


@pytest.mark.asyncio
async def test_require_role_blocks_viewer_from_admin_ping(
    viewer_client: AsyncClient,
) -> None:
    """require_role blocks VIEWER from /v1/admin/ping with standard error body."""
    response = await viewer_client.get("/v1/admin/ping")
    assert response.status_code == 401

    body = response.json()
    assert body["error"]["type"] == "AuthError"
    assert body["error"]["message"] == "insufficient permissions"


@pytest.mark.asyncio
async def test_unauthenticated_request_to_admin_ping_blocked(
    client: AsyncClient,
) -> None:
    """Unauthenticated request to /v1/admin/ping returns 401."""
    response = await client.get("/v1/admin/ping")
    assert response.status_code == 401
