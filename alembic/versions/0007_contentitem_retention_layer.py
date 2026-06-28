"""ContentItem: adiciona campo retention_layer JSONB.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column(
            "retention_layer",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment=(
                "Dados de retenção por camada do roteiro. "
                "Estrutura: {hook, development, climax, cta} cada um com "
                "{estimated_retention_pct, duration_target_s, score}."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("content_items", "retention_layer")
