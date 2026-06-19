"""Model: trend_snapshots — sinais de tendência coletados pelo SCOUT."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
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
