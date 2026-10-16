import logging
import sys
from contextvars import ContextVar
from typing import Any, MutableMapping, Optional

import structlog

from app.core.config import settings

# Context variable for request ID tracking across async calls
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def bind_request_id(request_id: str) -> None:
    """Bind a request ID to ContextVar and structlog context variables."""
    request_id_ctx.set(request_id)
    structlog.contextvars.bind_contextvars(request_id=request_id)


def get_request_id() -> Optional[str]:
    """Retrieve the current request ID."""
    return request_id_ctx.get()


def clear_request_id() -> None:
    """Clear the active request ID."""
    request_id_ctx.set(None)
    try:
        structlog.contextvars.unbind_contextvars("request_id")
    except KeyError:
        pass


def _rename_event_to_message(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Rename structlog's default 'event' key to 'message'."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _add_request_id(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Inject request_id into the log event if set in ContextVar."""
    req_id = request_id_ctx.get()
    if req_id and "request_id" not in event_dict:
        event_dict["request_id"] = req_id
    return event_dict


def configure_logging() -> None:
    """Configure structured JSON logging for the application and standard library."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _rename_event_to_message,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Route framework loggers through the structured formatter
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        framework_logger = logging.getLogger(logger_name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger instance."""
    return structlog.get_logger(name)
