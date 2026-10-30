from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.keys import router as keys_router
from app.api.v1.traces import router as traces_router

api_v1_router = APIRouter()

# Health endpoints (/v1/health, /v1/health/ready) and domain routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(keys_router, prefix="/keys", tags=["api-keys"])
api_v1_router.include_router(traces_router, prefix="/traces", tags=["traces"])
# DEV-ONLY: Admin router for smoke testing RBAC
api_v1_router.include_router(admin_router, prefix="/admin", tags=["admin"])

