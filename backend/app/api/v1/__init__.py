from .auth import router as auth_router
from .health import router as health_router
from .router import api_v1_router

__all__ = ["api_v1_router", "auth_router", "health_router"]
