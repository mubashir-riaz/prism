"""create traces table

Revision ID: 0003_create_traces_table
Revises: 0002_create_tenancy_tables
Create Date: 2026-10-28 20:47:00.000000

Hand-reviewed checklist
-----------------------
[x] api_key_id uses ondelete="SET NULL"  (traces survive key rotation)
[x] cost_usd is Numeric(12, 6)           (not Float — avoids precision loss)
[x] metadata_json is JSONB with server_default='{}'
[x] All 4 composite indexes present:
      ix_traces_project_id_created_at
      ix_traces_feature_created_at
      ix_traces_model_created_at
      ix_traces_organization_id_created_at
[x] Simple FK indexes present for all FK columns
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0003_create_traces_table"
down_revision: Union[str, None] = "0002_create_tenancy_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "traces",
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
        # Foreign key columns
        # -----------------------------------------------------------------
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        # Nullable — SET NULL when the API key is deleted (key rotation).
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        # -----------------------------------------------------------------
        # Correlation / feature metadata
        # -----------------------------------------------------------------
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("feature", sa.String(length=64), nullable=False),
        # -----------------------------------------------------------------
        # LLM call data
        # -----------------------------------------------------------------
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("completion", sa.Text(), nullable=False),
        # -----------------------------------------------------------------
        # Token accounting
        # -----------------------------------------------------------------
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        # -----------------------------------------------------------------
        # Performance / cost
        # -----------------------------------------------------------------
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        # Numeric(12, 6) — never Float; preserves sub-cent precision.
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        # -----------------------------------------------------------------
        # Prompt versioning
        # -----------------------------------------------------------------
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        # -----------------------------------------------------------------
        # Arbitrary metadata — JSONB with server default '{}'
        # -----------------------------------------------------------------
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        # -----------------------------------------------------------------
        # Constraints
        # -----------------------------------------------------------------
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_traces_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_traces_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_traces_environment_id_environments"),
            ondelete="CASCADE",
        ),
        # SET NULL — traces survive API key deletion / rotation.
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_keys.id"],
            name=op.f("fk_traces_api_key_id_api_keys"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_traces")),
    )

    # -----------------------------------------------------------------
    # Single-column FK indexes (for join performance)
    # -----------------------------------------------------------------
    op.create_index(
        op.f("ix_traces_organization_id"),
        "traces",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traces_project_id"),
        "traces",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traces_environment_id"),
        "traces",
        ["environment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traces_api_key_id"),
        "traces",
        ["api_key_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traces_request_id"),
        "traces",
        ["request_id"],
        unique=False,
    )

    # -----------------------------------------------------------------
    # Composite analytical indexes (DESC on created_at for recency queries)
    # -----------------------------------------------------------------
    op.create_index(
        "ix_traces_project_id_created_at",
        "traces",
        ["project_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_traces_feature_created_at",
        "traces",
        ["feature", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_traces_model_created_at",
        "traces",
        ["model", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_traces_organization_id_created_at",
        "traces",
        ["organization_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    # Drop composite analytical indexes
    op.drop_index("ix_traces_organization_id_created_at", table_name="traces")
    op.drop_index("ix_traces_model_created_at", table_name="traces")
    op.drop_index("ix_traces_feature_created_at", table_name="traces")
    op.drop_index("ix_traces_project_id_created_at", table_name="traces")

    # Drop single-column indexes
    op.drop_index(op.f("ix_traces_request_id"), table_name="traces")
    op.drop_index(op.f("ix_traces_api_key_id"), table_name="traces")
    op.drop_index(op.f("ix_traces_environment_id"), table_name="traces")
    op.drop_index(op.f("ix_traces_project_id"), table_name="traces")
    op.drop_index(op.f("ix_traces_organization_id"), table_name="traces")

    op.drop_table("traces")
