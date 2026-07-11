"""Router do agente BRAIN — endpoint batch-run (multi-output por editorial_highlight)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.domain.models.office import Office
from viraxis.domain.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["brain"])


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_office_or_404(
    office_id: UUID, user_id: UUID, session: AsyncSession
) -> Office:
    result = await session.execute(
        select(Office).where(Office.id == office_id, Office.user_id == user_id)
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=404, detail="Escritório não encontrado")
    return office


# ── Schemas ───────────────────────────────────────────────────────────────────

class BatchBrainRequest(BaseModel):
    office_id: UUID
    raw_video_id: UUID
    n_videos: int = Field(
        default=0, ge=0, le=10,
        description="0 = auto (todos os highlights, máx 5). >0 = limitar a N."
    )


class BatchBrainDecisionItem(BaseModel):
    id: str
    title: str
    archetype: str
    platform: str
    focus_start: float | None
    focus_end: float | None


class BatchBrainResponse(BaseModel):
    decisions: list[BatchBrainDecisionItem]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/batch-run", response_model=BatchBrainResponse)
async def batch_brain_run(
    body: BatchBrainRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Roda o BRAIN N vezes sobre o mesmo vídeo bruto, uma por editorial_highlight.

    Cada rodada gera um ContentDecision independente com foco num
    trecho diferente do vídeo. Retorna a lista de decisões criadas.
    Se o vídeo não tem highlights, roda 1x sem foco (comportamento padrão).
    """
    from viraxis.domain.models.raw_video import RawVideo
    from viraxis.agents.brain.runner import run_brain

    # Verificar ownership do vídeo bruto
    raw_video = await session.get(RawVideo, body.raw_video_id)
    if not raw_video or raw_video.office_id != body.office_id:
        raise HTTPException(status_code=404, detail="Vídeo bruto não encontrado.")

    # Verificar que escritório pertence ao usuário
    await _get_office_or_404(body.office_id, current_user.id, session)

    # Extrair highlights
    ai = raw_video.ai_analysis or {}
    highlights = ai.get("editorial_highlights", [])

    if not highlights:
        # Sem highlights: roda 1x sem foco (compatibilidade)
        highlights = [{"start": None, "end": None, "reason": "vídeo completo"}]

    max_n = body.n_videos if body.n_videos > 0 else min(len(highlights), 5)
    highlights = highlights[:max_n]

    decisions_out: list[BatchBrainDecisionItem] = []

    for hl in highlights:
        start = hl.get("start")
        end = hl.get("end")
        reason = hl.get("reason", "")

        if start is not None and end is not None:
            focus_hint = (
                f"\n\n⚡ FOCO DESTE VÍDEO: concentre-se no trecho {start:.0f}s–{end:.0f}s "
                f"como ponto de partida para o hook principal. "
                f"Razão identificada pela análise de IA: {reason}. "
                f"A decisão e o selected_topic devem refletir especificamente este momento do vídeo."
            )
        else:
            focus_hint = ""

        decision = await run_brain(
            office_id=body.office_id,
            user_id=current_user.id,
            raw_video_id=body.raw_video_id,
            focus_hint=focus_hint,
        )

        decisions_out.append(BatchBrainDecisionItem(
            id=str(decision.id),
            title=decision.selected_topic or "",
            archetype=decision.selected_archetype or "",
            platform=decision.selected_platform or "",
            focus_start=start,
            focus_end=end,
        ))

    return BatchBrainResponse(decisions=decisions_out, total=len(decisions_out))
