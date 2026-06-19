"""Model: performance_metrics — métricas de desempenho por conteúdo e plataforma."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import UUIDPrimaryKeyMixin
from viraxis.domain.models.social_account import SocialPlatform


class PerformanceMetric(UUIDPrimaryKeyMixin, Base):
    """
    Snapshot de métricas em um ponto no tempo.
    Imutável: cada coleta = nova linha. Permite análise de crescimento temporal.
    """

    __tablename__ = "performance_metrics"
    __table_args__ = (
        Index("ix_perf_metrics_content_item", "content_item_id", "recorded_at"),
        Index("ix_perf_metrics_office_platform", "office_id", "platform"),
        Index("ix_perf_metrics_user_id", "user_id"),
        {"comment": "Snapshots de métricas por conteúdo/plataforma — imutáveis."},
    )

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
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
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(SocialPlatform, name="socialplatform", create_constraint=False),
        nullable=False,
    )

    # Métricas brutas
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    likes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    comments: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    shares: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    saves: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    watch_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="% médio de visualização completa (0.0–1.0).",
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    content_item: Mapped["ContentItem"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ContentItem", back_populates="performance_metrics", lazy="raise"
    )
