from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from viraxis.infrastructure.database.base import Base
import viraxis.domain.models  # noqa: F401 — registra todos os models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Ler DATABASE_URL do ambiente (Render/produção) ────────────────────────────
# Alembic usa driver síncrono (psycopg2); converte asyncpg → psycopg2 se necessário
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    _db_url = (
        _db_url
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgres://", "postgresql+psycopg2://")
    )
    config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
