"""Router de Offices — escritórios + BRAIN + decisões + SCOUT trends."""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from viraxis.api.deps import get_current_user, get_session
from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus
from viraxis.domain.models.niche_profile import NicheProfile
from viraxis.domain.models.office import Office, OfficeStatus
from viraxis.domain.models.user import User
from viraxis.infrastructure.repositories.content_decision import ContentDecisionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/offices", tags=["offices"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class OfficeCreate(BaseModel):
    name: str
    niche: str
    platforms: list[str] = []
    target_audience: str = ""
    content_style: str = "educational"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome não pode ser vazio")
        return v

    @field_validator("niche")
    @classmethod
    def niche_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nicho não pode ser vazio")
        return v


class OfficeResponse(BaseModel):
    id: str
    name: str
    niche: str
    status: str
    platforms: list[str]
    target_audience: str
    content_style: str
    content_count: int = 0
    published_count: int = 0
    viral_count: int = 0
    pending_decisions: int = 0


class DecisionResponse(BaseModel):
    id: str
    decision_type: str
    status: str
    # Conteúdo selecionado
    content_topic: str
    content_format: str
    target_platform: str
    selected_archetype: str
    confidence_score: float
    # Raciocínio auditável
    hypothesis: str
    reasoning: dict
    input_signals: dict
    # Timestamps
    created_at: str
    updated_at: str


class DecisionStatusUpdate(BaseModel):
    status: str
    extra_instructions: str | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {s.value for s in DecisionStatus}
        if v not in allowed:
            raise ValueError(f"Status inválido. Permitidos: {allowed}")
        return v


class BrainRunResponse(BaseModel):
    id: str
    content_topic: str
    target_platform: str
    confidence_score: float
    hypothesis: str


class OfficeStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {s.value for s in OfficeStatus}
        if v not in allowed:
            raise ValueError(f"Status inválido. Permitidos: {allowed}")
        return v


# ── Helpers ────────────────────────────────────────────────────────────────────

def _office_to_response(
    office: Office,
    profile: NicheProfile | None,
    pending: int = 0,
) -> OfficeResponse:
    return OfficeResponse(
        id=str(office.id),
        name=office.name,
        niche=office.niche,
        status=office.status.value,
        platforms=profile.target_platforms if profile else [],
        target_audience=profile.raw_notes or "" if profile else "",
        content_style=(
            profile.content_style.get("style", "educational") if profile else "educational"
        ),
        pending_decisions=pending,
    )


def _decision_to_response(d: ContentDecision) -> DecisionResponse:
    return DecisionResponse(
        id=str(d.id),
        decision_type=d.decision_type.value,
        status=d.status.value,
        content_topic=d.selected_topic or "",
        content_format=d.decision_type.value,
        target_platform=d.selected_platform or "",
        selected_archetype=d.selected_archetype or "",
        confidence_score=d.confidence_score or 0.0,
        hypothesis=d.hypothesis,
        reasoning=d.reasoning or {},
        input_signals=d.input_signals or {},
        created_at=d.created_at.isoformat() if d.created_at else "",
        updated_at=d.updated_at.isoformat() if d.updated_at else "",
    )


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


# ── Endpoints: Offices ─────────────────────────────────────────────────────────

