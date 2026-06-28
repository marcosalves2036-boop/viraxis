"""Runner do agente SCOUT — PR-3 Fase 2.

Fluxo:
  1. Validar URL e detectar plataforma
  2. Extrair metadados via yt-dlp (asyncio.to_thread)
  3. Executar agente CrewAI para extrair sinais virais
  4. Persistir TrendSnapshot no banco
  5. Registrar AgentRunLog (success ou failed)
  6. Retornar TrendSnapshot salvo
"""

import asyncio
import logging
import traceback
from uuid import UUID

from crewai import Crew, Process

from viraxis.agents.scout.agent import create_scout_agent
from viraxis.agents.scout.schemas import ScoutInput, ScoutOutput
from viraxis.agents.scout.tasks import create_scout_analysis_task
from viraxis.domain.models.trend_snapshot import TrendSnapshot, TrendSource
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.agent_run_log import AgentRunLogRepository
from viraxis.infrastructure.ytdlp_client import (
    DownloadTimeoutError,
    UnsupportedPlatformError,
    VideoUnavailableError,
    YtdlpError,
    build_video_context,
    fetch_video_metadata,
)

logger = logging.getLogger(__name__)


def _run_scout_crew_sync(agent, task) -> ScoutOutput:
    """Executa o Crew SCOUT de forma síncrona — via asyncio.to_thread."""
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()
    if result.pydantic is None:
        raise RuntimeError(
            f"SCOUT não retornou output Pydantic válido. Raw: {result.raw!r}"
        )
    return result.pydantic  # type: ignore[return-value]


async def run_scout(office_id: UUID, user_id: UUID, url: str) -> TrendSnapshot:
    """Ponto de entrada principal do SCOUT.

    Args:
        office_id: UUID do escritório que está analisando a tendência
        user_id: UUID do usuário dono do escritório
        url: URL do vídeo viral (YouTube, Twitch, TikTok experimental)

    Returns:
        TrendSnapshot persistido no banco.

    Raises:
        UnsupportedPlatformError: URL de plataforma não suportada
        VideoUnavailableError: Vídeo privado ou removido
        DownloadTimeoutError: Timeout excedido
        YtdlpError: Outros erros do yt-dlp
        RuntimeError: SCOUT não gerou output válido
    """
    scout_input = ScoutInput(
        url=url,
        office_id=str(office_id),
    )

    async with AsyncSessionLocal() as session:
        log_repo = AgentRunLogRepository(session)

        # ---- 1. Criar AgentRunLog com status=running ----
        run_log = await log_repo.create_running(
            agent_name="ScoutAgent",
            task_name="create_scout_analysis_task",
            office_id=office_id,
            user_id=user_id,
            input_data={"url": url},
        )
        await session.flush()

        try:
            # ---- 2. Extrair metadados via yt-dlp ----
            logger.info("SCOUT iniciando | office=%s | url=%.80s", office_id, url)
            metadata = await fetch_video_metadata(url)
            video_context = build_video_context(metadata)

            # ---- 3. Executar agente CrewAI ----
            agent = create_scout_agent()
            task = create_scout_analysis_task(agent, scout_input, video_context)
            scout_output: ScoutOutput = await asyncio.to_thread(
                _run_scout_crew_sync, agent, task
            )

            # Enriquecer output com metadados do vídeo
            scout_output.video_title = scout_output.video_title or metadata.title
            scout_output.video_description = scout_output.video_description or metadata.description[:500]
            scout_output.platform_detected = metadata.platform
            scout_output.duration_seconds = metadata.duration_seconds
            scout_output.transcription_used = metadata.transcription is not None

            logger.info(
                "SCOUT concluiu | archetype=%s | engagement=%s | keywords=%d",
                scout_output.archetype,
                scout_output.engagement_estimate,
                len(scout_output.keywords),
            )

            # ---- 4. Persistir TrendSnapshot ----
            # Calcular viral_score baseado em engagement_estimate
            _engagement_to_score = {"low": 0.3, "medium": 0.6, "high": 0.9}
            computed_viral_score = _engagement_to_score.get(
                scout_output.engagement_estimate, 0.5
            )

            snapshot = TrendSnapshot(
                office_id=office_id,
                user_id=user_id,
                source=TrendSource.scout_url,
                source_url=url,
                # ── campos promovidos (migration 0006) ──
                platform=metadata.platform,
                video_title=metadata.title[:512] if metadata.title else None,
                duration_seconds=metadata.duration_seconds,
                view_count=metadata.view_count,
                like_count=metadata.like_count,
                viral_score=computed_viral_score,
                seasonal_multiplier=1.0,
                # ────────────────────────────────────────
                raw_metadata={
                    "title": metadata.title,
                    "description": metadata.description[:1000],
                    "duration_seconds": metadata.duration_seconds,
                    "view_count": metadata.view_count,
                    "like_count": metadata.like_count,
                    "uploader": metadata.uploader,
                    "thumbnail_url": metadata.thumbnail_url,
                    "platform": metadata.platform,
                },
                processed_signals=scout_output.model_dump(),
                transcription=metadata.transcription,
            )
            session.add(snapshot)

            # ---- 5. Atualizar log para success ----
            await log_repo.mark_success(
                run_log,
                output_data={
                    "archetype": scout_output.archetype,
                    "engagement_estimate": scout_output.engagement_estimate,
                    "keywords_count": len(scout_output.keywords),
                    "platform": metadata.platform,
                },
            )

            await session.commit()
            await session.refresh(snapshot)

            logger.info("TrendSnapshot salvo | id=%s | log=%s", snapshot.id, run_log.id)
            return snapshot

        except Exception as exc:
            tb = traceback.format_exc()
            await log_repo.mark_failed(run_log, error_message=str(exc), traceback=tb)
            await session.commit()
            logger.error("SCOUT falhou | office=%s | url=%s | erro=%s", office_id, url, exc)
            raise
