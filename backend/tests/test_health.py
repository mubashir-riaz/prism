"""Tests for health checks and application startup."""

import pytest
from httpx import AsyncClient

from app.core.constants import REQUEST_ID_HEADER


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    """GET /health returns 200 and body {'status': 'ok'}."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_ok(client: AsyncClient) -> None:
    """GET /health/ready returns 200 when DB is up."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "db": "ok"}


@pytest.mark.asyncio
async def test_request_id_header_present(client: AsyncClient) -> None:
    """Response includes X-Request-ID header."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert len(response.headers[REQUEST_ID_HEADER]) > 0

    # Verify custom X-Request-ID is preserved if supplied
    custom_request_id = "test-req-id-12345"
    custom_response = await client.get(
        "/health",
        headers={REQUEST_ID_HEADER: custom_request_id},
    )
    assert custom_response.status_code == 200
    assert custom_response.headers.get(REQUEST_ID_HEADER) == custom_request_id
