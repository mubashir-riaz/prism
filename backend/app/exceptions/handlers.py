"""
Prism exception → HTTP response handlers.

All error responses share the same JSON envelope:

    {
        "error": {
            "type":    "<ExceptionClassName>",
            "message": "<human-readable message>",
            "details": { ... }          # always a dict, may be empty
        }
    }

Register everything by calling ``register_exception_handlers(app)``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import (
    AuthError,
    ConflictError,
    NotFoundError,
    PrismException,
    TokenError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _error_body(exc: PrismException) -> dict:
    """Build the standard ``{"error": {...}}`` envelope from a domain exception."""
    return {
        "error": {
            "type": type(exc).__name__,
            "message": exc.message,
            "details": exc.details,
        }
    }


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------


async def _handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content=_error_body(exc))


async def _handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content=_error_body(exc))


async def _handle_validation(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content=_error_body(exc))


async def _handle_auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_error_body(exc),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _handle_token_error(request: Request, exc: TokenError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_error_body(exc),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _handle_prism_exception(request: Request, exc: PrismException) -> JSONResponse:
    """Catch-all for any PrismException subclass not matched above → HTTP 400."""
    return JSONResponse(status_code=400, content=_error_body(exc))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all domain-exception handlers to *app*.

    Order matters: more-specific subclasses must be registered **before**
    the ``PrismException`` catch-all so FastAPI routes to the right handler.
    """
    app.add_exception_handler(NotFoundError, _handle_not_found)       # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, _handle_conflict)         # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, _handle_validation)     # type: ignore[arg-type]
    app.add_exception_handler(AuthError, _handle_auth_error)           # type: ignore[arg-type]
    app.add_exception_handler(TokenError, _handle_token_error)         # type: ignore[arg-type]
    # Catch-all — must be last
    app.add_exception_handler(PrismException, _handle_prism_exception) # type: ignore[arg-type]
