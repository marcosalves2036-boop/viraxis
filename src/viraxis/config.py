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
    postgres_user: str = "viraxis"
    postgres_password: str = "viraxis_dev"
    postgres_db: str = "viraxis"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @computed_field  # type: ignore[misc]
    @property
    def database_url_async(self) -> str:
        """URL para o driver asyncpg (SQLAlchemy async)."""
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
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    llm_provider: str = "gemini"
    llm_model: str = "gemini/gemini-2.5-pro"

    # Anthropic (ativar depois)
    anthropic_api_key: str = ""

    # ------------------------------------------------------------------ #
    # Segurança                                                           #
    # ------------------------------------------------------------------ #
    secret_key: str = "troque-por-uma-string-aleatoria-de-64-chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 dias

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
