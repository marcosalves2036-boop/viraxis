"""Schemas Pydantic de entrada e saída do agente RENDERER."""

from typing import Literal

from pydantic import BaseModel, Field


class RendererInput(BaseModel):
    """Contexto que o RENDERER recebe para gerar o roteiro."""

    # Decisão do BRAIN
    decision_type: str
    selected_topic: str
    selected_archetype: str
    selected_platform: str
    hypothesis: str

    # Contexto do nicho
    niche_name: str
    content_style: dict
    target_audience: str | None = None

    # Tendências capturadas pelo SCOUT (opcional — enriquece o roteiro)
    trend_keywords: list[str] = Field(default_factory=list)
    trend_hook_pattern: str | None = None
    trend_summary: str | None = None


class ScriptSection(BaseModel):
    """Uma seção do roteiro de vídeo."""

    section: Literal["hook", "development", "climax", "cta"]
    content: str = Field(
        description="Texto completo da seção — como será falado no vídeo.",
        min_length=10,
    )
    duration_estimate_seconds: int = Field(
        description="Estimativa de duração em segundos para esta seção.",
        ge=1,
        le=120,
    )
    visual_notes: str | None = Field(
        default=None,
        description="Sugestões de cenas/texto na tela/transições para o editor.",
    )


class RendererOutput(BaseModel):
    """Roteiro estruturado gerado pelo RENDERER."""

    schema_version: str = "1.0"

    title: str = Field(
        description="Título do vídeo — otimizado para SEO e retenção.",
        max_length=512,
    )

    sections: list[ScriptSection] = Field(
        description="As 4 seções do roteiro: hook, development, climax, cta.",
        min_length=4,
        max_length=4,
    )

    full_script: str = Field(
        description=(
            "Roteiro completo contínuo, unindo as 4 seções. "
            "Pronto para ser lido pelo locutor/TTS."
        )
    )

    total_duration_estimate_seconds: int = Field(
        description="Soma das durações estimadas de todas as seções.",
        ge=10,
        le=300,
    )

    archetype_applied: str = Field(
        description="Archetype viral aplicado (deve coincidir com o da decisão)."
    )

    platform_adaptations: str = Field(
        description=(
            "Adaptações específicas feitas para a plataforma alvo "
            "(ex: linguagem TikTok, hashtags sugeridas para Instagram, etc)."
        )
    )

    confidence_score: float = Field(
        description="Confiança do RENDERER na qualidade do roteiro, de 0.0 a 1.0.",
        ge=0.0,
        le=1.0,
    )
