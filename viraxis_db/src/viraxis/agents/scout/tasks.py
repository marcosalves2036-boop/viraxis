"""Tasks CrewAI do agente SCOUT."""

from crewai import Agent, Task

from viraxis.agents.scout.schemas import ScoutInput, ScoutOutput


def create_scout_analysis_task(agent: Agent, scout_input: ScoutInput, video_context: str) -> Task:
    """Cria a task de análise de sinais virais.

    Args:
        agent: O agente SCOUT criado por create_scout_agent()
        scout_input: Input com URL e contexto do escritório
        video_context: Texto com título + descrição + transcrição parcial do vídeo
    """
    context_block = f"""
URL analisada: {scout_input.url}
Nicho do escritório: {scout_input.niche_name or 'não especificado'}
Plataformas alvo: {', '.join(scout_input.target_platforms) if scout_input.target_platforms else 'não especificadas'}

CONTEÚDO DO VÍDEO:
{video_context}
""".strip()

    return Task(
        description=f"""
Analise o conteúdo do vídeo abaixo e extraia os sinais virais.

{context_block}

Sua análise deve incluir:
1. keywords: lista de 5 a 15 termos de alta performance presentes ou implícitos
2. archetype: o archetype viral principal (revelacao, transformacao, tutorial_rapido, humor_educativo, comparacao, desafio, bastidores)
3. hook_pattern: o padrão de gancho (pergunta_retorica, dado_chocante, historia_pessoal, promessa_resultado, contra_intuicao)
4. engagement_estimate: low, medium ou high baseado na força do conteúdo
5. hook_text: os primeiros 3-5 segundos do roteiro identificados
6. summary: resumo objetivo em 2-3 frases
""",
        expected_output="""
JSON válido com os campos: keywords (list), archetype (str), hook_pattern (str),
engagement_estimate (low/medium/high), hook_text (str|null), summary (str|null).
Responda APENAS com o JSON, sem markdown, sem explicações adicionais.
""",
        agent=agent,
        output_pydantic=ScoutOutput,
    )
