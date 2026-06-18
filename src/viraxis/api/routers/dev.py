"""
Router /dev — Painel de desenvolvimento Kevin+Davi.

Endpoints:
  POST /dev/task         — Inicia uma sessão Kevin+Davi
  GET  /dev/task/{id}    — Polling do status da sessão
  GET  /dev/sessions     — Lista sessões recentes
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from viraxis.api.deps import get_current_admin
from viraxis.domain.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class DevTaskRequest(BaseModel):
    task: str = Field(
        min_length=10,
        max_length=2000,
        description="Descrição da tarefa de desenvolvimento em linguagem natural.",
        examples=["Adicionar endpoint PATCH /offices/{id}/status que pausa ou ativa um escritório"],
    )


class DevSessionResponse(BaseModel):
    id: str
    task: str
    status: str
    started_at: str | None
    finished_at: str | None
    kevin_spec: str
    davi_output: str
    review_output: str
    error: str | None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/task", response_model=DevSessionResponse, status_code=202)
async def start_dev_task(
    body: DevTaskRequest,
    current_user: User = Depends(get_current_admin),
):
    """
    Inicia uma sessão Kevin+Davi para a tarefa solicitada.
    Retorna imediatamente com status='running' — use GET /dev/task/{id} para polling.
    """
    from viraxis.agents.dev_crew import run_dev_task  # lazy import — crewai é pesado

    logger.info("[dev] Admin %s iniciou tarefa: %s", current_user.email, body.task[:80])
    session = await run_dev_task(body.task)
    return DevSessionResponse(**session.to_dict())


@router.get("/task/{session_id}", response_model=DevSessionResponse)
async def get_dev_task(
    session_id: str,
    current_user: User = Depends(get_current_admin),
):
    """Retorna o estado atual de uma sessão DevCrew pelo ID."""
    from viraxis.agents.dev_crew import get_session

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return DevSessionResponse(**session.to_dict())


@router.get("/sessions", response_model=list[DevSessionResponse])
async def list_dev_sessions(
    current_user: User = Depends(get_current_admin),
):
    """Lista as sessões DevCrew recentes (até 20)."""
    from viraxis.agents.dev_crew import list_sessions

    return [DevSessionResponse(**s.to_dict()) for s in list_sessions()]
