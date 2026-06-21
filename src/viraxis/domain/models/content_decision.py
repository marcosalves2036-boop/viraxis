"""Model: content_decisions — decisão documentada do BRAIN (diferencial de produto)."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class DecisionType(str, enum.Enum):
    content_topic = "content_topic"       # BRAIN escolheu tema
    archetype_selection = "archetype_selection"  # BRAIN escolheu archetype viral
    platform_targeting = "platform_targeting"    # BRAIN escolheu plataforma
    repost_strategy = "repost_strategy"          # BRAIN decidiu repostar com ajuste
    pause_office = "pause_office"                # BRAIN decidiu pausar escritório


class DecisionStatus(str, enum.Enum):
    pending = "pending"       # Gerada, aguardando execução
    approved = "approved"     # Kevin aprovou manualmente (se modo supervisionado)
    executing = "executing"   # Em execução pelo pipeline
    done = "done"             # Conteúdo produzido com sucesso
    rejected = "rejected"     # Rejeitada pelo Kevin ou pelo pipeline
    failed = "failed"         # Falhou durante execução


class ContentDecision(BaseModelMixin, Base):
    """
    Cada linha = uma decisão do BRAIN documentada.
    O log de decisão é um first-class object — não é log, é produto.
    """

    __tablename__ = "content_decisions"
    __table_args__ = (
        Index("ix_content_decisions_office_status", "office_id", "status"),
        Index("ix_content_decisions_user_id", "user_id"),
        Index("ix_content_decisions_created_at", "created_at"),
        {"comment": "Decisões documentadas do BRAIN — diferencial core do produto."},
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
    decision_type: Mapped[DecisionType] = mapped_column(
        Enum(DecisionType, name="decisiontype", create_constraint=True),
        nullable=False,
    )
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus, name="decisionstatus", create_constraint=True),
        nullable=False,
        default=DecisionStatus.pending,
        server_default=DecisionStatus.pending.value,
    )

    # O raciocínio do BRAIN — o que torna o produto auditável
    hypothesis: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Hipótese do BRAIN: por que esse conteúdo vai performar.",
    )
    reasoning: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Chain-of-thought estruturado: sinais identificados, alternativas descartadas.",
    )

    selected_archetype: Mapped[str | None] = mapped_column(String(128), nullable=True)
    selected_topic: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selected_platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_instructions: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Instruções adicionais do criador para o roteiro.")

    # Inputs que embasaram a decisão (snapshot das evidências no momento)
    input_signals: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Sinais de trend e analytics que motivaram a decisão.",
    )

    # Relationships
    office: Mapped["Office"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="content_decisions", lazy="raise"
    )
    content_items: Mapped[list["ContentItem"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ContentItem", back_populates="decision", lazy="raise"
    )
