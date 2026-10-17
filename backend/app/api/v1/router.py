from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router

api_v1_router = APIRouter()

# Health endpoints (/v1/health, /v1/health/ready) and domain routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
