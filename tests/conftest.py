"""Fixtures compartilhadas para a suite de testes de autenticacao (P1).

Banco de teste: SQLite em memoria via aiosqlite, isolado por teste — NUNCA
toca o Postgres/Neon de producao. So a tabela `users` e criada (via
Base.metadata.create_all(tables=[User.__table__])), porque outras tabelas do
projeto usam tipos especificos de Postgres (JSONB) que o dialeto SQLite nao
sabe compilar — nao precisamos delas para testar os endpoints de auth.

O dependency override troca `viraxis.api.deps.get_session` (usado pelos
routers de auth e de users) por uma sessao ligada ao engine de teste.
"""

import os

# As variaveis de ambiente precisam existir ANTES do modulo viraxis.config
# ser importado pela primeira vez em qualquer lugar do processo — Settings e
# um singleton lido uma unica vez via lru_cache (veja viraxis/config.py).
os.environ.setdefault("SECRET_KEY", "test-secret-key-para-suite-de-auth-nao-usar-em-prod")
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("RESEND_API_KEY", "")  # sem chave -> infra.email._send() so loga, nao bate na Resend real

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from viraxis.api.deps import get_session
from viraxis.api.main import app
from viraxis.domain.models.user import User
from viraxis.infrastructure.database.base import Base


@pytest_asyncio.fixture
async def db_session_factory():
    """Engine SQLite em memoria exclusivo do teste, so com a tabela `users`."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session_factory):
    """AsyncClient contra a app real, com get_session apontando pro banco de teste."""

    async def _override_get_session():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
