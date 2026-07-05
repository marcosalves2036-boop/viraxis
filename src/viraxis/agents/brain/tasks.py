"""Tasks CrewAI do agente BRAIN."""

from crewai import Agent, Task

from viraxis.agents.brain.schemas import BrainDecisionInput, BrainDecisionOutput


def create_decision_task(
    agent: Agent,
    niche_input: BrainDecisionInput,
) -> Task:
    """
    Cria a Task principal do BRAIN.

    Dois modos:
      - "100% IA" (reference_video is None): decide conteúdo novo do zero.
      - "com referência" (reference_video presente): decide COMO editar o
        vídeo bruto específico para máxima viralidade.

    O output_pydantic instrui o CrewAI a forçar JSON válido alinhado ao schema
    BrainDecisionOutput. O LLM recebe o schema automaticamente no system prompt.
    """
    context = niche_input.to_context_string()

    if niche_input.reference_video is not None:
        # ---- Modo "com referência": decidir a ESTRATÉGIA DE EDIÇÃO ----
        rv = niche_input.reference_video
        duration_str = (
            f"{rv.duration_seconds:.0f}" if rv.duration_seconds else "desconhecida"
        )
        description = f"""
Você recebeu um vídeo bruto que SERÁ editado e publicado. Ele já foi escolhido
pelo operador — sua tarefa NÃO é escolher um tema novo, e sim decidir a
ESTRATÉGIA DE EDIÇÃO deste vídeo específico para maximizar a viralidade.

=== VÍDEO A EDITAR ===
ID: {rv.id}
Título: {rv.title or 'sem título'}
Duração: {duration_str}s
Tags: {', '.join(rv.tags) or 'nenhuma'}
Descrição: {rv.description or 'nenhuma'}
======================

=== PERFIL DO NICHO ===
{context}
======================

INSTRUÇÕES:
1. Analise o potencial viral DESTE vídeo com base no nicho, archetypes e keywords.

2. Decida a estratégia de edição: qual é o hook principal (primeiros 3s)?
   Qual parte manter/cortar? Qual ritmo de cortes? Texto na tela?

3. Defina: archetype do resultado final (selected_archetype), plataforma alvo
   (selected_platform) e um selected_topic que descreva o conteúdo final no
   formato '[video:{rv.id[:8]}] Título do conteúdo editado'.

4. hypothesis deve descrever: "Este vídeo vai performar porque [razão baseada
   no conteúdo do vídeo + sinais do nicho]."

5. Use decision_type = "content_topic" e preencha raw_video_id = "{rv.id}".

6. Seja honesto no confidence_score:
   - 0.9+ : vídeo com fit óbvio com archetype dominante
   - 0.7-0.9: bom fit, alguma incerteza
   - 0.5-0.7: fit exploratório
   - <0.5: vídeo com baixo potencial no nicho (sinalize no reasoning)
""".strip()
        expected_output = (
            "Um objeto JSON válido seguindo exatamente o schema BrainDecisionOutput, "
            "com hypothesis focada no potencial viral do vídeo de referência, "
            "reasoning estruturado com as chaves 'sinais_identificados', "
            "'alternativas_descartadas' e 'justificativa_final' descrevendo a "
            "estratégia de edição, raw_video_id preenchido com o ID do vídeo, "
            "e confidence_score honesto."
        )
    else:
        # ---- Modo "100% IA": decidir conteúdo novo do zero ----
        description = f"""
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
""".strip()
        expected_output = (
            "Um objeto JSON válido seguindo exatamente o schema BrainDecisionOutput, "
            "com hypothesis detalhada, reasoning estruturado com as chaves "
            "'sinais_identificados', 'alternativas_descartadas' e 'justificativa_final', "
            "campos selected_* preenchidos quando aplicável, e confidence_score honesto."
        )

    return Task(
        description=description,
        expected_output=expected_output,
        output_pydantic=BrainDecisionOutput,
        agent=agent,
    )
