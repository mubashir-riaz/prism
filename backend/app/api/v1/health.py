from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Pure liveness check - returns 200 OK without touching the database."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Readiness probe that executes SELECT 1 to verify database reachability."""
    try:
        await db.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "db": "ok"},
        )
    except Exception as exc:
        logger.error("Readiness check failed - database unreachable", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unready", "db": "error"},
        )
