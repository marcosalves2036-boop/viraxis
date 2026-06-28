"""Model: trend_snapshots — sinais de tendência coletados pelo SCOUT."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import UUIDPrimaryKeyMixin


class TrendSource(str, enum.Enum):
    scout_url = "scout_url"        # SCOUT baixou via yt-dlp
    vault_upload = "vault_upload"  # Kevin fez upload manual
    manual_input = "manual_input"  # Inserção via CLI/UI


class TrendSnapshot(UUIDPrimaryKeyMixin, Base):
    """
    Snapshot imutável de tendência. Não tem updated_at intencionalmente:
    cada nova coleta gera uma nova linha — preserva histórico de sinais.
    """

    __tablename__ = "trend_snapshots"
    __table_args__ = (
        Index("ix_trend_snapshots_office_captured", "office_id", "captured_at"),
        Index("ix_trend_snapshots_user_id", "user_id"),
        Index("ix_trend_snapshots_source", "source"),
        Index("ix_trend_snapshots_platform", "platform"),
        {"comment": "Sinais de tendência coletados — imutáveis, preservam histórico."},
    )

    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[TrendSource] = mapped_column(
        Enum(TrendSource, name="trendsource", create_constraint=True),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="URL original do vídeo referência (SCOUT mode).",
    )

    # ── 7 novos campos (migration 0006) ──────────────────────────────────
    # Promovidos do JSONB raw_metadata para buscas e ordenação eficientes

    platform: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=False,  # índice via __table_args__
        comment="Plataforma do vídeo original: youtube, tiktok, twitch, instagram.",
    )
    video_title: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="Título do vídeo original (promovido de raw_metadata).",
    )
    duration_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Duração do vídeo em segundos (promovido de raw_metadata).",
    )
    view_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
        comment="Views do vídeo original no momento da coleta.",
    )
    like_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Likes do vídeo original no momento da coleta.",
    )
    viral_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Score de viralidade calculado pelo SCOUT (0.0–1.0).",
    )
    seasonal_multiplier: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="1.0",
        comment="Multiplicador sazonal do BRAIN (ex.: 1.3 = alta temporada). Padrão 1.0.",
    )
    # ─────────────────────────────────────────────────────────────────────

    # Metadados brutos do yt-dlp / upload
    raw_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Output bruto do yt-dlp ou metadata do upload.",
    )
    # Sinais processados pelo SCOUT agent
    processed_signals: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Sinais extraídos: keywords, archetype, hook_pattern, engagement_rate.",
    )
    transcription: Mapped[str | None] = mapped_column(
        String, nullable=True,
        comment="Transcrição via faster-whisper (se disponível).",
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    office: Mapped["Office"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="trend_snapshots", lazy="raise"
    )
