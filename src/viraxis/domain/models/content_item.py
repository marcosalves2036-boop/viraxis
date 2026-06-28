"""Model: content_items — videos produzidos pelo pipeline."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class ContentStatus(str, enum.Enum):
    draft = "draft"
    rendering = "rendering"
    review = "review"
    ready = "ready"
    published = "published"
    failed = "failed"


class ContentItem(BaseModelMixin, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        Index("ix_content_items_office_status", "office_id", "status"),
        Index("ix_content_items_user_id", "user_id"),
        Index("ix_content_items_decision_id", "decision_id"),
        {"comment": "Videos produzidos — cada item rastreia decisao, roteiro, artefatos e publicacao."},
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
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_decisions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Nulo se conteudo foi criado manualmente (fora do BRAIN).",
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    script: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Roteiro completo: gancho/desenvolvimento/climax/final.",
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="contentstatus", create_constraint=True),
        nullable=False,
        default=ContentStatus.draft,
        server_default=ContentStatus.draft.value,
    )

    # Armazenamento no Cloudflare R2
    storage_path: Mapped[str | None] = mapped_column(
        String(1024), nullable=True,
        comment="Caminho no R2: offices/{office_id}/videos/{item_id}.mp4",
    )
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Metadados de producao
    production_meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Parametros de geracao: voz TTS, musica, template visual.",
    )
    # Plataformas onde foi publicado e respectivos IDs externos
    publication_log: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
        comment="[{platform, external_id, published_at, url}]",
    )

    # Camadas de retenção para analytics do Renderer (migration 0007)
    retention_layer: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment=(
            "Dados de retenção por camada do roteiro. "
            "Estrutura: {hook, development, climax, cta} cada um com "
            "{estimated_retention_pct, duration_target_s, score}. "
            "Preenchido pelo RENDERER para orientar otimizações."
        ),
    )

    # Soft delete — PR-1 Fase 2
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
        comment="Preenchido no soft delete — item nao aparece nas listagens normais.",
    )

    # Relationships
    office: Mapped["Office"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="content_items", lazy="raise"
    )
    decision: Mapped["ContentDecision | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ContentDecision", back_populates="content_items", lazy="raise"
    )
    performance_metrics: Mapped[list["PerformanceMetric"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "PerformanceMetric", back_populates="content_item", lazy="raise"
    )
