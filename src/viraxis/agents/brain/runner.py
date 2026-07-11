"""
Runner do agente BRAIN — orquestra DB + CrewAI + persistência.

Fluxo:
  1. Carrega NicheProfile do banco (async)
  2. Executa o Crew CrewAI (sync, via asyncio.to_thread para não bloquear o event loop)
  3. Persiste o ContentDecision resultante (async)
  4. Retorna o ContentDecision salvo
"""

import asyncio
import logging
import traceback
from uuid import UUID

from sqlalchemy import select, desc

from crewai import Crew, Process

from viraxis.agents.brain.agent import create_brain_agent
from viraxis.agents.brain.schemas import BrainDecisionInput, BrainDecisionOutput
from viraxis.agents.brain.tasks import create_decision_task
from viraxis.domain.models.content_decision import ContentDecision, DecisionType
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.agent_run_log import AgentRunLogRepository
from viraxis.infrastructure.repositories.content_decision import ContentDecisionRepository
from viraxis.infrastructure.repositories.niche_profile import NicheProfileRepository
from viraxis.infrastructure.repositories.raw_video import RawVideoRepository
from viraxis.agents.brain.schemas import RawVideoContext
from viraxis.domain.models.raw_video import RawVideo
from viraxis.domain.models.trend_snapshot import TrendSnapshot

logger = logging.getLogger(__name__)


def _run_crew_sync(niche_input: BrainDecisionInput, temperature: float) -> BrainDecisionOutput:
    """
    Executa o Crew de forma síncrona.
    Chamado via asyncio.to_thread para não bloquear o event loop.
    """
    agent = create_brain_agent(temperature=temperature)
    task = create_decision_task(agent, niche_input)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    # result.pydantic contém o BrainDecisionOutput validado pelo CrewAI
    if result.pydantic is None:
        raise RuntimeError(
            "BRAIN não retornou output Pydantic válido. "
            f"Raw output: {result.raw!r}"
        )

    return result.pydantic  # type: ignore[return-value]


