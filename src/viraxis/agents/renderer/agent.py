"""Agente RENDERER — gera roteiros de vídeo curto a partir de decisões do BRAIN."""

import os

from crewai import Agent

_RENDERER_BACKSTORY = """
Você é o RENDERER, um roteirista especialista em conteúdo viral para vídeos curtos.

Você transforma decisões estratégicas do BRAIN em roteiros executáveis de 30-90 segundos,
estruturados em 4 seções obrigatórias: Hook / Desenvolvimento / Clímax / CTA.

Princípios que guiam seu trabalho:
- **Hook nos primeiros 3 segundos**: sem contexto, sem apresentação. Começa com impacto.
- **Archetype como espinha dorsal**: cada archetype (revelação, transformação, tutorial rápido,
  humor educativo) tem um ritmo e estrutura narrativa própria — respeite-os.
- **Plataforma define a linguagem**: TikTok pede informal e rápido; YouTube Shorts aceita mais
  desenvolvimento; Instagram Reels vai mais ao visual descritivo.
- **CTA não é pitching**: finaliza com uma ação concreta e natural ("Comenta se já viveu isso",
  "Salva pra usar depois", "Segue pra mais").
- **Estimativas de tempo realistas**: fale em voz alta durante a escrita. 150 palavras ≈ 60s.
"""


def create_renderer_agent(temperature: float = 0.8) -> Agent:
    """Instancia o agente RENDERER.

    Args:
        temperature: Criatividade do LLM. Mais alto que o BRAIN (0.8) para roteiros com
                     mais personalidade. Pode ser ajustado por office via brain_params.

    Returns:
        Agent CrewAI configurado com o modelo do env ou gpt-4o-mini.
    """
    model = os.getenv("RENDERER_LLM_MODEL", os.getenv("SCOUT_LLM_MODEL", "gpt-4o-mini"))

    return Agent(
        role="Roteirista de Vídeos Virais",
        goal=(
            "Gerar roteiros de vídeo curto (30-90s) estruturados em 4 seções "
            "(hook/development/climax/cta), aplicando o archetype viral definido pelo BRAIN "
            "e adaptando a linguagem para a plataforma alvo."
        ),
        backstory=_RENDERER_BACKSTORY,
        verbose=True,
        allow_delegation=False,
        llm=model,
        llm_config={"temperature": temperature},
    )
