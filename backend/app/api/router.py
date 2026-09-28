from fastapi import APIRouter

from app.api.v1.router import api_v1_router
from app.core.config import settings

api_router = APIRouter()

# Root-level health router (for health checks at root level, e.g. /health)
health_router = APIRouter(tags=["Health"])
api_router.include_router(health_router)

# Mount versioned API router under configured prefix (e.g. /v1)
api_router.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
