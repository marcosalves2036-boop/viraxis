"""raw_videos: adiciona campo ai_analysis (JSONB) para análise automática de IA.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_videos",
        sa.Column(
            "ai_analysis",
            JSONB,
            nullable=True,
            comment=(
                "Análise IA gerada no upload: transcrição Whisper com timestamps, "
                "análise visual cena-a-cena via Gemini 1.5 Flash, metadados técnicos."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("raw_videos", "ai_analysis")
