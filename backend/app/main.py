import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import settings
from app.core.constants import REQUEST_ID_HEADER
from app.core.logging import (
    bind_request_id,
    clear_request_id,
    configure_logging,
    get_logger,
)
from app.db.session import engine

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to extract or generate X-Request-ID, bind to logging context, and set on response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not request_id:
            request_id = str(uuid.uuid4())

        bind_request_id(request_id)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            clear_request_id()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_logging()
    logger.info("prism starting")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connectivity verified")
    except Exception as exc:
        logger.error("Database connectivity check failed on startup", error=str(exc))
        if settings.APP_ENV != "dev":
            raise

    yield

    # Shutdown
    await engine.dispose()
    logger.info("prism stopping")


def create_app() -> FastAPI:
    """Application factory for Prism."""
    app = FastAPI(
        title=settings.APP_NAME,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        lifespan=lifespan,
    )

    # Attach request ID tracking middleware
    app.add_middleware(RequestIDMiddleware)

    # Mount top-level API router
    app.include_router(api_router)

    return app


app = create_app()
