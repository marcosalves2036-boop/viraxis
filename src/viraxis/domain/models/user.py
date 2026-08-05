"""Model: users — raiz do tenant."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class UserPlan(str, enum.Enum):
    free = "free"
    pro = "pro"
    business = "business"


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class User(BaseModelMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        {"comment": "Contas de usuario — raiz da hierarquia multi-tenant."},
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[UserPlan] = mapped_column(
        Enum(UserPlan, name="userplan", create_constraint=True),
        nullable=False,
        default=UserPlan.free,
        server_default=UserPlan.free.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True após o usuário clicar no link de verificação de email.",
    )
    notify_content_ready: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
        comment=(
            "Opt-out de notificações por email quando um ContentItem fica "
            "pronto (status=ready). True (padrão) = recebe o email. "
            "False = usuário desabilitou este tipo de notificação."
        ),
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole", create_constraint=True),
        nullable=False,
        default=UserRole.user,
        server_default=UserRole.user.value,
    )

    # ── Onboarding travado (gate de primeiro uso) ──────────────────────────
    # Espelho persistido do progresso real do pipeline (não é checkbox manual:
    # cada campo é recalculado a partir de eventos reais toda vez que o
    # endpoint GET /users/me/onboarding é consultado — ver
    # viraxis.api.routers.users._compute_onboarding_progress). Persistimos
    # aqui para: (1) permitir consulta/auditoria via SQL direto sem refazer os
    # três selects, e (2) fixar `onboarding_completed_at` permanentemente na
    # primeira vez que os três marcos são atingidos, mesmo que o usuário
    # depois delete o vídeo/decisão/conteúdo que os originou — o gate não
    # deve reaparecer para quem já passou por ele.
    has_uploaded_video: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True quando existe ao menos um RawVideo status=ready do usuário (qualquer escritório).",
    )
    has_brain_decision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True quando existe ao menos uma ContentDecision criada pelo BRAIN para o usuário.",
    )
    has_ready_content: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True quando existe ao menos um ContentItem status=ready/published do usuário.",
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
        comment="Preenchido uma única vez quando os 3 marcos acima são atingidos. Trava o gate como concluído para sempre.",
    )

    # Relationships
    offices: Mapped[list["Office"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="user", lazy="raise"
    )
