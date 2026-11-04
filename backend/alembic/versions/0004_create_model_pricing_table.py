"""create model_pricing table

Revision ID: 0004_create_model_pricing_table
Revises: 0003_create_traces_table
Create Date: 2026-11-04 23:37:00.000000

Hand-reviewed checklist
-----------------------
[x] input_price_per_1k / output_price_per_1k use Numeric(10, 6) — not Float
[x] Unique constraint on (provider, model): uq_model_pricing_provider_model
[x] Single-column indexes on provider and model for lookup performance
[x] downgrade() fully reverses upgrade() — drops indexes then table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_create_model_pricing_table"
down_revision: Union[str, None] = "0003_create_traces_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        # -----------------------------------------------------------------
        # Primary key + timestamps (TimestampedBase columns)
        # -----------------------------------------------------------------
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # -----------------------------------------------------------------
        # Provider / model identity
        # -----------------------------------------------------------------
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        # -----------------------------------------------------------------
        # Pricing — Numeric(10, 6): never Float; preserves sub-cent precision.
        # -----------------------------------------------------------------
        sa.Column("input_price_per_1k", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("output_price_per_1k", sa.Numeric(precision=10, scale=6), nullable=False),
        # -----------------------------------------------------------------
        # Constraints
        # -----------------------------------------------------------------
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_pricing")),
        sa.UniqueConstraint(
            "provider",
            "model",
            name="uq_model_pricing_provider_model",
        ),
    )

    # -----------------------------------------------------------------
    # Single-column indexes for fast provider/model lookups
    # -----------------------------------------------------------------
    op.create_index(
        op.f("ix_model_pricing_provider"),
        "model_pricing",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_pricing_model"),
        "model_pricing",
        ["model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_model_pricing_model"), table_name="model_pricing")
    op.drop_index(op.f("ix_model_pricing_provider"), table_name="model_pricing")
    op.drop_table("model_pricing")
