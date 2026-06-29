"""Model: niche_profiles — inteligência acumulada de nicho por escritório."""

import uuid

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import UUIDPrimaryKeyMixin, TimestampMixin


class NicheProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    1:1 com Office. Armazena o estado atual do aprendizado de nicho:
    archetypes preferidos, plataformas alvo, keywords de alta performance,
    estilo editorial e parâmetros do BRAIN.
    """

    __tablename__ = "niche_profiles"
    __table_args__ = (
        UniqueConstraint("office_id", name="uq_niche_profiles_office_id"),
        Index("ix_niche_profiles_user_id", "user_id"),
        Index("ix_niche_profiles_office_user", "office_id", "user_id"),
        {"comment": "Perfil de nicho — inteligência acumulada por escritório."},
    )

    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Desnormalizado intencionalmente: queries de manager por user_id sem JOIN
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    niche_name: Mapped[str] = mapped_column(Text(), nullable=False)

    # JSONB: permite evolução de schema sem migrations para dados flexíveis
    target_platforms: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
        comment="['tiktok', 'instagram', 'youtube', 'kwai']",
    )
    viral_archetypes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Pesos por archetype baseados em performance histórica.",
    )
    content_style: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Tom, ritmo, estilo editorial preferidos.",
    )
    top_keywords: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
        comment="Keywords de alta performance identificadas pelo SCOUT.",
    )
    brain_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Parâmetros tunados do BRAIN: temperature, thresholds, etc.",
    )
    raw_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    office: Mapped["Office"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="niche_profile", lazy="raise"
    )
