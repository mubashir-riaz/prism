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


class TokenError(PrismException):
    """Raised when a JWT is missing, expired, or has an invalid signature."""

    pass


class AuthError(PrismException):
    """Raised on authentication failures (invalid credentials, inactive account).

    Deliberately non-specific: never distinguish "user not found" from "wrong
    password" to prevent user-enumeration attacks.
    """

    pass


# ---------------------------------------------------------------------------
# Dataset-specific exceptions
# ---------------------------------------------------------------------------


class DatasetNotFoundError(NotFoundError):
    """Raised when a dataset does not exist or belongs to a different org."""

    pass


class EmptyDatasetError(PrismException):
    """Raised when an uploaded JSONL file contains zero data rows."""

    pass


class FileTooLargeError(PrismException):
    """Raised when an uploaded file exceeds the maximum allowed byte size."""

    pass


class TooManyRowsError(PrismException):
    """Raised when an uploaded dataset exceeds MAX_ROWS."""

    pass


class RowValidationError(PrismException):
    """Raised when a dataset row fails DatasetRow schema validation.

    Attributes
    ----------
    line_number : int
        1-indexed line number of the offending row (matches editor line numbers).
    reason : str
        Human-readable description of the validation failure.
    """

    def __init__(self, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(
            f"Row {line_number} failed validation: {reason}",
            details={"line_number": line_number, "reason": reason},
        )


__all__ = [
    "PrismException",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "TokenError",
    "AuthError",
    # Dataset
    "DatasetNotFoundError",
    "EmptyDatasetError",
    "FileTooLargeError",
    "TooManyRowsError",
    "RowValidationError",
]
