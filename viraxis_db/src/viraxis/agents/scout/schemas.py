"""Schemas Pydantic do SCOUT — PR-3 Fase 2."""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ScoutInput(BaseModel):
    """Input do SCOUT: URL do vídeo viral + contexto do escritório."""

    url: str = Field(..., description="URL do vídeo a analisar")
    office_id: str = Field(..., description="UUID do escritório que está analisando")

    # Contexto opcional para melhorar os sinais extraídos
    niche_name: str | None = None
    target_platforms: list[str] = []


class ScoutOutput(BaseModel):
    """Output validado do SCOUT — persiste em TrendSnapshot.processed_signals."""

    schema_version: str = Field(default="1.0", description="Versão do schema para retrocompatibilidade")

    # Sinais virais principais
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords de alta performance extraídas do vídeo",
        max_length=20,
    )
    archetype: str | None = Field(
        default=None,
        description="Archetype viral identificado: revelacao, transformacao, tutorial_rapido, humor_educativo, etc.",
        max_length=64,
    )
    hook_pattern: str | None = Field(
        default=None,
        description="Padrão de gancho identificado: pergunta_retorica, dado_chocante, historia_pessoal, etc.",
        max_length=128,
    )
    engagement_estimate: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Estimativa de potencial de engajamento",
    )

    # Metadados do vídeo original
    video_title: str | None = Field(default=None, max_length=512)
    video_description: str | None = Field(default=None, max_length=2000)
    platform_detected: str | None = Field(
        default=None,
        description="Plataforma detectada da URL: youtube, tiktok, twitch",
        max_length=32,
    )
    duration_seconds: float | None = None

    # Análise de estrutura
    hook_text: str | None = Field(
        default=None,
        description="Primeiros 3-5 segundos do roteiro — o gancho identificado",
        max_length=500,
    )
    summary: str | None = Field(
        default=None,
        description="Resumo do conteúdo em 2-3 frases",
        max_length=500,
    )

    # Flags de processo
    transcription_used: bool = Field(
        default=False,
        description="Se a transcrição Whisper foi usada (SCOUT_ENABLE_TRANSCRIPTION=true)",
    )