async def run_brain(
    office_id: UUID,
    user_id: UUID,
    *,
    temperature: float | None = None,
    raw_video_id: UUID | None = None,
) -> ContentDecision:
    """
    Ponto de entrada principal do BRAIN.

    Args:
        office_id: UUID do escritório a ser analisado.
        user_id: UUID do usuário dono do escritório.
        temperature: Criatividade do LLM. Se None, usa brain_params do NicheProfile
                     ou o padrão (0.7).
        raw_video_id: UUID do vídeo bruto de referência (opcional). Vinculado à
                      ContentDecision para o RENDERER usar como contexto de estilo.

    Returns:
        ContentDecision persistido no banco com status=pending.

    Raises:
        ValueError: Se o escritório não tem NicheProfile configurado.
        RuntimeError: Se o BRAIN não gerar output válido.
    """
    async with AsyncSessionLocal() as session:
        # ---- 1. Carregar NicheProfile ----
        niche_repo = NicheProfileRepository(session)
        niche = await niche_repo.get_by_office_or_raise(office_id)

        # Temperatura: argumento > brain_params > padrão
        brain_params = niche.brain_params or {}
        resolved_temperature = (
            temperature
            if temperature is not None
            else float(brain_params.get("temperature", 0.7))
        )

        # ---- v2: Buscar vídeos brutos disponíveis ----
        # Só no modo "com referência" (raw_video_id presente). No modo "IA pura"
        # a biblioteca fica FORA do prompt — senão o LLM ancora a decisão em um
        # vídeo existente em vez de criar tema livre.
        raw_video_contexts: list[RawVideoContext] = []
        if raw_video_id is not None:
            raw_video_repo = RawVideoRepository(session)
            ready_videos = await raw_video_repo.get_ready_by_office(office_id)
            raw_video_contexts = [
                RawVideoContext(
                    id=str(v.id),
                    title=v.title or v.original_filename,
                    duration_seconds=v.duration_seconds,
                    tags=v.tags or [],
                    description=v.description,
                    ai_analysis=v.ai_analysis,
                )
                for v in ready_videos
            ]
            if raw_video_contexts:
                logger.info(
                    "BRAIN v2: %d vídeo(s) bruto(s) disponíveis para office=%s",
                    len(raw_video_contexts),
                    office_id,
                )

        # ---- v2: Buscar seasonal_multipliers dos TrendSnapshots recentes ----
        stmt = (
            select(TrendSnapshot.seasonal_multiplier)
            .where(TrendSnapshot.office_id == office_id)
            .where(TrendSnapshot.seasonal_multiplier.isnot(None))
            .order_by(desc(TrendSnapshot.captured_at))
            .limit(10)
        )
        result = await session.execute(stmt)
        raw_multipliers = result.scalars().all()
        seasonal_multipliers = [float(m) for m in raw_multipliers if m is not None]
        if seasonal_multipliers:
            logger.info(
                "BRAIN: %d seasonal_multiplier(s) carregados para office=%s | avg=%.2f",
                len(seasonal_multipliers),
                office_id,
                sum(seasonal_multipliers) / len(seasonal_multipliers),
            )

        # ---- Modo "com referência": carregar o vídeo bruto selecionado ----
        reference_video_ctx: RawVideoContext | None = None
        if raw_video_id is not None:
            ref_video = await session.get(RawVideo, raw_video_id)
            if ref_video is None or ref_video.office_id != office_id:
                raise ValueError(
                    f"Vídeo bruto {raw_video_id} não encontrado neste escritório."
                )
            reference_video_ctx = RawVideoContext(
                id=str(ref_video.id),
                title=ref_video.title or ref_video.original_filename,
                duration_seconds=ref_video.duration_seconds,
                tags=ref_video.tags or [],
                description=ref_video.description,
                ai_analysis=ref_video.ai_analysis,
            )
            logger.info(
                "BRAIN modo 'com referência' | office=%s | video=%s (%s)",
                office_id,
                raw_video_id,
                reference_video_ctx.title,
            )

        niche_input = BrainDecisionInput.from_niche_profile(
            niche,
            raw_videos=raw_video_contexts,
            reference_video=reference_video_ctx,
        )
        niche_input.seasonal_multipliers = seasonal_multipliers
        logger.info(
            "BRAIN iniciando análise | office=%s | nicho=%s | temp=%.2f | modo=%s",
            office_id,
            niche.niche_name,
            resolved_temperature,
            "com_referencia" if reference_video_ctx else "100_ia",
        )

        # ---- 2. Criar AgentRunLog com status=running ----
        log_repo = AgentRunLogRepository(session)
        run_log = await log_repo.create_running(
            agent_name="BrainAgent",
            task_name="create_decision_task",
            office_id=office_id,
            user_id=user_id,
            input_data=niche_input.model_dump(),
        )
        await session.flush()

        # ---- 3. Executar CrewAI (sync → thread) ----
        decision_output: BrainDecisionOutput | None = None
        try:
            decision_output = await asyncio.to_thread(
                _run_crew_sync, niche_input, resolved_temperature
            )
        except Exception as exc:
            tb = traceback.format_exc()
            await log_repo.mark_failed(run_log, error_message=str(exc), traceback=tb)
            await session.commit()
            logger.error("BRAIN falhou | office=%s | erro=%s", office_id, exc)
            raise

        logger.info(
            "BRAIN concluiu | tipo=%s | confiança=%.2f | hipótese=%.80s...",
            decision_output.decision_type,
            decision_output.confidence_score,
            decision_output.hypothesis,
        )

        # ---- 4. Persistir ContentDecision ----
        cd_repo = ContentDecisionRepository(session)
        decision = await cd_repo.create_decision(
            office_id=office_id,
            user_id=user_id,
            decision_type=DecisionType[decision_output.decision_type],
            hypothesis=decision_output.hypothesis,
            reasoning=decision_output.reasoning,
            input_signals=niche_input.model_dump(),
            selected_topic=decision_output.selected_topic,
            selected_archetype=decision_output.selected_archetype,
            selected_platform=decision_output.selected_platform,
            confidence_score=decision_output.confidence_score,
            raw_video_id=raw_video_id,  # v2: propagado do endpoint brain/run
        )

        # ---- 5. Atualizar log para success ----
        await log_repo.mark_success(
            run_log,
            output_data={
                "decision_id": str(decision.id),
                "decision_type": decision_output.decision_type,
                "confidence_score": decision_output.confidence_score,
            },
        )

        await session.commit()

        logger.info("ContentDecision salvo | id=%s | log=%s", decision.id, run_log.id)
        return decision


