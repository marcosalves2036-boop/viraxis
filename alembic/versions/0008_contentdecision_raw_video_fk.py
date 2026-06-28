"""ContentDecision: FK raw_video_id → raw_videos (ondelete SET NULL).

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_decisions",
        sa.Column(
            "raw_video_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Vídeo bruto de referência para o RENDERER usar como contexto de estilo.",
        ),
    )
    op.create_foreign_key(
        "fk_content_decisions_raw_video_id",
        "content_decisions",
        "raw_videos",
        ["raw_video_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_content_decisions_raw_video_id",
        "content_decisions",
        ["raw_video_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_content_decisions_raw_video_id", table_name="content_decisions")
    op.drop_constraint(
        "fk_content_decisions_raw_video_id", "content_decisions", type_="foreignkey"
    )
    op.drop_column("content_decisions", "raw_video_id")
