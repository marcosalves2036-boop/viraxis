"""TrendSnapshot: 7 novos campos — platform, video_title, duration_seconds, view_count, like_count, viral_score, seasonal_multiplier.

Revision ID: 0006
Revises: 0005_add_facebook_platform
Create Date: 2026-06-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # platform — promovido de raw_metadata["platform"]
    op.add_column(
        "trend_snapshots",
        sa.Column("platform", sa.String(32), nullable=True,
                  comment="Plataforma do vídeo original: youtube, tiktok, twitch, instagram."),
    )

    # video_title — promovido de raw_metadata["title"]
    op.add_column(
        "trend_snapshots",
        sa.Column("video_title", sa.String(512), nullable=True,
                  comment="Título do vídeo original (promovido de raw_metadata)."),
    )

    # duration_seconds — promovido de raw_metadata["duration_seconds"]
    op.add_column(
        "trend_snapshots",
        sa.Column("duration_seconds", sa.Float(), nullable=True,
                  comment="Duração do vídeo em segundos (promovido de raw_metadata)."),
    )

    # view_count — promovido de raw_metadata["view_count"]
    op.add_column(
        "trend_snapshots",
        sa.Column("view_count", sa.BigInteger(), nullable=True,
                  comment="Views do vídeo original no momento da coleta."),
    )

    # like_count — promovido de raw_metadata["like_count"]
    op.add_column(
        "trend_snapshots",
        sa.Column("like_count", sa.Integer(), nullable=True,
                  comment="Likes do vídeo original no momento da coleta."),
    )

    # viral_score — score calculado 0.0–1.0
    op.add_column(
        "trend_snapshots",
        sa.Column("viral_score", sa.Float(), nullable=True,
                  comment="Score de viralidade calculado pelo SCOUT (0.0–1.0)."),
    )

    # seasonal_multiplier — para uso do BRAIN, padrão 1.0
    op.add_column(
        "trend_snapshots",
        sa.Column("seasonal_multiplier", sa.Float(), nullable=True,
                  server_default="1.0",
                  comment="Multiplicador sazonal do BRAIN (ex.: 1.3 = alta temporada). Padrão 1.0."),
    )

    # Índice em platform para queries de filtragem
    op.create_index(
        "ix_trend_snapshots_platform",
        "trend_snapshots",
        ["platform"],
    )

    # Backfill: promover dados já existentes em raw_metadata para as novas colunas
    op.execute("""
        UPDATE trend_snapshots
        SET
            platform         = raw_metadata->>'platform',
            video_title      = LEFT(raw_metadata->>'title', 512),
            duration_seconds = (raw_metadata->>'duration_seconds')::FLOAT,
            view_count       = (raw_metadata->>'view_count')::BIGINT,
            like_count       = (raw_metadata->>'like_count')::INT,
            viral_score      = 0.5,
            seasonal_multiplier = 1.0
        WHERE platform IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_trend_snapshots_platform", table_name="trend_snapshots")
    op.drop_column("trend_snapshots", "seasonal_multiplier")
    op.drop_column("trend_snapshots", "viral_score")
    op.drop_column("trend_snapshots", "like_count")
    op.drop_column("trend_snapshots", "view_count")
    op.drop_column("trend_snapshots", "duration_seconds")
    op.drop_column("trend_snapshots", "video_title")
    op.drop_column("trend_snapshots", "platform")
