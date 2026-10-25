"""Tests for global domain exception handlers and standard error envelope formatting."""

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.exceptions import AuthError, ConflictError, NotFoundError, TokenError, ValidationError
from app.exceptions.handlers import register_exception_handlers
from app.main import app


# Test router to raise specific domain exceptions
dummy_errors_router = APIRouter(prefix="/test-errors")


@dummy_errors_router.get("/not-found")
async def raise_not_found():
    raise NotFoundError("The requested entity does not exist.", details={"resource": "item", "id": 123})


@dummy_errors_router.get("/conflict")
async def raise_conflict():
    raise ConflictError("A conflict occurred with an existing entity.", details={"field": "slug"})


@dummy_errors_router.get("/auth-error")
async def raise_auth_error():
    raise AuthError("Authentication failed or permissions insufficient.")


@dummy_errors_router.get("/token-error")
async def raise_token_error():
    raise TokenError("Token is malformed or signature is invalid.")


@dummy_errors_router.get("/validation-error")
async def raise_validation_error():
    raise ValidationError("Input validation failed.", details={"field": "name", "issue": "too_short"})


# Include router once for tests
app.include_router(dummy_errors_router)


@pytest.mark.asyncio
async def test_not_found_error_handler_standard_body(client: AsyncClient) -> None:
    """NotFoundError returns 404 with standard error body shape."""
    response = await client.get("/test-errors/not-found")
    assert response.status_code == 404

    body = response.json()
    assert body == {
        "error": {
            "type": "NotFoundError",
            "message": "The requested entity does not exist.",
            "details": {"resource": "item", "id": 123},
        }
    }


@pytest.mark.asyncio
async def test_conflict_error_handler_standard_body(client: AsyncClient) -> None:
    """ConflictError returns 409 with standard error body shape."""
    response = await client.get("/test-errors/conflict")
    assert response.status_code == 409

    body = response.json()
    assert body == {
        "error": {
            "type": "ConflictError",
            "message": "A conflict occurred with an existing entity.",
            "details": {"field": "slug"},
        }
    }


@pytest.mark.asyncio
async def test_auth_error_handler_standard_body_and_header(client: AsyncClient) -> None:
    """AuthError returns 401 with standard error body and WWW-Authenticate: Bearer header."""
    response = await client.get("/test-errors/auth-error")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

    body = response.json()
    assert body == {
        "error": {
            "type": "AuthError",
            "message": "Authentication failed or permissions insufficient.",
            "details": {},
        }
    }


@pytest.mark.asyncio
async def test_token_error_handler_standard_body_and_header(client: AsyncClient) -> None:
    """TokenError returns 401 with standard error body and WWW-Authenticate: Bearer header."""
    response = await client.get("/test-errors/token-error")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

    body = response.json()
    assert body == {
        "error": {
            "type": "TokenError",
            "message": "Token is malformed or signature is invalid.",
            "details": {},
        }
    }


@pytest.mark.asyncio
async def test_validation_error_handler_standard_body(client: AsyncClient) -> None:
    """ValidationError returns 422 with standard error body shape."""
    response = await client.get("/test-errors/validation-error")
    assert response.status_code == 422

    body = response.json()
    assert body == {
        "error": {
            "type": "ValidationError",
            "message": "Input validation failed.",
            "details": {"field": "name", "issue": "too_short"},
        }
    }
