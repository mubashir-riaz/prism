"""Add datasets and dataset_versions tables

Revision ID: 0007_add_dataset_tables
Revises: 0006_replace_org_created_at_index
Create Date: 2026-11-18 23:49:00.000000

Schema introduced
-----------------
datasets
    id               UUID PK
    org_id           UUID FK → organizations.id  CASCADE  NOT NULL  indexed
    project_id       UUID FK → projects.id        CASCADE  NOT NULL  indexed
    name             VARCHAR(200) NOT NULL
    created_at       TIMESTAMPTZ NOT NULL  server_default now()
    updated_at       TIMESTAMPTZ NOT NULL  server_default now()
    UNIQUE (org_id, project_id, name)

dataset_versions
    id               UUID PK
    dataset_id       UUID FK → datasets.id  CASCADE  NOT NULL  indexed
    version_number   INTEGER NOT NULL
    content_hash     VARCHAR(64) NOT NULL   -- SHA-256 hex
    row_count        INTEGER NOT NULL
    rows             JSONB NOT NULL
    created_at       TIMESTAMPTZ NOT NULL  server_default now()
    UNIQUE (dataset_id, version_number)    -- no duplicate version numbers
    UNIQUE (dataset_id, content_hash)      -- idempotency: same file = same hash
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0007_add_dataset_tables"
down_revision: Union[str, None] = "0006_replace_org_created_at_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # datasets
    # ------------------------------------------------------------------
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "name",
            name="uq_datasets_org_project_name",
        ),
    )
    op.create_index("ix_datasets_org_id", "datasets", ["org_id"])
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])

    # ------------------------------------------------------------------
    # dataset_versions
    # ------------------------------------------------------------------
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column(
            "rows",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON, "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "version_number",
            name="uq_dataset_versions_dataset_version_number",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "content_hash",
            name="uq_dataset_versions_dataset_content_hash",
        ),
    )
    op.create_index(
        "ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"]
    )


def downgrade() -> None:
    # Remove in reverse dependency order.
    op.drop_index("ix_dataset_versions_dataset_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")

    op.drop_index("ix_datasets_project_id", table_name="datasets")
    op.drop_index("ix_datasets_org_id", table_name="datasets")
    op.drop_table("datasets")
