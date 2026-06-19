"""Gerador de legenda otimizada por plataforma via LLM — PR-7 Fase 2.

Chamado pelo PUBLISHER quando o operador nao fornece caption customizada.
Usa LLM diretamente (sem CrewAI) para uma resposta mais simples e rapida.
"""

import logging
import os

logger = logging.getLogger(__name__)

_CAPTION_PROMPTS = {
    "tiktok": (
        "Escreva uma legenda para TikTok de no maximo 150 caracteres. "
        "Tom informal, 3-5 hashtags relevantes. "
        "Comece com um hook de 1 linha, termine com os hashtags."
    ),
    "instagram": (
        "Escreva uma legenda para Instagram Reels de 100-200 caracteres. "
        "Tom engajador, 5-8 hashtags relevantes no fim. "
        "Inclua uma pergunta para incentivar comentarios."
    ),
    "youtube": (
        "Escreva uma descricao para YouTube Shorts de 150-300 caracteres. "
        "Inclua palavras-chave para SEO, 2-3 hashtags. "
        "Termine com um CTA para se inscrever."
    ),
    "kwai": (
        "Escreva uma legenda para Kwai de no maximo 150 caracteres. "
        "Tom popular e direto, 3-5 hashtags. "
        "Linguagem acessivel para publico amplo."
    ),
}


def generate_caption_sync(
    platform: str,
    title: str,
    script_excerpt: str,
    niche: str,
) -> str:
    """Gera legenda otimizada para a plataforma via LLM.

    Chamado de forma sincrona — use via asyncio.to_thread se necessario.

    Args:
        platform: tiktok | instagram | youtube | kwai
        title: Titulo do video
        script_excerpt: Primeiros 200 chars do roteiro (hook)
        niche: Nome do nicho (ex: "financas pessoais")

    Returns:
        Legenda gerada. Em caso de erro retorna legenda fallback.
    """
    try:
        from crewai import LLM  # noqa: PLC0415

        model = os.getenv("RENDERER_LLM_MODEL", os.getenv("SCOUT_LLM_MODEL", "gpt-4o-mini"))
        llm = LLM(model=model, temperature=0.7)

        prompt_guide = _CAPTION_PROMPTS.get(
            platform,
            "Escreva uma legenda curta e engajadora de 100-200 caracteres com hashtags."
        )

        prompt = f"""
{prompt_guide}

Contexto:
- Nicho: {niche}
- Titulo do video: {title}
- Inicio do roteiro: {script_excerpt[:200]}

Retorne APENAS a legenda, sem explicacoes adicionais.
""".strip()

        response = llm.call([{"role": "user", "content": prompt}])
        caption = response.strip() if isinstance(response, str) else str(response).strip()
        logger.info("Caption gerada | platform=%s | len=%d", platform, len(caption))
        return caption

    except Exception as exc:
        logger.warning("Falha ao gerar caption via LLM: %s. Usando fallback.", exc)
        return f"{title} #viraxis #{niche.replace(' ', '').lower()}"
