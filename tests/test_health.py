"""Suite pytest para GET /health (P1 do BACKLOG).

Contexto: antes desta mudança /health devolvia {"status": "ok"} estático,
sem nenhuma checagem real de dependência — o keep-alive (roda a cada 10min)
tratava qualquer HTTP 200 como "serviço vivo". Isso já causou um incidente
real: o projeto Supabase ficou INACTIVE (pausado por inatividade) e passou
despercebido por um ciclo inteiro porque /health continuava respondendo 200.

Esta suite prova que:
  - quando Neon (Postgres) e Supabase Storage respondem OK, /health devolve
    200 com status="ok";
  - quando qualquer uma das duas falha, /health devolve 503 com
    status="degraded" e o detalhe de qual dependência falhou — não mais um
    200 estático mascarando o problema.

Mock nas BORDAS: `_check_database` e `_check_storage` (funções que fazem a
chamada de rede real via asyncpg/httpx) são substituídas — não precisamos de
Postgres/Supabase reais neste ambiente de teste. A lógica de decisão do
endpoint (combinar os dois resultados, escolher status_code, montar o corpo)
roda de verdade e pode genuinamente falhar se regredir.
"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-para-suite-de-health-nao-usar-em-prod")
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("RESEND_API_KEY", "")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from viraxis.api import main as main_module
from viraxis.api.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_200_ok_when_database_and_storage_are_healthy(
        self, client, monkeypatch
    ):
        async def _db_ok():
            return {"ok": True}

        async def _storage_ok():
            return {"ok": True}

        monkeypatch.setattr(main_module, "_check_database", _db_ok)
        monkeypatch.setattr(main_module, "_check_storage", _storage_ok)

        resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["database"]["ok"] is True
        assert body["checks"]["storage"]["ok"] is True
        assert body["service"] == "viraxis-api"

    async def test_health_returns_503_degraded_when_database_is_down(self, client, monkeypatch):
        async def _db_fail():
            return {"ok": False, "detail": "TimeoutError: conexão recusada pelo Neon"}

        async def _storage_ok():
            return {"ok": True}

        monkeypatch.setattr(main_module, "_check_database", _db_fail)
        monkeypatch.setattr(main_module, "_check_storage", _storage_ok)

        resp = await client.get("/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["database"]["ok"] is False
        assert "Neon" in body["checks"]["database"]["detail"]
        # Storage estava saudável — não deve ser reportado como falho.
        assert body["checks"]["storage"]["ok"] is True

    async def test_health_returns_503_degraded_when_storage_is_down(self, client, monkeypatch):
        async def _db_ok():
            return {"ok": True}

        async def _storage_fail():
            return {"ok": False, "detail": "HTTP 000: falha de DNS (projeto Supabase pausado/INACTIVE)"}

        monkeypatch.setattr(main_module, "_check_database", _db_ok)
        monkeypatch.setattr(main_module, "_check_storage", _storage_fail)

        resp = await client.get("/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["storage"]["ok"] is False
        assert "INACTIVE" in body["checks"]["storage"]["detail"]
        assert body["checks"]["database"]["ok"] is True

    async def test_health_returns_503_when_both_dependencies_are_down(self, client, monkeypatch):
        async def _db_fail():
            return {"ok": False, "detail": "connection refused"}

        async def _storage_fail():
            return {"ok": False, "detail": "connection refused"}

        monkeypatch.setattr(main_module, "_check_database", _db_fail)
        monkeypatch.setattr(main_module, "_check_storage", _storage_fail)

        resp = await client.get("/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["database"]["ok"] is False
        assert body["checks"]["storage"]["ok"] is False

    async def test_health_does_not_require_authentication(self, client, monkeypatch):
        """/health precisa ser acessível sem token — é usado pelo keep-alive
        (GitHub Actions, sem credenciais de usuário) e por health checks de
        infraestrutura (Render)."""

        async def _ok():
            return {"ok": True}

        monkeypatch.setattr(main_module, "_check_database", _ok)
        monkeypatch.setattr(main_module, "_check_storage", _ok)

        resp = await client.get("/health")
        assert resp.status_code in (200, 503)  # nunca 401/403


class TestCheckDatabaseAndStorageUnit:
    """Testes unitários das funções de checagem em si (sem rede real) —
    garantem que elas retornam {"ok": False, ...} quando não configuradas,
    em vez de estourar exceção não tratada (o endpoint depende disso)."""

    async def test_check_database_returns_not_ok_when_database_url_missing(self, monkeypatch):
        from viraxis.config import settings

        monkeypatch.setattr(settings, "database_url", "")
        result = await main_module._check_database()
        assert result["ok"] is False
        assert "DATABASE_URL" in result["detail"]

    async def test_check_storage_returns_not_ok_when_supabase_not_configured(self, monkeypatch):
        from viraxis.config import settings

        monkeypatch.setattr(settings, "supabase_url", "")
        monkeypatch.setattr(settings, "supabase_service_role_key", "")
        result = await main_module._check_storage()
        assert result["ok"] is False
        assert "SUPABASE" in result["detail"]

    async def test_check_database_handles_connection_error_gracefully(self, monkeypatch):
        """Se asyncpg.connect levantar qualquer exceção (host errado, timeout,
        credencial inválida), a função deve devolver {"ok": False}, não
        propagar — senão o endpoint /health inteiro quebraria com 500 em vez
        de reportar 503 degraded, que é o objetivo desta task."""
        from viraxis.config import settings

        monkeypatch.setattr(
            settings, "database_url", "postgresql://user:pass@host-invalido-qa:5432/db"
        )

        import asyncpg

        async def _raise_connect(*_a, **_kw):
            raise OSError("[Errno -2] Name or service not known")

        monkeypatch.setattr(asyncpg, "connect", _raise_connect)

        result = await main_module._check_database()
        assert result["ok"] is False
        assert "OSError" in result["detail"] or "not known" in result["detail"]

    async def test_check_storage_handles_http_error_gracefully(self, monkeypatch):
        from viraxis.config import settings

        monkeypatch.setattr(settings, "supabase_url", "https://fake-inactive.qa")
        monkeypatch.setattr(settings, "supabase_service_role_key", "fake-key")

        import httpx

        class _FailingClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, *_a, **_kw):
                raise httpx.ConnectError("DNS NXDOMAIN — projeto pausado")

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FailingClient())

        result = await main_module._check_storage()
        assert result["ok"] is False
        assert "ConnectError" in result["detail"] or "NXDOMAIN" in result["detail"]
