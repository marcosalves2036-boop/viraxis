"""Tasks Celery do pipeline VIRAXIS — PR-6 Fase 2.

Cada task envolve um runner async (BRAIN, SCOUT, RENDERER, PUBLISHER) e
executa via asyncio.run() porque o worker Celery é síncrono.

Padrão de instrumentacao:
  - bind=True para acesso a self.request.id (celery_task_id)
  - autoretry_for + max_retries para resiliência
  - AgentRunLog ja é criado dentro dos runners — não duplicar aqui
"""

import asyncio
import logging
from uuid import UUID

from celery import shared_task

logger = logging.getLogger(__name__)

# ── Constantes de retry ────────────────────────────────────────────────────────

_AI_TASK_RETRY = {
    "autoretry_for": (Exception,),
    "max_retries": 2,
    "retry_backoff": True,         # 2s, 4s
    "retry_backoff_max": 30,
    "retry_jitter": True,
    "dont_autoretry_for": (ValueError,),  # erros de validação não fazem retry
}


# ── BRAIN ──────────────────────────────────────────────────────────────────────

@shared_task(
    name="viraxis.worker.tasks.run_brain_task",
    bind=True,
    **_AI_TASK_RETRY,
)
def run_brain_task(
    self,
    office_id: str,
    user_id: str,
    temperature: float | None = None,
) -> dict:
    """Executa o agente BRAIN para um escritório.

    Args:
        office_id: UUID do escritório (str).
        user_id: UUID do usuário (str).
        temperature: Criatividade do LLM. None = usa brain_params do NicheProfile.

    Returns:
        dict com decision_id, decision_type e confidence_score.
    """
    from viraxis.agents.brain.runner import run_brain  # import lazy

    logger.info(
        "BRAIN task iniciando | celery_id=%s | office=%s",
        self.request.id, office_id,
    )

    decision = asyncio.run(
        run_brain(UUID(office_id), UUID(user_id), temperature=temperature)
    )

    result = {
        "decision_id": str(decision.id),
        "decision_type": decision.decision_type.value,
        "confidence_score": decision.confidence_score,
        "selected_topic": decision.selected_topic,
        "selected_platform": decision.selected_platform,
    }
    logger.info("BRAIN task concluida | %s", result)
    return result


# ── SCOUT ──────────────────────────────────────────────────────────────────────

@shared_task(
    name="viraxis.worker.tasks.run_scout_task",
    bind=True,
    **_AI_TASK_RETRY,
)
def run_scout_task(
    self,
    office_id: str,
    user_id: str,
    url: str,
) -> dict:
    """Executa o agente SCOUT para analisar um vídeo viral.

    Args:
        office_id: UUID do escritório (str).
        user_id: UUID do usuário (str).
        url: URL do vídeo (YouTube, Twitch, TikTok experimental).

    Returns:
        dict com snapshot_id, platform, archetype e engagement_estimate.
    """
    from viraxis.agents.scout.runner import run_scout  # import lazy
    from viraxis.infrastructure.ytdlp_client import (
        DownloadTimeoutError,
        UnsupportedPlatformError,
        VideoUnavailableError,
    )

    logger.info(
        "SCOUT task iniciando | celery_id=%s | office=%s | url=%.80s",
        self.request.id, office_id, url,
    )

    try:
        snapshot = asyncio.run(run_scout(UUID(office_id), UUID(user_id), url))
    except (UnsupportedPlatformError, VideoUnavailableError) as exc:
        # Erro de domínio — não faz retry
        raise ValueError(str(exc)) from exc
    except DownloadTimeoutError as exc:
        # Timeout pode ser transitório — deixa o autoretry agir
        raise RuntimeError(str(exc)) from exc

    signals = snapshot.processed_signals or {}
    result = {
        "snapshot_id": str(snapshot.id),
        "platform": signals.get("platform_detected", "unknown"),
        "archetype": signals.get("archetype"),
        "engagement_estimate": signals.get("engagement_estimate", "medium"),
        "keywords_count": len(signals.get("keywords", [])),
    }
    logger.info("SCOUT task concluida | %s", result)
    return result


# ── RENDERER ───────────────────────────────────────────────────────────────────

@shared_task(
    name="viraxis.worker.tasks.run_renderer_task",
    bind=True,
    **_AI_TASK_RETRY,
)
def run_renderer_task(
    self,
    office_id: str,
    user_id: str,
    decision_id: str,
    temperature: float | None = None,
) -> dict:
    """Executa o agente RENDERER para gerar roteiro a partir de uma decisão.

    Args:
        office_id: UUID do escritório (str).
        user_id: UUID do usuário (str).
        decision_id: UUID da ContentDecision gerada pelo BRAIN (str).
        temperature: Criatividade. Padrão 0.8.

    Returns:
        dict com content_item_id, title e duration_seconds.
    """
    from viraxis.agents.renderer.runner import run_renderer  # import lazy

    logger.info(
        "RENDERER task iniciando | celery_id=%s | office=%s | decision=%s",
        self.request.id, office_id, decision_id,
    )

    content_item = asyncio.run(
        run_renderer(
            UUID(office_id),
            UUID(user_id),
            UUID(decision_id),
            temperature=temperature,
        )
    )

    result = {
        "content_item_id": str(content_item.id),
        "title": content_item.title,
        "duration_seconds": content_item.duration_seconds,
        "status": content_item.status.value,
    }
    logger.info("RENDERER task concluida | %s", result)
    return result


# ── PUBLISHER ─────────────────────────────────────────────────────────────────

@shared_task(
    name="viraxis.worker.tasks.run_publisher_task",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    dont_autoretry_for=(ValueError,),
)
def run_publisher_task(
    self,
    office_id: str,
    user_id: str,
    content_item_id: str,
    targets: list[dict] | None = None,
) -> dict:
    """Publica um ContentItem nas redes sociais.

    Args:
        office_id: UUID do escritorio (str).
        user_id: UUID do usuario (str).
        content_item_id: UUID do ContentItem (str).
        targets: Lista de PublishTarget dicts com platform, social_account_id, etc.

    Returns:
        dict com successful_platforms e failed_platforms.
    """
    from viraxis.agents.publisher.runner import run_publisher  # import lazy
    from viraxis.agents.publisher.schemas import PublisherInput, PublishTarget

    logger.info(
        "PUBLISHER task iniciando | celery_id=%s | item=%s | targets=%s",
        self.request.id, content_item_id,
        [t.get("platform") for t in (targets or [])],
    )

    parsed_targets = [PublishTarget(**t) for t in (targets or [])]

    async def _get_item_info():
        from viraxis.infrastructure.database.session import AsyncSessionLocal  # noqa
        from viraxis.domain.models.content_item import ContentItem  # noqa
        from sqlalchemy import select  # noqa
        from uuid import UUID  # noqa
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ContentItem).where(ContentItem.id == UUID(content_item_id))
            )
            item = result.scalar_one_or_none()
            if not item:
                raise ValueError(f"ContentItem {content_item_id} nao encontrado")
            return item.title, item.script

    title, script = asyncio.run(_get_item_info())

    publisher_input = PublisherInput(
        content_item_id=content_item_id,
        office_id=office_id,
        user_id=user_id,
        title=title,
        script=script,
        targets=parsed_targets,
    )

    output = asyncio.run(run_publisher(publisher_input))

    result = {
        "content_item_id": content_item_id,
        "successful_platforms": output.successful_platforms,
        "failed_platforms": output.failed_platforms,
    }
    logger.info("PUBLISHER task concluida | %s", result)
    return result


# ── BEAT: Limpeza periódica ────────────────────────────────────────────────────

@shared_task(name="viraxis.worker.tasks.cleanup_agent_logs_task")
def cleanup_agent_logs_task() -> dict:
    """Remove AgentRunLogs com mais de 90 dias. Roda todo dia às 3:00 via Beat."""
    from viraxis.infrastructure.repositories.agent_run_log import AgentRunLogRepository
    from viraxis.infrastructure.database.session import AsyncSessionLocal

    async def _cleanup() -> int:
        async with AsyncSessionLocal() as session:
            repo = AgentRunLogRepository(session)
            deleted = await repo.cleanup_old_logs()
            await session.commit()
            return deleted

    deleted_count = asyncio.run(_cleanup())
    logger.info("Limpeza AgentRunLog | deletados=%d registros (>90 dias)", deleted_count)
    return {"deleted_count": deleted_count}
