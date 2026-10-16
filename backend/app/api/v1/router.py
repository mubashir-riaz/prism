from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_v1_router = APIRouter()

# Health endpoints (/v1/health, /v1/health/ready) and future domain routers
api_v1_router.include_router(health_router)
