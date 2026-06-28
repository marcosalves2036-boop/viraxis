"""Task CrewAI para o agente RENDERER."""

from crewai import Agent, Task

from viraxis.agents.renderer.schemas import RendererInput, RendererOutput

_SECTION_GUIDE = {
    "hook": (
        "Os primeiros 3 segundos decidem se o vídeo será assistido ou não. "
        "Sem introdução, sem 'olá', direto ao impacto. "
        "Use: pergunta provocativa, estatística chocante, afirmação contraintuitiva, ou cena in media res."
    ),
    "development": (
        "Desenvolva a promessa do hook. Entregue valor real em 15-30 segundos. "
        "Use 2-3 pontos concretos, não abstrações. "
        "Mantenha ritmo — frases curtas, transições rápidas."
    ),
    "climax": (
        "O momento de maior valor ou surpresa do vídeo. "
        "Pode ser a revelação final, a virada, o dado mais impactante. "
        "É aqui que o viewer decide salvar ou compartilhar."
    ),
    "cta": (
        "Finalize com uma ação natural, não forçada. "
        "Evite 'curte e compartilha'. Prefira: comentário engajador, salvamento, seguir. "
        "Max 10 segundos — não prolongue após o clímax."
    ),
}

_PLATFORM_GUIDE = {
    "tiktok": "Linguagem jovem, informal, gírias aceitáveis. Trending sounds em mind. Max 60s.",
    "instagram": "Visual forte, legendas descritivas para modo silencioso. Hashtags relevantes.",
    "youtube": "Pode ter mais desenvolvimento. Tom educativo aceito. Max 90s.",
    "kwai": "Similar TikTok. Conteúdo regional/popular tem mais alcance.",
}


def create_render_task(
    agent: Agent,
    renderer_input: RendererInput,
) -> Task:
    """Cria a Task CrewAI de geração de roteiro.

    Args:
        agent: O agente RENDERER instanciado.
        renderer_input: Contexto completo da decisão do BRAIN + nicho.

    Returns:
        Task configurada com output_pydantic=RendererOutput.
    """
    platform = renderer_input.selected_platform.lower()
    platform_hint = _PLATFORM_GUIDE.get(platform, f"Adapte para {platform}.")

    # Contexto de tendências (SCOUT) se disponível
    trend_context = ""
    if renderer_input.trend_keywords:
        trend_context = f"""
TENDÊNCIAS CAPTURADAS PELO SCOUT:
- Keywords em alta: {', '.join(renderer_input.trend_keywords[:8])}
- Padrão de hook identificado: {renderer_input.trend_hook_pattern or 'não disponível'}
- Resumo de conteúdo viral recente: {renderer_input.trend_summary or 'não disponível'}

Use esses sinais para tornar o roteiro mais relevante, mas não os force artificialmente.
"""

    description = f"""
Gere um roteiro de vídeo viral completo baseado na seguinte decisão estratégica:

DECISÃO DO BRAIN:
- Tipo: {renderer_input.decision_type}
- Tópico: {renderer_input.selected_topic}
- Archetype viral: {renderer_input.selected_archetype}
- Plataforma alvo: {renderer_input.selected_platform}
- Hipótese: {renderer_input.hypothesis}

CONTEXTO DO NICHO:
- Nicho: {renderer_input.niche_name}
- Estilo editorial: {renderer_input.content_style}
- Público-alvo: {renderer_input.target_audience or 'não especificado'}

ADAPTAÇÃO DE PLATAFORMA:
{platform_hint}
{trend_context}

{ref_video_context}

ESTRUTURA OBRIGATÓRIA (4 seções):

1. HOOK (3-8s):
{_SECTION_GUIDE['hook']}

2. DEVELOPMENT (15-30s):
{_SECTION_GUIDE['development']}

3. CLIMAX (5-15s):
{_SECTION_GUIDE['climax']}

4. CTA (5-10s):
{_SECTION_GUIDE['cta']}

ENTREGUE:
- Título otimizado para SEO/retenção (max 512 chars)
- As 4 seções com texto, estimativa de duração e notas visuais
- Roteiro completo contínuo (full_script)
- Duração total estimada
- Descrição das adaptações feitas para {platform}
- Score de confiança (0.0-1.0) na qualidade do roteiro
""".strip()

    # Contexto de vídeo de referência (v2) — para coerência de estilo
    ref_video_context = ""
    if renderer_input.reference_video:
        rv = renderer_input.reference_video
        title = rv.get("title", "sem título")
        tags = ", ".join(rv.get("tags", [])) or "sem tags"
        desc = rv.get("description") or ""
        dur = rv.get("duration_seconds")
        dur_str = f"{int(dur)}s" if dur else "desconhecida"
        ref_video_context = f"""
VÍDEO DE REFERÊNCIA (use como base de estilo):
- Título: {title}
- Duração: {dur_str}
- Tags: {tags}
{f"- Descrição: {desc[:300]}" if desc else ""}

Analise o estilo narrativo, vocabulário e tom emocional deste vídeo e aplique
ao roteiro gerado. O resultado deve soar como continuação natural deste canal.
""".strip()

    return Task(
        description=description,
        agent=agent,
        expected_output=(
            "JSON estruturado com título, 4 seções (hook/development/climax/cta) "
            "cada uma com content, duration_estimate_seconds e visual_notes, "
            "full_script completo, total_duration_estimate_seconds, "
            "archetype_applied, platform_adaptations e confidence_score."
        ),
        output_pydantic=RendererOutput,
    )
