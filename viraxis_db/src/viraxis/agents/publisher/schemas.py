"""Schemas para o agente PUBLISHER — PR-7 Fase 2."""

from typing import Literal

from pydantic import BaseModel, Field


class PublishTarget(BaseModel):
    """Uma plataforma alvo para publicacao."""

    platform: Literal["tiktok", "instagram", "youtube", "kwai"]
    social_account_id: str
    caption: str | None = None         # Legenda customizada por plataforma
    hashtags: list[str] = Field(default_factory=list)
    scheduled_at: str | None = None    # ISO8601 ou None = publicar agora


class PublisherInput(BaseModel):
    """Input do PUBLISHER: ContentItem + lista de plataformas alvo."""

    content_item_id: str
    office_id: str
    user_id: str
    title: str
    script: str
    storage_path: str | None = None    # R2 path do video renderizado
    targets: list[PublishTarget]


class PublishResult(BaseModel):
    """Resultado de uma publicacao em uma plataforma."""

    platform: str
    social_account_id: str
    success: bool
    external_id: str | None = None     # ID do post na plataforma
    url: str | None = None             # URL publica do post
    error_message: str | None = None


class PublisherOutput(BaseModel):
    """Output do PUBLISHER: resultado por plataforma."""

    schema_version: str = "1.0"
    results: list[PublishResult]
    successful_platforms: list[str]
    failed_platforms: list[str]
    caption_generated: str | None = None  # Legenda gerada pelo LLM se nao fornecida
