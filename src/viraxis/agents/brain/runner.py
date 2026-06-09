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
from uuid import UUID

from crewai import Crew, Process

from viraxis.agents.brain.agent import create_brain_agent
from viraxis.agents.brain.schemas import BrainDecisionInput, BrainDecisionOutput
from viraxis.agents.brain.tasks import create_decision_task
from viraxis.domain.models.content_decision import ContentDecision, DecisionType
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.content_decision import ContentDecisionRepository
from viraxis.infrastructure.repositories.niche_profile import NicheProfileRepository

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
) -> ContentDecision:
    """
    Ponto de entrada principal do BRAIN.

    Args:
        office_id: UUID do escritório a ser analisado.
        user_id: UUID do usuário dono do escritório.
        temperature: Criatividade do LLM. Se None, usa brain_params do NicheProfile
                     ou o padrão (0.7).

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

        niche_input = BrainDecisionInput.from_niche_profile(niche)
        logger.info(
            "BRAIN iniciando análise | office=%s | nicho=%s | temp=%.2f",
            office_id,
            niche.niche_name,
            resolved_temperature,
        )

        # ---- 2. Executar CrewAI (sync → thread) ----
        decision_output: BrainDecisionOutput = await asyncio.to_thread(
            _run_crew_sync, niche_input, resolved_temperature
        )

        logger.info(
            "BRAIN concluiu | tipo=%s | confiança=%.2f | hipótese=%.80s...",
            decision_output.decision_type,
            decision_output.confidence_score,
            decision_output.hypothesis,
        )

        # ---- 3. Persistir ContentDecision ----
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
        )

        await session.commit()

        logger.info("ContentDecision salvo | id=%s", decision.id)
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
