"""Router de ContentItems — PR-1 Fase 2.

Endpoints:
  GET    /offices/{office_id}/content-items               → lista
  GET    /offices/{office_id}/content-items/{item_id}     → detalhe
  POST   /offices/{office_id}/content-items               → criar rascunho manual
  PATCH  /offices/{office_id}/content-items/{item_id}/status → transição de status
  DELETE /offices/{office_id}/content-items/{item_id}     → soft delete
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.office import Office
from viraxis.domain.models.user import User
from viraxis.infrastructure.repositories.content_item import ContentItemRepository

router = APIRouter(prefix="/offices", tags=["content-items"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class ContentItemResponse(BaseModel):
    id: str
    office_id: str
    decision_id: str | None
    title: str
    status: str
    duration_seconds: float | None
    production_meta: dict
    publication_log: list
    created_at: str
    updated_at: str
    deleted_at: str | None


class ContentItemDetailResponse(ContentItemResponse):
    """Resposta completa com script — para a página de detalhe."""
    script: str


class ContentItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    script: str = Field(..., min_length=1)
    decision_id: str | None = None


class ContentItemStatusUpdate(BaseModel):
    status: str = Field(...)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return cls(status=v) if isinstance(v, dict) else v

    def model_post_init(self, __context) -> None:
        allowed = {s.value for s in ContentStatus}
        if self.status not in allowed:
            raise ValueError(f"Status inválido. Permitidos: {allowed}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_response(item: ContentItem) -> ContentItemResponse:
    return ContentItemResponse(
        id=str(item.id),
        office_id=str(item.office_id),
        decision_id=str(item.decision_id) if item.decision_id else None,
        title=item.title,
        status=item.status.value,
        duration_seconds=item.duration_seconds,
        production_meta=item.production_meta or {},
        publication_log=item.publication_log or [],
        created_at=_fmt(item.created_at) or "",
        updated_at=_fmt(item.updated_at) or "",
        deleted_at=_fmt(getattr(item, "deleted_at", None)),
    )


def _to_detail(item: ContentItem) -> ContentItemDetailResponse:
    base = _to_response(item)
    return ContentItemDetailResponse(**base.model_dump(), script=item.script)


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


async def _get_item_or_404(
    repo: ContentItemRepository, item_id: UUID, office_id: UUID
) -> ContentItem:
    item = await repo.get_by_id_for_office(item_id, office_id)
    if not item:
        raise HTTPException(status_code=404, detail="ContentItem não encontrado")
    return item


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/{office_id}/content-items",
    response_model=list[ContentItemResponse],
)
async def list_content_items(
    office_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista ContentItems de um escritório com filtro opcional por status."""
    await _get_office_or_404(office_id, current_user.id, session)

    status_enum: ContentStatus | None = None
    if status_filter:
        try:
            status_enum = ContentStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {status_filter}")

    repo = ContentItemRepository(session)
    items = await repo.list_by_office(
        office_id,
        status=status_enum,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    return [_to_response(i) for i in items]


@router.get(
    "/{office_id}/content-items/{item_id}",
    response_model=ContentItemDetailResponse,
)
async def get_content_item(
    office_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna um ContentItem completo (inclui script) para a página de detalhe."""
    await _get_office_or_404(office_id, current_user.id, session)
    repo = ContentItemRepository(session)
    item = await _get_item_or_404(repo, item_id, office_id)
    return _to_detail(item)


@router.post(
    "/{office_id}/content-items",
    response_model=ContentItemDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_content_item(
    office_id: UUID,
    body: ContentItemCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Cria um rascunho manual — sem passar pelo BRAIN/RENDERER."""
    await _get_office_or_404(office_id, current_user.id, session)

    decision_uuid: UUID | None = None
    if body.decision_id:
        try:
            decision_uuid = UUID(body.decision_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="decision_id inválido")

    repo = ContentItemRepository(session)
    item = await repo.create(
        office_id=office_id,
        user_id=current_user.id,
        decision_id=decision_uuid,
        title=body.title,
        script=body.script,
        status=ContentStatus.draft,
    )
    await session.commit()
    await session.refresh(item)
    return _to_detail(item)


@router.patch(
    "/{office_id}/content-items/{item_id}/status",
    response_model=ContentItemDetailResponse,
)
async def update_content_item_status(
    office_id: UUID,
    item_id: UUID,
    body: ContentItemStatusUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Transição de status com validação de máquina de estados."""
    await _get_office_or_404(office_id, current_user.id, session)
    repo = ContentItemRepository(session)
    item = await _get_item_or_404(repo, item_id, office_id)

    try:
        item = await repo.update_status(item, ContentStatus(body.status))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await session.commit()
    await session.refresh(item)
    return _to_detail(item)


@router.delete(
    "/{office_id}/content-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def soft_delete_content_item(
    office_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Soft delete — seta deleted_at, não remove do banco."""
    await _get_office_or_404(office_id, current_user.id, session)
    repo = ContentItemRepository(session)
    item = await _get_item_or_404(repo, item_id, office_id)
    await repo.soft_delete(item)
    await session.commit()


# ── Publicacao ─────────────────────────────────────────────────────────────────

class PublishTargetRequest(BaseModel):
    platform: str
    social_account_id: str
    caption: str | None = None
    hashtags: list[str] = []


class PublishRequest(BaseModel):
    targets: list[PublishTargetRequest]


class PublishResponse(BaseModel):
    content_item_id: str
    successful_platforms: list[str]
    failed_platforms: list[str]
    message: str


@router.post(
    "/{office_id}/content-items/{item_id}/publish",
    response_model=PublishResponse,
)
async def publish_content_item(
    office_id: UUID,
    item_id: UUID,
    body: PublishRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Publica um ContentItem nas plataformas sociais especificadas.

    Sprint 1: execucao sincrona.
    Sprint 3: migra para Celery (retorna task_id + status queued).
    """
    await _get_office_or_404(office_id, current_user.id, session)
    repo = ContentItemRepository(session)
    item = await _get_item_or_404(repo, item_id, office_id)

    if item.status not in (ContentStatus.ready, ContentStatus.draft):
        raise HTTPException(
            status_code=422,
            detail=f"Item com status={item.status.value} nao pode ser publicado. Esperado: ready ou draft.",
        )

    try:
        from viraxis.agents.publisher.runner import run_publisher
        from viraxis.agents.publisher.schemas import PublisherInput, PublishTarget

        publisher_input = PublisherInput(
            content_item_id=str(item_id),
            office_id=str(office_id),
            user_id=str(current_user.id),
            title=item.title,
            script=item.script,
            targets=[
                PublishTarget(
                    platform=t.platform,
                    social_account_id=t.social_account_id,
                    caption=t.caption,
                    hashtags=t.hashtags,
                )
                for t in body.targets
            ],
        )
        output = await run_publisher(publisher_input)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao publicar: {e}")

    msg_parts = []
    if output.successful_platforms:
        msg_parts.append(f"Publicado em: {', '.join(output.successful_platforms)}.")
    if output.failed_platforms:
        msg_parts.append(f"Falhou em: {', '.join(output.failed_platforms)}.")

    return PublishResponse(
        content_item_id=str(item_id),
        successful_platforms=output.successful_platforms,
        failed_platforms=output.failed_platforms,
        message=" ".join(msg_parts) or "Nenhuma plataforma processada.",
    )
