from enum import Enum


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Pagination
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100

# HTTP & Tracing
REQUEST_ID_HEADER: str = "X-Request-ID"
