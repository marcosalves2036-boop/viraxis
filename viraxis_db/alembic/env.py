from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from viraxis.infrastructure.database.base import Base
import viraxis.domain.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _make_sync_url(raw: str) -> str:
    """Converte DATABASE_URL para driver síncrono psycopg2 + SSL."""
    url = raw.strip()
    # Normalizar protocolo
    url = url.replace("postgres://", "postgresql://")
    # Trocar driver para psycopg2
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    # Garantir prefixo correto
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    # Adicionar sslmode=require se não tiver (Supabase exige SSL)
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def run_migrations_offline() -> None:
    raw = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    url = _make_sync_url(raw) if os.environ.get("DATABASE_URL") else raw
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    raw = os.environ.get("DATABASE_URL")
    if raw:
        config.set_main_option("sqlalchemy.url", _make_sync_url(raw))

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
