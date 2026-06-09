"""Model: users — raiz do tenant."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class UserPlan(str, enum.Enum):
    free = "free"
    pro = "pro"
    business = "business"


class User(BaseModelMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        {"comment": "Contas de usuário — raiz da hierarquia multi-tenant."},
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

    # Relationships (lazy="raise" força joins explícitos — sem N+1 silencioso)
    offices: Mapped[list["Office"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="user", lazy="raise"
    )
