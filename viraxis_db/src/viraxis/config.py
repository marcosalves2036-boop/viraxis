"""Configurações centrais da aplicação via pydantic-settings + .env."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Aplicação                                                           #
    # ------------------------------------------------------------------ #
    environment: str = "development"
    debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ------------------------------------------------------------------ #
    # Banco de dados                                                      #
    # ------------------------------------------------------------------ #
    # Opção A — URL completa (Render, Heroku, Supabase): tem prioridade
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    # Opção B — vars individuais (Docker local / Codespaces)
    postgres_user: str = "viraxis"
    postgres_password: str = "viraxis_dev"
    postgres_db: str = "viraxis"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @computed_field  # type: ignore[misc]
    @property
    def database_url_async(self) -> str:
        """URL asyncpg para SQLAlchemy async."""
        if self.database_url:
            url = self.database_url
            url = url.replace("postgres://", "postgresql://")
            url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            if not url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        u, p = self.postgres_user, self.postgres_password
        h, port, db = self.postgres_host, self.postgres_port, self.postgres_db
        return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/{db}"

    @computed_field  # type: ignore[misc]
    @property
    def database_url_sync(self) -> str:
        """URL psycopg2 para Alembic CLI."""
        if self.database_url:
            url = self.database_url
            url = url.replace("postgres://", "postgresql://")
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
            if not url.startswith("postgresql+psycopg2://"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url
        u, p = self.postgres_user, self.postgres_password
        h, port, db = self.postgres_host, self.postgres_port, self.postgres_db
        return f"postgresql+psycopg2://{u}:{p}@{h}:{port}/{db}"

    # ------------------------------------------------------------------ #
    # Redis / Celery                                                      #
    # ------------------------------------------------------------------ #
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ------------------------------------------------------------------ #
    # LLM providers                                                       #
    # ------------------------------------------------------------------ #
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = "groq/llama-3.3-70b-versatile"
    scout_llm_model: str = Field(default="groq/llama-3.3-70b-versatile", alias="SCOUT_LLM_MODEL")
    renderer_llm_model: str = Field(default="groq/llama-3.3-70b-versatile", alias="RENDERER_LLM_MODEL")
    scout_enable_transcription: bool = Field(default=False, alias="SCOUT_ENABLE_TRANSCRIPTION")

    # Campos legados
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    anthropic_api_key: str = ""

    # ------------------------------------------------------------------ #
    # Segurança                                                           #
    # ------------------------------------------------------------------ #
    secret_key: str = "troque-por-uma-string-aleatoria-de-64-chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 dias

    # ------------------------------------------------------------------ #
    # Stripe Billing                                                      #
    # ------------------------------------------------------------------ #
    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_pro: str = Field(default="", alias="STRIPE_PRICE_PRO")
    stripe_price_business: str = Field(default="", alias="STRIPE_PRICE_BUSINESS")

    # ------------------------------------------------------------------ #
    # Cloudflare R2                                                       #
    # ------------------------------------------------------------------ #
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "viraxis-media"
    r2_endpoint_url: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton — lido do .env uma única vez."""
    return Settings()


settings = get_settings()
