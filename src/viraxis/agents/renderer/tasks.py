"""Tasks CrewAI para o agente RENDERER.

Dois modos:
  - create_render_task: modo "100% IA" — gera roteiro novo (RendererOutput).
  - create_editing_plan_task: modo "com referência" — gera plano de edição
    do vídeo bruto específico (EditingPlanOutput).
"""

from crewai import Agent, Task

from viraxis.agents.renderer.schemas import (
    EditingPlanOutput,
    RendererInput,
    RendererOutput,
)

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
    """Cria a Task CrewAI de geração de roteiro novo (modo '100% IA').

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

    # Contexto de vídeo de referência (estilo) — definido ANTES do uso na description
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


def create_editing_plan_task(
    agent: Agent,
    renderer_input: RendererInput,
) -> Task:
    """Cria a Task CrewAI de plano de edição (modo 'com referência').

    O vídeo bruto JÁ EXISTE — o RENDERER não escreve roteiro novo, e sim um
    plano de edição concreto: cortes, hook, textos na tela, trilha, ritmo.

    Args:
        agent: O agente RENDERER instanciado.
        renderer_input: Contexto da decisão do BRAIN + nicho, com
            reference_video obrigatório.

    Returns:
        Task configurada com output_pydantic=EditingPlanOutput.

    Raises:
        ValueError: Se renderer_input.reference_video ausente.
    """
    if not renderer_input.reference_video:
        raise ValueError(
            "create_editing_plan_task exige renderer_input.reference_video."
        )

    rv = renderer_input.reference_video
    title = rv.get("title", "sem título")
    tags = ", ".join(rv.get("tags", [])) or "sem tags"
    desc = rv.get("description") or "nenhuma"
    dur = rv.get("duration_seconds")
    dur_str = f"{dur:.0f}s" if dur else "desconhecida"

    platform = renderer_input.selected_platform.lower()
    platform_hint = _PLATFORM_GUIDE.get(platform, f"Adapte para {platform}.")

    description = f"""
Você é o editor-chefe. Um vídeo bruto REAL será editado e publicado.
NÃO escreva um roteiro novo — gere um PLANO DE EDIÇÃO concreto e executável
para este vídeo específico.

=== VÍDEO A EDITAR ===
- Título: {title}
- Duração bruta: {dur_str}
- Tags: {tags}
- Descrição: {desc}
======================

DECISÃO ESTRATÉGICA DO BRAIN (estratégia de edição já aprovada):
- Tópico/direção: {renderer_input.selected_topic}
- Archetype alvo: {renderer_input.selected_archetype}
- Plataforma alvo: {renderer_input.selected_platform}
- Hipótese: {renderer_input.hypothesis}

CONTEXTO DO NICHO:
- Nicho: {renderer_input.niche_name}
- Estilo editorial: {renderer_input.content_style}
- Público-alvo: {renderer_input.target_audience or 'não especificado'}

ADAPTAÇÃO DE PLATAFORMA:
{platform_hint}

ENTREGUE UM PLANO DE EDIÇÃO com:

1. hook_timestamp: o segundo exato (estimado) do vídeo bruto onde está o
   momento mais impactante — ele deve virar os primeiros 3s do vídeo final.

2. suggested_cuts: lista de instruções instruction_type="cut" ou "keep" com
   timestamp_start/timestamp_end (dentro da duração bruta de {dur_str}),
   description clara do que cortar/manter e priority
   (essential/recommended/optional).

3. overlay_texts: instruções instruction_type="overlay_text" com o texto
   exato a exibir na tela e em qual trecho (timestamps).

4. music_suggestion: estilo/vibe de trilha sonora (ou None se o áudio
   original for o ponto forte).

5. estimated_final_duration: duração final estimada em segundos após os
   cortes (ideal para {platform}: siga o guia da plataforma acima).

6. platform_adaptations: dict com chaves por plataforma (ex: "tiktok",
   "instagram") descrevendo ajustes específicos.

7. production_notes: instruções gerais para o editor humano — ritmo,
   transições, tom, o que NÃO fazer.

REGRAS:
- Todos os timestamps devem estar dentro da duração bruta do vídeo.
- Instruções "essential" são o mínimo para o vídeo funcionar; seja seletivo.
- title deve ser o título do vídeo FINAL editado, otimizado para retenção.
- archetype_used deve coincidir com o archetype da decisão.
""".strip()

    return Task(
        description=description,
        agent=agent,
        expected_output=(
            "JSON estruturado seguindo EditingPlanOutput: mode='editing_plan', "
            "title, hook_timestamp, suggested_cuts e overlay_texts como listas de "
            "EditingInstruction (timestamp_start, timestamp_end, instruction_type, "
            "description, priority), music_suggestion, estimated_final_duration, "
            "platform_adaptations (dict) e production_notes."
        ),
        output_pydantic=EditingPlanOutput,
    )
