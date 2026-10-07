"""Base model and mixins for SQLAlchemy 2.x domain models."""

from datetime import datetime
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class TimestampedBase:
    """Mixin class providing UUID primary key and timezone-aware timestamps.

    Attributes:
        id: UUID primary key, defaulting to uuid4.
        created_at: Creation timestamp with timezone, server default func.now().
        updated_at: Last update timestamp with timezone, server default and onupdate func.now().
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base, TimestampedBase):
    """Abstract declarative base class combining Base and TimestampedBase."""

    __abstract__ = True
