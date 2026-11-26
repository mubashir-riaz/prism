"""Add eval_configs table

Revision ID: 0008_add_eval_config_table
Revises: 0007_add_dataset_tables
Create Date: 2026-11-26 00:00:00.000000

Schema introduced
-----------------
eval_configs
    id               UUID PK
    org_id           UUID FK → organizations.id  CASCADE  NOT NULL  indexed
    project_id       UUID FK → projects.id        CASCADE  NOT NULL  indexed
    name             VARCHAR(200) NOT NULL
    evaluators       JSONB NOT NULL  server_default '[]'
    created_at       TIMESTAMPTZ NOT NULL  server_default now()
    updated_at       TIMESTAMPTZ NOT NULL  server_default now()
    UNIQUE (org_id, project_id, name)      -- one config name per project
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0008_add_eval_config_table"
down_revision: Union[str, None] = "0007_add_dataset_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_configs",
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
            "evaluators",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON, "sqlite"),
            nullable=False,
            server_default="[]",
        ),
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
            name="uq_eval_configs_org_project_name",
        ),
    )
    op.create_index("ix_eval_configs_org_id", "eval_configs", ["org_id"])
    op.create_index("ix_eval_configs_project_id", "eval_configs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_configs_project_id", table_name="eval_configs")
    op.drop_index("ix_eval_configs_org_id", table_name="eval_configs")
    op.drop_table("eval_configs")
