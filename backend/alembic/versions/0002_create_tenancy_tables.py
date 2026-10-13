"""create tenancy tables

Revision ID: 0002_create_tenancy_tables
Revises: 0001_init
Create Date: 2026-10-13 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_create_tenancy_tables"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. organizations table
    op.create_table(
        "organizations",
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
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_index(
        op.f("ix_organizations_slug"),
        "organizations",
        ["slug"],
        unique=True,
    )

    # 2. users table
    op.create_table(
        "users",
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "hashed_password",
            sa.String(length=255),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_users_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(
        op.f("ix_users_organization_id"),
        "users",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_users_email"),
        "users",
        ["email"],
        unique=True,
    )

    # 3. projects table
    op.create_table(
        "projects",
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_projects_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_projects_organization_id_slug",
        ),
    )
    op.create_index(
        op.f("ix_projects_organization_id"),
        "projects",
        ["organization_id"],
        unique=False,
    )

    # 4. environments table
    op.create_table(
        "environments",
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
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_environments_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environments")),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_environments_project_id_name",
        ),
    )
    op.create_index(
        op.f("ix_environments_project_id"),
        "environments",
        ["project_id"],
        unique=False,
    )

    # 5. api_keys table
    op.create_table(
        "api_keys",
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
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("hashed_key", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_api_keys_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_api_keys_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
    )
    op.create_index(
        op.f("ix_api_keys_environment_id"),
        "api_keys",
        ["environment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_keys_key_prefix"),
        "api_keys",
        ["key_prefix"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_keys_project_id"),
        "api_keys",
        ["project_id"],
        unique=False,
    )

    # 6. audit_logs table
    op.create_table(
        "audit_logs",
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=255), nullable=True),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_logs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        op.f("ix_audit_logs_action"),
        "audit_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id"),
        "audit_logs",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_organization_id"),
        "audit_logs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_organization_id_created_at",
        "audit_logs",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_resource_id"),
        "audit_logs",
        ["resource_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_resource_type"),
        "audit_logs",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_resource_type_resource_id",
        "audit_logs",
        ["resource_type", "resource_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop audit_logs
    op.drop_index(
        "ix_audit_logs_resource_type_resource_id",
        table_name="audit_logs",
    )
    op.drop_index(
        op.f("ix_audit_logs_resource_type"),
        table_name="audit_logs",
    )
    op.drop_index(
        op.f("ix_audit_logs_resource_id"),
        table_name="audit_logs",
    )
    op.drop_index(
        "ix_audit_logs_organization_id_created_at",
        table_name="audit_logs",
    )
    op.drop_index(
        op.f("ix_audit_logs_organization_id"),
        table_name="audit_logs",
    )
    op.drop_index(
        op.f("ix_audit_logs_actor_user_id"),
        table_name="audit_logs",
    )
    op.drop_index(
        op.f("ix_audit_logs_action"),
        table_name="audit_logs",
    )
    op.drop_table("audit_logs")

    # Drop api_keys
    op.drop_index(
        op.f("ix_api_keys_project_id"),
        table_name="api_keys",
    )
    op.drop_index(
        op.f("ix_api_keys_key_prefix"),
        table_name="api_keys",
    )
    op.drop_index(
        op.f("ix_api_keys_environment_id"),
        table_name="api_keys",
    )
    op.drop_table("api_keys")

    # Drop environments
    op.drop_index(
        op.f("ix_environments_project_id"),
        table_name="environments",
    )
    op.drop_table("environments")

    # Drop projects
    op.drop_index(
        op.f("ix_projects_organization_id"),
        table_name="projects",
    )
    op.drop_table("projects")

    # Drop users
    op.drop_index(
        op.f("ix_users_email"),
        table_name="users",
    )
    op.drop_index(
        op.f("ix_users_organization_id"),
        table_name="users",
    )
    op.drop_table("users")

    # Drop organizations
    op.drop_index(
        op.f("ix_organizations_slug"),
        table_name="organizations",
    )
    op.drop_table("organizations")
