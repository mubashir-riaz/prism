from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.x declarative models."""
    pass


# Re-export the mixin and abstract base from models.base
from app.models.base import BaseModel, TimestampedBase  # noqa: E402, F401

__all__ = ["Base", "TimestampedBase", "BaseModel"]
