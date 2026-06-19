"""Model: offices — escritórios virtuais de conteúdo por nicho."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class OfficeStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class Office(BaseModelMixin, Base):
    __tablename__ = "offices"
    __table_args__ = (
        Index("ix_offices_user_id", "user_id"),
        Index("ix_offices_user_status", "user_id", "status"),
        {"comment": "Escritórios virtuais — cada um opera em um nicho específico."},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[OfficeStatus] = mapped_column(
        Enum(OfficeStatus, name="officestatus", create_constraint=True),
        nullable=False,
        default=OfficeStatus.active,
        server_default=OfficeStatus.active.value,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="offices", lazy="raise")  # type: ignore[name-defined]  # noqa: F821
    niche_profile: Mapped["NicheProfile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "NicheProfile", back_populates="office", uselist=False, lazy="raise"
    )
    content_decisions: Mapped[list["ContentDecision"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ContentDecision", back_populates="office", lazy="raise"
    )
    content_items: Mapped[list["ContentItem"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ContentItem", back_populates="office", lazy="raise"
    )
    trend_snapshots: Mapped[list["TrendSnapshot"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "TrendSnapshot", back_populates="office", lazy="raise"
    )
    social_accounts: Mapped[list["SocialAccount"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "SocialAccount", back_populates="office", lazy="raise"
    )
