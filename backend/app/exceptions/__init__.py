"""Prism domain exceptions."""

from typing import Any, Optional


class PrismException(Exception):
    """Base exception for all Prism domain errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(PrismException):
    """Raised when a requested resource is not found."""

    pass


class ConflictError(PrismException):
    """Raised when an operation conflicts with existing resource state (e.g. duplicate slug)."""

    pass


class ValidationError(PrismException):
    """Raised when domain business validation fails."""

    pass


__all__ = [
    "PrismException",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
]
