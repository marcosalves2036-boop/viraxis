"""Router de Analytics — KPIs e agregados para o dashboard de analytics.

Endpoints:
  GET /analytics/summary               → KPIs consolidados (vídeos, aprovação,
                                          publicações, plataformas ativas)
  GET /analytics/timeline?days=30      → série temporal de vídeos gerados/dia
  GET /analytics/publications?limit=20 → últimas publicações (SocialPost não
                                          existe como tabela própria — as
                                          publicações ficam registradas em
                                          ContentItem.publication_log, um JSONB
                                          com uma entrada por publicação bem
                                          sucedida: {platform, external_id,
                                          published_at, url}).

Isolamento: todas as queries filtram por office_id pertencente ao usuário
autenticado (Office.user_id == current_user.id), mesmo padrão usado em
content_items.py / offices.py — nunca expõe dados de outro usuário.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.office import Office
from viraxis.domain.models.social_account import SocialAccount
from viraxis.domain.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Status que contam como "aprovado" para a taxa de aprovação.
# `ready` é o status logo após aprovação pelo RENDERER; `published` é um
# ready que já avançou para publicação — também conta como aprovado (nunca
# deixou de ser aprovado só porque já foi publicado).
_APPROVED_STATUSES = (ContentStatus.ready, ContentStatus.published)


# ── Schemas ────────────────────────────────────────────────────────────────────

class PlatformCount(BaseModel):
    platform: str
    count: int


class AnalyticsSummaryResponse(BaseModel):
    total_videos: int
    ready_count: int
    approval_rate: float  # percentual 0-100, 1 casa decimal
    total_publications: int
    platforms_active: list[PlatformCount]


class TimelinePoint(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class PublicationRow(BaseModel):
    content_item_id: str
    office_id: str
    title: str
    platform: str | None
    external_id: str | None
    url: str | None
    published_at: str | None
    content_status: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _office_ids_subquery(user_id):
    """Subquery com os IDs de todos os escritórios do usuário autenticado.

    Usado para filtrar qualquer query de analytics — garante que um usuário
    nunca veja dados agregados de escritórios de outro usuário.
    """
    return select(Office.id).where(Office.user_id == user_id).scalar_subquery()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """KPIs consolidados para os cards do topo do dashboard de analytics.

    - total_videos: total de ContentItems não deletados nos escritórios do usuário.
    - approval_rate: percentual de itens em status ready/published sobre o total.
    - total_publications: soma do tamanho de publication_log (JSONB) de todos
      os ContentItems do usuário — cada elemento do array é uma publicação
      bem sucedida em uma plataforma.
    - platforms_active: contagem de SocialAccounts ativas por plataforma.
    """
    office_ids = _office_ids_subquery(current_user.id)

    try:
        total_result = await session.execute(
            select(func.count(ContentItem.id)).where(
                ContentItem.office_id.in_(office_ids),
                ContentItem.deleted_at.is_(None),
            )
        )
        total_videos = total_result.scalar_one() or 0

        ready_result = await session.execute(
            select(func.count(ContentItem.id)).where(
                ContentItem.office_id.in_(office_ids),
                ContentItem.deleted_at.is_(None),
                ContentItem.status.in_(_APPROVED_STATUSES),
            )
        )
        ready_count = ready_result.scalar_one() or 0

        approval_rate = round((ready_count / total_videos) * 100, 1) if total_videos else 0.0

        pubs_result = await session.execute(
            select(
                func.coalesce(
                    func.sum(func.jsonb_array_length(ContentItem.publication_log)), 0
                )
            ).where(
                ContentItem.office_id.in_(office_ids),
                ContentItem.deleted_at.is_(None),
            )
        )
        total_publications = pubs_result.scalar_one() or 0

        platforms_result = await session.execute(
            select(SocialAccount.platform, func.count(SocialAccount.id))
            .where(
                SocialAccount.user_id == current_user.id,
                SocialAccount.is_active.is_(True),
            )
            .group_by(SocialAccount.platform)
        )
        platforms_active = [
            PlatformCount(platform=platform.value, count=count)
            for platform, count in platforms_result.all()
        ]

        return AnalyticsSummaryResponse(
            total_videos=total_videos,
            ready_count=ready_count,
            approval_rate=approval_rate,
            total_publications=int(total_publications),
            platforms_active=platforms_active,
        )
    except Exception:
        logger.exception(
            "Falha ao calcular analytics summary | user_id=%s", current_user.id
        )
        raise


@router.get("/timeline", response_model=list[TimelinePoint])
async def get_analytics_timeline(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Série temporal de ContentItems criados por dia, últimos `days` dias.

    Zero-fill: dias sem nenhum vídeo gerado aparecem com count=0, para o
    gráfico de linha no frontend não ter buracos na série.
    """
    office_ids = _office_ids_subquery(current_user.id)
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days - 1)).date()

    try:
        day_expr = func.date(ContentItem.created_at)
        result = await session.execute(
            select(day_expr.label("day"), func.count(ContentItem.id))
            .where(
                ContentItem.office_id.in_(office_ids),
                ContentItem.deleted_at.is_(None),
                ContentItem.created_at >= start_date,
            )
            .group_by(day_expr)
            .order_by(day_expr)
        )
        counts_by_day: dict[str, int] = {}
        for day, count in result.all():
            key = day.isoformat() if hasattr(day, "isoformat") else str(day)
            counts_by_day[key] = count

        points: list[TimelinePoint] = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            key = d.isoformat()
            points.append(TimelinePoint(date=key, count=counts_by_day.get(key, 0)))

        return points
    except Exception:
        logger.exception(
            "Falha ao calcular analytics timeline | user_id=%s | days=%s",
            current_user.id, days,
        )
        raise


@router.get("/publications", response_model=list[PublicationRow])
async def get_recent_publications(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Últimas publicações (flatten de ContentItem.publication_log).

    Não existe tabela SocialPost dedicada no schema atual — cada publicação
    bem sucedida fica registrada como um elemento do array JSONB
    publication_log em ContentItem (ver publisher/runner.py). Este endpoint
    busca os ContentItems com publicações não vazias, achata os arrays em
    linhas e retorna as mais recentes ordenadas por published_at desc.
    """
    office_ids = _office_ids_subquery(current_user.id)

    try:
        # Busca um lote generoso de itens com publicações — como cada item
        # pode ter mais de uma entrada (multi-plataforma), buscamos mais
        # itens do que `limit` para depois cortar após o flatten+sort.
        fetch_n = max(limit * 3, 50)
        result = await session.execute(
            select(ContentItem)
            .where(
                ContentItem.office_id.in_(office_ids),
                ContentItem.deleted_at.is_(None),
                func.jsonb_array_length(ContentItem.publication_log) > 0,
            )
            .order_by(ContentItem.updated_at.desc())
            .limit(fetch_n)
        )
        items = result.scalars().all()

        rows: list[PublicationRow] = []
        for item in items:
            for entry in (item.publication_log or []):
                if not isinstance(entry, dict):
                    continue
                rows.append(
                    PublicationRow(
                        content_item_id=str(item.id),
                        office_id=str(item.office_id),
                        title=item.title,
                        platform=entry.get("platform"),
                        external_id=entry.get("external_id"),
                        url=entry.get("url"),
                        published_at=entry.get("published_at"),
                        content_status=item.status.value,
                    )
                )

        rows.sort(key=lambda r: r.published_at or "", reverse=True)
        return rows[:limit]
    except Exception:
        logger.exception(
            "Falha ao buscar publicações recentes | user_id=%s", current_user.id
        )
        raise
