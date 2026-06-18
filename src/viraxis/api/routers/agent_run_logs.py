"""Router de AgentRunLogs — PR-2 Fase 2.

Endpoints:
  GET /agent-run-logs                           → lista todos (admin only)
  GET /offices/{office_id}/agent-run-logs       → lista por escritório
  GET /agent-run-logs/{log_id}                  → detalhe completo (admin only)
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_admin, get_current_user, get_session
from viraxis.domain.models.agent_run_log import AgentRunLog, AgentRunStatus
from viraxis.domain.models.office import Office
from viraxis.domain.models.user import User
from viraxis.infrastructure.repositories.agent_run_log import AgentRunLogRepository

router = APIRouter(tags=["agent-run-logs"])


# ── Schemas ────────────────────────────────────────────────────────────────────

def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _duration_seconds(log: AgentRunLog) -> float | None:
    if log.started_at and log.finished_at:
        return (log.finished_at - log.started_at).total_seconds()
    return None


class AgentRunLogSummary(BaseModel):
    """Versão pública — sem input/output brutos, sem stack trace."""
    id: str
    agent_name: str
    task_name: str
    status: str
    started_at: str | None
    duration_s: float | None
    message: str | None  # mensagem amigável derivada de error_message


class AgentRunLogDetail(AgentRunLogSummary):
    """Versão completa — apenas para admin."""
    office_id: str | None
    user_id: str | None
    celery_task_id: str | None
    input_data: dict
    output_data: dict
    error_message: str | None
    traceback: str | None
    finished_at: str | None
    created_at: str


_STATUS_MESSAGES: dict[str, str] = {
    "queued": "Aguardando execução",
    "running": "Em andamento",
    "success": "Concluído com sucesso",
    "failed": "Falhou durante a execução",
    "retrying": "Tentando novamente",
    "cancelled": "Cancelado",
}


def _to_summary(log: AgentRunLog) -> AgentRunLogSummary:
    return AgentRunLogSummary(
        id=str(log.id),
        agent_name=log.agent_name,
        task_name=log.task_name,
        status=log.status.value,
        started_at=_fmt(log.started_at),
        duration_s=_duration_seconds(log),
        message=_STATUS_MESSAGES.get(log.status.value),
    )


def _to_detail(log: AgentRunLog) -> AgentRunLogDetail:
    base = _to_summary(log)
    return AgentRunLogDetail(
        **base.model_dump(),
        office_id=str(log.office_id) if log.office_id else None,
        user_id=str(log.user_id) if log.user_id else None,
        celery_task_id=log.celery_task_id,
        input_data=log.input_data or {},
        output_data=log.output_data or {},
        error_message=log.error_message,
        traceback=log.traceback,
        finished_at=_fmt(log.finished_at),
        created_at=_fmt(log.created_at) or "",
    )


async def _get_office_for_user(
    office_id: UUID, user_id: UUID, session: AsyncSession
) -> Office:
    result = await session.execute(
        select(Office).where(Office.id == office_id, Office.user_id == user_id)
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=404, detail="Escritório não encontrado")
    return office


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/agent-run-logs",
    response_model=list[AgentRunLogDetail],
)
async def list_all_logs_admin(
    agent_name: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Lista todos os logs de agentes — admin only."""
    status_enum: AgentRunStatus | None = None
    if status_filter:
        try:
            status_enum = AgentRunStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {status_filter}")

    repo = AgentRunLogRepository(session)
    logs = await repo.list_all_admin(
        agent_name=agent_name,
        status=status_enum,
        limit=limit,
        offset=offset,
    )
    return [_to_detail(log) for log in logs]


@router.get(
    "/offices/{office_id}/agent-run-logs",
    response_model=list[AgentRunLogSummary],
)
async def list_logs_by_office(
    office_id: UUID,
    agent_name: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista logs de um escritório do usuário — versão sem dados internos."""
    await _get_office_for_user(office_id, current_user.id, session)

    status_enum: AgentRunStatus | None = None
    if status_filter:
        try:
            status_enum = AgentRunStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {status_filter}")

    repo = AgentRunLogRepository(session)
    logs = await repo.list_by_office(
        office_id,
        agent_name=agent_name,
        status=status_enum,
        limit=limit,
        offset=offset,
    )
    return [_to_summary(log) for log in logs]


@router.get(
    "/agent-run-logs/{log_id}",
    response_model=AgentRunLogDetail,
)
async def get_log_detail(
    log_id: UUID,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Retorna log completo com input/output/traceback — admin only."""
    repo = AgentRunLogRepository(session)
    log = await repo.get(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    return _to_detail(log)