# ------------------------------------------------------------------ #
# Entrypoint CLI para teste rápido                                    #
# ------------------------------------------------------------------ #

async def _demo() -> None:
    """
    Demo: cria User -> Office -> NicheProfile e roda o BRAIN.
    Cria toda a hierarquia de FK necessária para o teste E2E.
    """
    import uuid
    from viraxis.domain.models.user import User, UserPlan
    from viraxis.domain.models.office import Office, OfficeStatus
    from viraxis.infrastructure.repositories.niche_profile import NicheProfileRepository

    # ---- 1. Criar User + Office (respeitando FK: users -> offices -> niche_profiles) ----
    async with AsyncSessionLocal() as session:
        # User demo
        user = User(
            email=f"demo-{uuid.uuid4().hex[:8]}@viraxis.dev",
            hashed_password="demo_hash_nao_usar_em_prod",
            full_name="Demo User BRAIN",
            plan=UserPlan.pro,
        )
        session.add(user)
        await session.flush()  # gera user.id

        # Office demo
        office = Office(
            user_id=user.id,
            name="Escritorio Demo - Financas",
            niche="financas-pessoais",
            status=OfficeStatus.active,
        )
        session.add(office)
        await session.flush()  # gera office.id

        office_id = office.id
        user_id = user.id

        # NicheProfile demo
        niche_repo = NicheProfileRepository(session)
        await niche_repo.upsert(
            office_id=office_id,
            user_id=user_id,
            niche_name="Financas Pessoais para Jovens",
            target_platforms=["tiktok", "instagram"],
            viral_archetypes={
                "revelacao": 0.40,
                "transformacao": 0.30,
                "tutorial_rapido": 0.20,
                "humor_educativo": 0.10,
            },
            content_style={
                "tom": "direto e descomplicado",
                "duracao": "30-60 segundos",
                "gancho": "pergunta retorica ou dado chocante",
            },
            top_keywords=[
                "investimento para iniciantes",
                "como sair das dividas",
                "renda passiva",
                "cartao de credito",
                "reserva de emergencia",
            ],
            brain_params={"temperature": 0.7},
            raw_notes="Publico: 18-30 anos, primeiros contatos com financas.",
        )
        await session.commit()

    print(f"\n[OK] Hierarquia criada: user={user_id} | office={office_id}\n")

    # ---- 2. Rodar o BRAIN ----
    decision = await run_brain(office_id, user_id)

    print("\n" + "=" * 60)
    print("DECISAO DO BRAIN")
    print("=" * 60)
    print(f"Tipo      : {decision.decision_type.value}")
    print(f"Status    : {decision.status.value}")
    print(f"Confianca : {decision.confidence_score:.0%}")
    print(f"Topico    : {decision.selected_topic}")
    print(f"Archetype : {decision.selected_archetype}")
    print(f"Plataforma: {decision.selected_platform}")
    print(f"\nHIPOTESE:\n{decision.hypothesis}")
    print(f"\nREASONING:\n{decision.reasoning}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_demo())
