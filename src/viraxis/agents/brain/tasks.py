"""Tasks CrewAI do agente BRAIN."""

from crewai import Agent, Task

from viraxis.agents.brain.schemas import BrainDecisionInput, BrainDecisionOutput


def create_decision_task(
    agent: Agent,
    niche_input: BrainDecisionInput,
) -> Task:
    """
    Cria a Task principal do BRAIN: analisar o nicho e retornar uma decisão estruturada.

    O output_pydantic instrui o CrewAI a forçar JSON válido alinhado ao schema
    BrainDecisionOutput. O LLM recebe o schema automaticamente no system prompt.
    """
    context = niche_input.to_context_string()

    return Task(
        description=f"""
Você recebeu os dados de um Escritório Viral Autônomo. Analise o perfil de nicho
abaixo e tome UMA decisão estratégica de conteúdo.

=== PERFIL DO NICHO ===
{context}
======================

INSTRUÇÕES:
1. Identifique os sinais mais relevantes: qual archetype tem maior peso histórico?
   Quais keywords estão em alta? Qual plataforma tem melhor fit com o estilo editorial?

2. Formule uma hipótese clara: "Este conteúdo vai performar porque [razão específica
   baseada nos dados acima]."

3. Documente as alternativas que você descartou e por quê.

4. Escolha o decision_type mais adequado para o momento:
   - "content_topic": BRAIN está escolhendo um tema/tópico específico
   - "archetype_selection": BRAIN está definindo o formato/archetype dominante
   - "platform_targeting": BRAIN está priorizando uma plataforma específica

5. Seja honesto no confidence_score:
   - 0.9+ : dados robustos, padrão claro
   - 0.7-0.9: boa evidência, alguma incerteza
   - 0.5-0.7: dados limitados, decisão exploratória
   - <0.5: dados insuficientes (sinalize no reasoning)
""".strip(),
        expected_output=(
            "Um objeto JSON válido seguindo exatamente o schema BrainDecisionOutput, "
            "com hypothesis detalhada, reasoning estruturado com as chaves "
            "'sinais_identificados', 'alternativas_descartadas' e 'justificativa_final', "
            "campos selected_* preenchidos quando aplicável, e confidence_score honesto."
        ),
        output_pydantic=BrainDecisionOutput,
        agent=agent,
    )
