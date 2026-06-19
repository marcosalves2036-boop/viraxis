"""content_items fase2 — adiciona deleted_at para soft delete.

Revision ID: 0003_content_items_fase2
Revises: 0002_add_user_role
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_content_items_fase2"
down_revision: str = "0002_add_user_role"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Adiciona deleted_at para soft delete no ContentItem
    op.add_column(
        "content_items",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_content_items_deleted_at",
        "content_items",
        ["deleted_at"],
    )
    # Index parcial para queries de itens ativos (deleted_at IS NULL) — PostgreSQL
    op.execute(
        """
        CREATE INDEX ix_content_items_office_active
        ON content_items (office_id, status)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_content_items_office_active")
    op.drop_index("ix_content_items_deleted_at", table_name="content_items")
    op.drop_column("content_items", "deleted_at")
