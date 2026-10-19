from .admin import router as admin_router
from .auth import router as auth_router
from .health import router as health_router
from .keys import router as keys_router
from .router import api_v1_router

__all__ = ["admin_router", "api_v1_router", "auth_router", "health_router", "keys_router"]
