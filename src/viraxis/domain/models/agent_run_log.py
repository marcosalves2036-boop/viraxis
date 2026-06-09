"""Model: agent_run_logs — log de execução de agentes Celery/CrewAI."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import UUIDPrimaryKeyMixin


class AgentRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    retrying = "retrying"
    cancelled = "cancelled"


class AgentRunLog(UUIDPrimaryKeyMixin, Base):
    """
    Rastreia cada execução de agente/task Celery.
    Permite auditoria completa do pipeline e diagnóstico de falhas.
    """

    __tablename__ = "agent_run_logs"
    __table_args__ = (
        UniqueConstraint(
            "celery_task_id",
            name="uq_agent_run_logs_celery_task_id",
        ),
        Index("ix_agent_run_logs_office_status", "office_id", "status"),
        Index("ix_agent_run_logs_user_id", "user_id"),
        Index("ix_agent_run_logs_agent_name", "agent_name"),
        Index("ix_agent_run_logs_started_at", "started_at"),
        {"comment": "Log de execução de agentes — base do painel de observabilidade."},
    )

    # office_id e user_id nullable: alguns runs são de sistema (ex: health check)
    office_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    agent_name: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="Ex: BrainAgent, ScoutAgent, RendererAgent",
    )
    task_name: Mapped[str] = mapped_column(
        String(256), nullable=False,
        comment="Nome da task Celery ou método CrewAI.",
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="UUID do Celery — nulo para runs síncronos.",
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agentrunstatus", create_constraint=True),
        nullable=False,
        default=AgentRunStatus.queued,
        server_default=AgentRunStatus.queued.value,
    )

    input_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Payload de entrada (sanitizado — sem secrets).",
    )
    output_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        comment="Resultado estruturado do agente.",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )
