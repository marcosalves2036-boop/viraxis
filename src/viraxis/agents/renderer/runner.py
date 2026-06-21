"""Runner do agente RENDERER — PR-4 Fase 2.

Fluxo:
  1. Carrega ContentDecision + NicheProfile do banco
  2. Opcionalmente busca TrendSnapshot recente para enriquecer o contexto
  3. Executa agente CrewAI para gerar roteiro estruturado
  4. Persiste ContentItem com script gerado (status=draft)
  5. Avança ContentDecision para status=executing
  6. Registra AgentRunLog (success ou failed)
  7. Retorna ContentItem salvo
"""

import asyncio
import logging
import traceback
from uuid import UUID

from crewai import Crew, Process
from sqlalchemy import desc, select

from viraxis.agents.renderer.agent import create_renderer_agent
from viraxis.agents.renderer.schemas import RendererInput, RendererOutput
from viraxis.agents.renderer.tasks import create_render_task
from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.trend_snapshot import TrendSnapshot
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.agent_run_log import AgentRunLogRepository
from viraxis.infrastructure.repositories.niche_profile import NicheProfileRepository

logger = logging.getLogger(__name__)


def _run_renderer_crew_sync(agent, task) -> RendererOutput:
    """Executa o Crew RENDERER de forma síncrona — via asyncio.to_thread."""
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()
    if result.pydantic is None:
        raise RuntimeError(
            f"RENDERER não retornou output Pydantic válido. Raw: {result.raw!r}"
        )
    return result.pydantic  # type: ignore[return-value]


async def run_renderer(
    office_id: UUID,
    user_id: UUID,
    decision_id: UUID,
    *,
    temperature: float | None = None,
) -> ContentItem:
    """Gera um roteiro de vídeo a partir de uma ContentDecision.

    Args:
        office_id: UUID do escritório.
        user_id: UUID do usuário.
        decision_id: UUID da ContentDecision gerada pelo BRAIN.
        temperature: Criatividade do LLM. Padrão 0.8 (mais criativo que BRAIN).

    Returns:
        ContentItem persistido com script gerado e status=draft.

    Raises:
        ValueError: Decisão não encontrada ou já processada.
        RuntimeError: RENDERER não gerou output válido.
    """
    resolved_temperature = temperature if temperature is not None else 0.8

    async with AsyncSessionLocal() as session:
        # ---- 1. Carregar ContentDecision ----
        result = await session.execute(
            select(ContentDecision).where(
                ContentDecision.id == decision_id,
                ContentDecision.office_id == office_id,
            )
        )
        decision = result.scalar_one_or_none()
        if not decision:
            raise ValueError(f"ContentDecision {decision_id} não encontrada para office {office_id}")

        if decision.status not in (DecisionStatus.pending, DecisionStatus.approved):
            raise ValueError(
                f"Decisão {decision_id} está com status={decision.status.value}. "
                "Apenas pending ou approved podem ser renderizadas."
            )

        # ---- 2. Carregar NicheProfile ----
        niche_repo = NicheProfileRepository(session)
        niche = await niche_repo.get_by_office_or_raise(office_id)

        # ---- 3. Buscar TrendSnapshot recente (opcional) ----
        trend_result = await session.execute(
            select(TrendSnapshot)
            .where(TrendSnapshot.office_id == office_id)
            .order_by(desc(TrendSnapshot.captured_at))
            .limit(1)
        )
        latest_trend: TrendSnapshot | None = trend_result.scalar_one_or_none()
        trend_signals = latest_trend.processed_signals if latest_trend else {}

        # ---- 4. Construir RendererInput ----
        renderer_input = RendererInput(
            decision_type=decision.decision_type.value,
            selected_topic=decision.selected_topic or "",
            selected_archetype=decision.selected_archetype or "",
            selected_platform=decision.selected_platform or "tiktok",
            hypothesis=decision.hypothesis,
            niche_name=niche.niche_name,
            content_style=niche.content_style or {},
            target_audience=niche.raw_notes,
            trend_keywords=trend_signals.get("keywords", [])[:8],
            trend_hook_pattern=trend_signals.get("hook_pattern"),
            trend_summary=trend_signals.get("summary"),
        )

        # ---- 5. Criar AgentRunLog ----
        log_repo = AgentRunLogRepository(session)
        run_log = await log_repo.create_running(
            agent_name="RendererAgent",
            task_name="create_render_task",
            office_id=office_id,
            user_id=user_id,
            input_data={
                "decision_id": str(decision_id),
                "topic": renderer_input.selected_topic,
                "archetype": renderer_input.selected_archetype,
                "platform": renderer_input.selected_platform,
            },
        )
        await session.flush()

        logger.info(
            "RENDERER iniciando | office=%s | decision=%s | topic=%.60s",
            office_id, decision_id, renderer_input.selected_topic,
        )

        try:
            # ---- 6. Executar CrewAI ----
            agent = create_renderer_agent(temperature=resolved_temperature)
            task = create_render_task(agent, renderer_input)
            renderer_output: RendererOutput = await asyncio.to_thread(
                _run_renderer_crew_sync, agent, task
            )

            logger.info(
                "RENDERER concluiu | title=%.60s | duration=%ds | confidence=%.2f",
                renderer_output.title,
                renderer_output.total_duration_estimate_seconds,
                renderer_output.confidence_score,
            )

            # ---- 7. Persistir ContentItem ----
            content_item = ContentItem(
                office_id=office_id,
                user_id=user_id,
                decision_id=decision_id,
                title=renderer_output.title,
                script=renderer_output.full_script,
                status=ContentStatus.draft,
                duration_seconds=float(renderer_output.total_duration_estimate_seconds),
                production_meta={
                    "renderer_output": renderer_output.model_dump(),
                    "archetype_applied": renderer_output.archetype_applied,
                    "platform_adaptations": renderer_output.platform_adaptations,
                    "confidence_score": renderer_output.confidence_score,
                    "trend_snapshot_id": str(latest_trend.id) if latest_trend else None,
                },
            )
            session.add(content_item)

            # ---- 8. Avançar status da Decisão para executing ----
            decision.status = DecisionStatus.executing
            session.add(decision)

            # ---- 9. Marcar log como success ----
            await log_repo.mark_success(
                run_log,
                output_data={
                    "title": renderer_output.title,
                    "duration_seconds": renderer_output.total_duration_estimate_seconds,
                    "confidence_score": renderer_output.confidence_score,
                },
            )

            await session.commit()
            await session.refresh(content_item)

            logger.info(
                "ContentItem salvo | id=%s | decision=%s | log=%s",
                content_item.id, decision_id, run_log.id,
            )
            return content_item

        except Exception as exc:
            tb = traceback.format_exc()
            await log_repo.mark_failed(run_log, error_message=str(exc), traceback=tb)
            await session.commit()
            logger.error("RENDERER falhou | office=%s | decision=%s | erro=%s", office_id, decision_id, exc)
            raise
