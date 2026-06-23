"""Model: social_accounts — contas nas plataformas vinculadas a um escritório."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class SocialPlatform(str, enum.Enum):
    tiktok = "tiktok"
    instagram = "instagram"
    youtube = "youtube"
    kwai = "kwai"
    facebook = "facebook"


class SocialAccount(BaseModelMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "platform", "platform_username",
            name="uq_social_accounts_user_platform_username",
        ),
        Index("ix_social_accounts_user_id", "user_id"),
        Index("ix_social_accounts_office_platform", "office_id", "platform"),
        {"comment": "Contas sociais vinculadas — tokens criptografados em aplicação."},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    office_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="SET NULL"),
        nullable=True,
        comment="Nulo = conta vinculada ao user mas ainda não atribuída a office.",
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(SocialPlatform, name="socialplatform", create_constraint=True),
        nullable=False,
    )
    platform_username: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_user_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="ID interno da plataforma (TikTok open_id, etc.).",
    )

    # Tokens — criptografados em nível de aplicação via cryptography.fernet
    # Nunca armazenar plaintext. A chave fica no SECRET_KEY do settings.
    access_token_enc: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="Token de acesso criptografado (Fernet).",
    )
    refresh_token_enc: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="Refresh token criptografado (Fernet).",
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    office: Mapped["Office | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="social_accounts", lazy="raise"
    )