@router.get("", response_model=list[OfficeResponse])
async def list_offices(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    offices_result = await session.execute(
        select(Office).where(Office.user_id == current_user.id)
    )
    offices = offices_result.scalars().all()

    responses = []
    for o in offices:
        profile_result = await session.execute(
            select(NicheProfile).where(NicheProfile.office_id == o.id)
        )
        profile = profile_result.scalar_one_or_none()

        # Contar decisões pendentes
        pending_result = await session.execute(
            select(ContentDecision).where(
                ContentDecision.office_id == o.id,
                ContentDecision.status == DecisionStatus.pending,
            )
        )
        pending = len(pending_result.scalars().all())

        responses.append(_office_to_response(o, profile, pending))

    return responses


@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(
    body: OfficeCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    office = Office(
        user_id=current_user.id,
        name=body.name,
        niche=body.niche,
        status=OfficeStatus.active,
    )
    session.add(office)
    await session.flush()

    from viraxis.infrastructure.repositories.niche_profile import NicheProfileRepository
    niche_repo = NicheProfileRepository(session)
    profile = await niche_repo.upsert(
        office_id=office.id,
        user_id=current_user.id,
        niche_name=body.niche,
        target_platforms=body.platforms,
        content_style={"style": body.content_style},
        viral_archetypes={},
        top_keywords=[],
        brain_params={},
        raw_notes=body.target_audience or None,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(office)

    return _office_to_response(office, profile)


@router.patch("/{office_id}", response_model=OfficeResponse)
async def update_office(
    office_id: UUID,
    body: OfficeCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    office = await _get_office_or_404(office_id, current_user.id, session)

    office.name = body.name
    office.niche = body.niche

    profile_result = await session.execute(
        select(NicheProfile).where(NicheProfile.office_id == office_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.niche_name = body.niche
        profile.target_platforms = body.platforms
        profile.content_style = {"style": body.content_style}
        profile.raw_notes = body.target_audience or None

    session.add(office)
    await session.commit()
    await session.refresh(office)
    return _office_to_response(office, profile)


@router.patch("/{office_id}/status", response_model=OfficeResponse)
async def update_office_status(
    office_id: UUID,
    body: OfficeStatusUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Pausar ou ativar um escritório."""
    office = await _get_office_or_404(office_id, current_user.id, session)
    office.status = OfficeStatus(body.status)
    session.add(office)
    await session.commit()
    await session.refresh(office)

    profile_result = await session.execute(
        select(NicheProfile).where(NicheProfile.office_id == office_id)
    )
    profile = profile_result.scalar_one_or_none()
    return _office_to_response(office, profile)


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_office(
    office_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    office = await _get_office_or_404(office_id, current_user.id, session)
    await session.delete(office)
    await session.commit()


# ── Endpoints: BRAIN ───────────────────────────────────────────────────────────

@router.post("/{office_id}/brain/run", response_model=BrainRunResponse)
async def run_brain_for_office(
    office_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Executa o agente BRAIN para um escritório e retorna a decisão gerada."""
    await _get_office_or_404(office_id, current_user.id, session)

    try:
        from viraxis.agents.brain.runner import run_brain
        decision = await run_brain(office_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar BRAIN: {e}")

    return BrainRunResponse(
        id=str(decision.id),
        content_topic=decision.selected_topic or "",
        target_platform=decision.selected_platform or "",
        confidence_score=decision.confidence_score or 0.0,
        hypothesis=decision.hypothesis,
    )


# ── Endpoints: SCOUT Trends ────────────────────────────────────────────────────

class TrendAnalyzeRequest(BaseModel):
    url: str

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return cls(url=v) if isinstance(v, dict) else v

    def model_post_init(self, __context) -> None:
        if not self.url.startswith("http"):
            raise ValueError("URL inválida — deve começar com http(s)://")


class TrendAnalyzeResponse(BaseModel):
    snapshot_id: str
    platform: str
    archetype: str | None
    engagement_estimate: str
    keywords: list[str]
    message: str


@router.post("/{office_id}/trends/analyze", response_model=TrendAnalyzeResponse)
async def analyze_trend(
    office_id: UUID,
    body: TrendAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Analisa um vídeo viral via SCOUT e cria um TrendSnapshot.

    Sprint 1: execução síncrona.
    Sprint 3: migra para Celery com retorno {task_id, status: 'queued'}.
    """
    await _get_office_or_404(office_id, current_user.id, session)

    try:
        from viraxis.agents.scout.runner import run_scout
        from viraxis.infrastructure.ytdlp_client import (
            DownloadTimeoutError,
            UnsupportedPlatformError,
            VideoUnavailableError,
            YtdlpError,
        )
        snapshot = await run_scout(office_id, current_user.id, body.url)
    except UnsupportedPlatformError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except VideoUnavailableError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DownloadTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="A análise demorou mais que o esperado. Tente novamente.",
        )
    except YtdlpError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar tendência: {e}")

    signals = snapshot.processed_signals or {}
    return TrendAnalyzeResponse(
        snapshot_id=str(snapshot.id),
        platform=signals.get("platform_detected", "unknown"),
        archetype=signals.get("archetype"),
        engagement_estimate=signals.get("engagement_estimate", "medium"),
        keywords=signals.get("keywords", [])[:5],
        message="Tendência capturada com sucesso. O BRAIN vai usá-la na próxima análise.",
    )


# ── Endpoints: Decisions ───────────────────────────────────────────────────────

@router.get("/{office_id}/decisions", response_model=list[DecisionResponse])

async def list_decisions(
    office_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista as ContentDecisions do BRAIN para um escritório, com filtro opcional por status."""
    await _get_office_or_404(office_id, current_user.id, session)

    query = select(ContentDecision).where(ContentDecision.office_id == office_id)
    if status_filter:
        try:
            query = query.where(ContentDecision.status == DecisionStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {status_filter}")
    query = query.order_by(ContentDecision.created_at.desc()).limit(limit)

    result = await session.execute(query)
    decisions = result.scalars().all()
    return [_decision_to_response(d) for d in decisions]


@router.get("/{office_id}/decisions/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    office_id: UUID,
    decision_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna uma decisão completa pelo ID."""
    await _get_office_or_404(office_id, current_user.id, session)

    result = await session.execute(
        select(ContentDecision).where(
            ContentDecision.id == decision_id,
            ContentDecision.office_id == office_id,
        )
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")
    return _decision_to_response(decision)




async def _run_renderer_safe(office_id, user_id, decision_id) -> None:
    """Executa o RENDERER v2 em background sem propagar exceções."""
    try:
        from viraxis.agents.renderer.v2_direct import run_renderer_v2
        await run_renderer_v2(office_id, user_id, decision_id)
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"
        logger.error("Background RENDERER falhou | office=%s decision=%s err=%s", office_id, decision_id, err_msg)
        # Write error to DB so we can debug without Render logs
        try:
            from viraxis.infrastructure.database.session import AsyncSessionLocal
            from viraxis.domain.models.content_item import ContentItem, ContentStatus
            from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus
            from sqlalchemy import select, update as sa_update
            async with AsyncSessionLocal() as s:
                # Find the content_item for this decision
                r = await s.execute(
                    select(ContentItem).where(
                        ContentItem.decision_id == decision_id,
                        ContentItem.status == ContentStatus.rendering,
                    ).order_by(ContentItem.created_at.desc()).limit(1)
                )
                item = r.scalar_one_or_none()
                if item:
                    item.status = ContentStatus.failed
                    item.production_meta = {
                        "render_progress": 0,
                        "render_stage": "falhou",
                        "error": err_msg[:800],
                    }
                await s.execute(
                    sa_update(ContentDecision)
                    .where(ContentDecision.id == decision_id)
                    .values(status=DecisionStatus.failed)
                )
                await s.commit()
        except Exception as db_err:
            logger.error("Falha ao gravar erro no DB: %s", db_err)

@router.patch("/{office_id}/decisions/{decision_id}/status", response_model=DecisionResponse)
async def update_decision_status(
    office_id: UUID,
    decision_id: UUID,
    body: DecisionStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Aprova, rejeita ou avança o status de uma decisão do BRAIN.
    
    Quando status=approved, dispara o RENDERER v2 em background automaticamente.
    """
    await _get_office_or_404(office_id, current_user.id, session)

    result = await session.execute(
        select(ContentDecision).where(
            ContentDecision.id == decision_id,
            ContentDecision.office_id == office_id,
        )
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")

    decision.status = DecisionStatus(body.status)
    # Persist extra_instructions so renderer can read from DB (not just memory)
    if body.extra_instructions is not None:
        decision.extra_instructions = body.extra_instructions
    session.add(decision)
    await session.commit()
    await session.refresh(decision)

    # Auto-trigger RENDERER quando aprovada
    if body.status == "approved":
        background_tasks.add_task(
            _run_renderer_safe,
            office_id=office_id,
            user_id=current_user.id,
            decision_id=decision_id,
            extra_instructions=body.extra_instructions,
        )

    return _decision_to_response(decision)


# ── Endpoints: RENDERER ────────────────────────────────────────────────────────

class RenderResponse(BaseModel):
    content_item_id: str
    title: str
    duration_seconds: float | None
    status: str
    message: str


@router.post(
    "/{office_id}/decisions/{decision_id}/render",
    response_model=RenderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def render_decision(
    office_id: UUID,
    decision_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Executa o agente RENDERER para gerar roteiro a partir de uma decisão do BRAIN.

    Cria um ContentItem com script completo (status=draft) e avança a decisão
    para status=executing.

    Sprint 1: execução síncrona.
    Sprint 3: migra para Celery com retorno {task_id, status: 'queued'}.
    """
    await _get_office_or_404(office_id, current_user.id, session)

    try:
        from viraxis.agents.renderer.runner import run_renderer
        content_item = await run_renderer(
            office_id, current_user.id, decision_id
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao renderizar roteiro: {e}")

    return RenderResponse(
        content_item_id=str(content_item.id),
        title=content_item.title,
        duration_seconds=content_item.duration_seconds,
        status=content_item.status.value,
        message="Roteiro gerado com sucesso. ContentItem criado com status=draft.",
    )


# ── Endpoints: Progresso do RENDERER ──────────────────────────────────────────

class RenderProgressResponse(BaseModel):
    item_id: str | None
    progress: int
    stage: str
    status: str


@router.get(
    "/{office_id}/decisions/{decision_id}/render/progress",
    response_model=RenderProgressResponse,
)
async def get_render_progress(
    office_id: UUID,
    decision_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna o progresso atual do RENDERER para uma decisão."""
    from viraxis.domain.models.content_item import ContentItem
    await _get_office_or_404(office_id, current_user.id, session)

    result = await session.execute(
        select(ContentItem)
        .where(ContentItem.decision_id == decision_id)
        .order_by(ContentItem.created_at.desc())
        .limit(1)
    )
    item = result.scalar_one_or_none()

    if item is None:
        return RenderProgressResponse(item_id=None, progress=0, stage="aguardando", status="pending")

    meta = item.production_meta or {}
    return RenderProgressResponse(
        item_id=str(item.id),
        progress=meta.get("render_progress", 0),
        stage=meta.get("render_stage", "processando"),
        status=item.status.value,
    )


# ── Endpoint: Conteúdo do escritório ──────────────────────────────────────────

class ContentItemSummary(BaseModel):
    id: str
    decision_id: str | None
    title: str
    status: str
    duration_seconds: float | None
    production_meta: dict
    script: str
    created_at: str


@router.get(
    "/{office_id}/content",
    response_model=list[ContentItemSummary],
)
async def list_office_content(
    office_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista todos os ContentItems gerados pelo RENDERER para um escritório."""
    from viraxis.domain.models.content_item import ContentItem
    from sqlalchemy import desc as sa_desc
    await _get_office_or_404(office_id, current_user.id, session)

    result = await session.execute(
        select(ContentItem)
        .where(
            ContentItem.office_id == office_id,
            ContentItem.deleted_at.is_(None),
        )
        .order_by(sa_desc(ContentItem.created_at))
        .limit(100)
    )
    items = result.scalars().all()

    return [
        ContentItemSummary(
            id=str(i.id),
            decision_id=str(i.decision_id) if i.decision_id else None,
            title=i.title,
            status=i.status.value,
            duration_seconds=i.duration_seconds,
            production_meta=i.production_meta or {},
            script=i.script or "",
            created_at=i.created_at.isoformat() if i.created_at else "",
        )
        for i in items
    ]


@router.delete(
    "/{office_id}/content/{item_id}",
    status_code=204,
)
async def delete_content_item(
    office_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete de um ContentItem. Também reseta a decisão associada para 'pending'."""
    from viraxis.domain.models.content_item import ContentItem
    from datetime import datetime, timezone

    await _get_office_or_404(office_id, current_user.id, session)

    item_result = await session.execute(
        select(ContentItem).where(
            ContentItem.id == item_id,
            ContentItem.office_id == office_id,
            ContentItem.deleted_at.is_(None),
        )
    )
    item = item_result.scalar_one_or_none()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Content item não encontrado")

    # Soft-delete
    item.deleted_at = datetime.now(timezone.utc)

    # Reset decisão associada para pending (se houver)
    if item.decision_id:
        dec_result = await session.execute(
            select(ContentDecision).where(ContentDecision.id == item.decision_id)
        )
        dec = dec_result.scalar_one_or_none()
        if dec:
            dec.status = DecisionStatus.pending
            dec.updated_at = datetime.now(timezone.utc)

    await session.commit()

# ── Endpoints: revisão de conteúdo ────────────────────────────────────────────

@router.patch("/{office_id}/content/{item_id}/approve", status_code=200)
async def approve_content_item(
    office_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Aprova o roteiro gerado → status vira ready."""
    await _get_office_or_404(office_id, current_user.id, session)
    result = await session.execute(
        select(ContentItem).where(
            ContentItem.id == item_id,
            ContentItem.office_id == office_id,
            ContentItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    if item.status != ContentStatus.review:
        raise HTTPException(status_code=400, detail=f"Item não está em review (status atual: {item.status})")
    item.status = ContentStatus.ready
    meta = dict(item.production_meta or {})
    meta["render_progress"] = 100
    meta["render_stage"] = "aprovado"
    item.production_meta = meta
    await session.commit()
    return {"id": str(item_id), "status": "ready"}


@router.patch("/{office_id}/content/{item_id}/reject", status_code=200)
async def reject_content_item(
    office_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Rejeita o roteiro → soft-delete + decisão volta para pending."""
    await _get_office_or_404(office_id, current_user.id, session)
    result = await session.execute(
        select(ContentItem).where(
            ContentItem.id == item_id,
            ContentItem.office_id == office_id,
            ContentItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    from datetime import datetime, timezone
    item.deleted_at = datetime.now(timezone.utc)

    if item.decision_id:
        dec_r = await session.execute(
            select(ContentDecision).where(ContentDecision.id == item.decision_id)
        )
        dec = dec_r.scalar_one_or_none()
        if dec:
            dec.status = DecisionStatus.pending

    await session.commit()
    return {"id": str(item_id), "status": "rejected", "decision_reset": "pending"}

