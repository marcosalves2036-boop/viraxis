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


def _compute_suggestion(duration: float | None, n_highlights: int) -> dict:
    """Regras de negócio para sugestão de quantidade de vídeos."""
    if duration is None:
        return {"max_allowed": 5, "suggested_n": min(n_highlights, 3),
                "requires_manual": False, "blocked": False, "block_reason": None}
    if duration < 300:
        return {"max_allowed": 1, "suggested_n": 1,
                "requires_manual": False, "blocked": True,
                "block_reason": f"Vídeo muito curto ({int(duration)}s). Máximo 1 vídeo para brutos abaixo de 5 minutos."}
    elif duration < 900:
        return {"max_allowed": 2, "suggested_n": min(n_highlights, 2) or 1,
                "requires_manual": False, "blocked": False, "block_reason": None}
    elif duration < 3600:
        return {"max_allowed": 5, "suggested_n": min(n_highlights, 5) or 2,
                "requires_manual": False, "blocked": False, "block_reason": None}
    else:
        return {"max_allowed": 10, "suggested_n": min(n_highlights, 5) or 3,
                "requires_manual": True, "blocked": False, "block_reason": None}


def _generate_synthetic_highlights(duration: float, n: int) -> list[dict]:
    """Divide o vídeo em N segmentos uniformes quando highlights reais são insuficientes."""
    segment = duration / n
    return [
        {
            "start": round(i * segment + segment * 0.15, 1),
            "end":   round(i * segment + segment * 0.65, 1),
            "reason": f"segmento sintético {i+1}/{n} — sem destaque editorial detectado",
            "_synthetic": True,
        }
        for i in range(n)
    ]


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
    synthetic_count: int = 0


class BatchSuggestResponse(BaseModel):
    duration_seconds: float | None
    n_highlights: int
    suggested_n: int
    max_allowed: int
    requires_manual: bool   # True se > 1h — frontend mostra input numérico
    blocked: bool           # True se < 5min — frontend bloqueia antes de abrir modal
    block_reason: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/batch-suggest", response_model=BatchSuggestResponse)
async def batch_suggest(
    raw_video_id: UUID,
    office_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Sugere quantos vídeos gerar a partir de um bruto (duração + highlights)."""
    from viraxis.domain.models.raw_video import RawVideo

    raw_video = await session.get(RawVideo, raw_video_id)
    if not raw_video or raw_video.office_id != office_id:
        raise HTTPException(404, "Vídeo não encontrado")
    await _get_office_or_404(office_id, current_user.id, session)

    ai = raw_video.ai_analysis or {}
    highlights = ai.get("editorial_highlights", [])
    suggestion = _compute_suggestion(raw_video.duration_seconds, len(highlights))

    return BatchSuggestResponse(
        duration_seconds=raw_video.duration_seconds,
        n_highlights=len(highlights),
        **suggestion,
    )



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

    # Extrair highlights + smart video count
    duration = raw_video.duration_seconds
    ai = raw_video.ai_analysis or {}
    highlights = ai.get("editorial_highlights", [])
    suggestion = _compute_suggestion(duration, len(highlights))

    # Bloquear vídeos muito curtos
    if suggestion["blocked"] and body.n_videos > 1:
        raise HTTPException(422, suggestion["block_reason"])

    # Determinar target
    target_n = body.n_videos if body.n_videos > 0 else suggestion["suggested_n"]
    target_n = min(target_n, suggestion["max_allowed"])

    # Preencher com sintéticos se necessário (só para vídeos com duration conhecida)
    real_highlights = highlights[:target_n]
    if len(real_highlights) < target_n and duration:
        synthetics = _generate_synthetic_highlights(duration, target_n)
        # Usar os slots não cobertos por highlights reais
        real_highlights = real_highlights + synthetics[len(real_highlights):]

    highlights = real_highlights or [{"start": None, "end": None, "reason": "vídeo completo"}]

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

    # Contar sintéticos na lista final
    n_synthetic = sum(1 for h in highlights if h.get("_synthetic"))

    return BatchBrainResponse(
        decisions=decisions_out,
        total=len(decisions_out),
        synthetic_count=n_synthetic,
    )
