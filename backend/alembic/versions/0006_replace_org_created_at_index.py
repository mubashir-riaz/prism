"""Replace ix_traces_organization_id_created_at with ix_traces_org_created_at_id

Revision ID: 0006_replace_org_created_at_index
Revises: 0005_make_cost_usd_nullable
Create Date: 2026-11-09 23:14:00.000000

Context
-------
The GET /v1/traces list endpoint orders results by (created_at DESC, id DESC)
and uses a Postgres row-value cursor comparison:

    (created_at, id) < (:cursor_ts, :cursor_id)

The old index — ix_traces_organization_id_created_at on (organization_id, created_at DESC)
— satisfied the WHERE org = ? clause and helped with the created_at sort, but Postgres
still had to perform a separate re-sort on ``id`` at every page boundary because ``id``
was not part of the index.

The replacement index — ix_traces_org_created_at_id on
(organization_id, created_at DESC, id DESC) — covers the full ORDER BY and allows
Postgres to resolve the cursor predicate directly from the index without a filesort.

Hand-reviewed checklist
-----------------------
[x] DROP old index first (avoids a brief period with both indexes present and bloat).
[x] CREATE new index CONCURRENTLY would be ideal in production; op.create_index
    does not support CONCURRENTLY out of the box, so schedule this migration
    during a low-traffic window on large tables.
[x] downgrade() restores the original index exactly as migration 0003 created it.
[x] No data migration required — index-only change.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0006_replace_org_created_at_index"
down_revision: Union[str, None] = "0005_make_cost_usd_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the two-column index that lacks ``id``.
    op.drop_index("ix_traces_organization_id_created_at", table_name="traces")

    # Create the three-column index that covers the full ORDER BY clause used by
    # GET /v1/traces: WHERE organization_id = ? ORDER BY created_at DESC, id DESC.
    op.create_index(
        "ix_traces_org_created_at_id",
        "traces",
        ["organization_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    # Restore the original two-column index from migration 0003.
    op.drop_index("ix_traces_org_created_at_id", table_name="traces")

    op.create_index(
        "ix_traces_organization_id_created_at",
        "traces",
        ["organization_id", sa.text("created_at DESC")],
        unique=False,
    )
