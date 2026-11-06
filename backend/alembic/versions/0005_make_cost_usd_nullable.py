"""make traces.cost_usd nullable

Revision ID: 0005_make_cost_usd_nullable
Revises: 0004_create_model_pricing_table
Create Date: 2026-11-05 18:30:00.000000

Context
-------
``cost_usd`` was originally created as ``nullable=True`` in migration 0003, so
this migration is a safety/idempotency guard that makes the intent explicit and
ensures any environment where the column was erroneously created NOT NULL is
corrected without data loss.

The corresponding application change is in ``trace_service.create_trace``:
when the caller omits ``cost_usd`` the service now auto-computes it from
``model_pricing``; if the model has no pricing row it falls back to NULL.

Hand-reviewed checklist
-----------------------
[x] ALTER COLUMN ... DROP NOT NULL — safe on PostgreSQL; existing NULL rows unaffected.
[x] downgrade() restores NOT NULL (requires no existing NULL rows; safe in dev/test).
[x] No data migration required — column was already nullable in the ORM model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_make_cost_usd_nullable"
down_revision: Union[str, None] = "0004_create_model_pricing_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure the column accepts NULL values.
    # This is a no-op if the column is already nullable (idempotent on Postgres).
    op.alter_column(
        "traces",
        "cost_usd",
        existing_type=sa.Numeric(precision=12, scale=6),
        nullable=True,
    )


def downgrade() -> None:
    # Restore NOT NULL constraint.
    # WARNING: this will fail if any rows contain a NULL cost_usd value.
    # Backfill NULLs with 0 before running downgrade in production.
    op.alter_column(
        "traces",
        "cost_usd",
        existing_type=sa.Numeric(precision=12, scale=6),
        nullable=False,
    )
