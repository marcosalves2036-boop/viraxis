"""Configurações centrais da aplicação via pydantic-settings + .env."""

from functools import lru_cache

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
    # DATABASE_URL (full URL — Render/Neon/etc.)
    database_url: str = Field(default="", alias="DATABASE_URL")

    # Componentes individuais (fallback / dev local)
    postgres_user: str = "viraxis"
    postgres_password: str = "viraxis_dev"
    postgres_db: str = "viraxis"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @computed_field  # type: ignore[misc]
    @property
    def database_url_async(self) -> str:
        """URL para o driver asyncpg (SQLAlchemy async)."""
        if self.database_url:
            url = self.database_url
            # Converter para asyncpg (postgres:// ou postgresql://)
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            return url
        # Fallback: componentes individuais (dev local)
        u = self.postgres_user
        p = self.postgres_password
        h = self.postgres_host
        port = self.postgres_port
        db = self.postgres_db
        return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/{db}"

    @computed_field  # type: ignore[misc]
    @property
    def database_url_sync(self) -> str:
        """URL para o driver psycopg2 (Alembic CLI)."""
        if self.database_url:
            url = self.database_url
            if url.startswith("postgres://"):
                url = "postgresql+psycopg2://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg2://" + url[len("postgresql://"):]
            # Remover sslmode do sync URL (psycopg2 aceita connect_args)
            import re
            url = re.sub(r'[?&]sslmode=[^&]*', '', url)
            return url
        u = self.postgres_user
        p = self.postgres_password
        h = self.postgres_host
        port = self.postgres_port
        db = self.postgres_db
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
    # Chave generica — usada por qualquer provider configurado em llm_model.
    # Exemplos:
    #   Groq:     LLM_API_KEY=gsk_...   LLM_MODEL=groq/llama-3.3-70b-versatile
    #   Gemini:   LLM_API_KEY=AIzaSy... LLM_MODEL=gemini/gemini-2.5-pro
    #   OpenAI:   LLM_API_KEY=sk-...    LLM_MODEL=gpt-4o
    #   Anthropic:LLM_API_KEY=sk-ant-...LLM_MODEL=anthropic/claude-3-5-sonnet
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = "groq/llama-3.3-70b-versatile"

    # Campos legados — mantidos para compatibilidade retroativa
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
    # Price IDs do Stripe Dashboard
    stripe_price_pro: str = Field(default="", alias="STRIPE_PRICE_PRO")
    stripe_price_business: str = Field(default="", alias="STRIPE_PRICE_BUSINESS")
    # ------------------------------------------------------------------ #
    # Email — Resend                                                      #
    # ------------------------------------------------------------------ #
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    frontend_url: str = Field(default="https://viraxis.com.br", alias="FRONTEND_URL")

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


# Atalho conveniente para import direto
settings = get_settings()
