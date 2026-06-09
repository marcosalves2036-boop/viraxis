"""Model: content_items — vídeos produzidos pelo pipeline."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class ContentStatus(str, enum.Enum):
    draft = "draft"           # Roteiro gerado, ainda não renderizado
    rendering = "rendering"   # Pipeline de vídeo rodando
    ready = "ready"           # Vídeo pronto no R2, aguardando publicação
    published = "published"   # Publicado em pelo menos uma plataforma
    failed = "failed"         # Falhou em alguma etapa


class ContentItem(BaseModelMixin, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        Index("ix_content_items_office_status", "office_id", "status"),
        Index("ix_content_items_user_id", "user_id"),
        Index("ix_content_items_decision_id", "decision_id"),
        {"comment": "Vídeos produzidos — cada item rastreia decisão, roteiro, artefatos e publicação."},
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
        comment="Nulo se conteúdo foi criado manualmente (fora do BRAIN).",
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    script: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Roteiro completo: gancho/desenvolvimento/clímax/final.",
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

    # Metadados de produção
    production_meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Parâmetros de geração: voz TTS, música, template visual.",
    )
    # Plataformas onde foi publicado e respectivos IDs externos
    publication_log: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
        comment="[{platform, external_id, published_at, url}]",
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
