"""Suite pytest para rate limiting por `user_id` (P1 do BACKLOG — "Hardening
de produção", "nenhum endpoint tem limite hoje").

Prova real de 429: chama um endpoint decorado com `@limiter.limit(...)`
(`POST /raw-videos/upload-url`, um dos 4 endpoints priorizados no BACKLOG)
mais vezes do que o limite configurado permite dentro da mesma janela, e
confirma que a resposta excedente é um 429 real — não um `assert True`.

Também prova a característica central do pedido ("por user_id, não por
IP" — sistema multi-tenant): dois usuários diferentes batendo no MESMO
endpoint, ao mesmo tempo, têm contadores independentes — o segundo usuário
não é penalizado pelo volume do primeiro.

Banco: mesma estratégia de `tests/test_raw_videos_reanalyze.py` —
`RawVideo`/`Office` usam colunas incompatíveis com SQLite, então usamos uma
`FakeAsyncSession` mínima injetada via `dependency_overrides`, com
`get_current_user` também sobrescrito. Mocks só na borda: `_supabase_configured`
e o cliente HTTP usado para assinar a upload URL — a lógica real do
endpoint (parse, autorização, geração do storage_path) roda de verdade.

IMPORTANTE sobre estado global: o `Limiter` do slowapi usa armazenamento em
memória (`MemoryStorage`) compartilhado por todo o processo de teste — a
chave é `user:<user_id>`, então cada teste usa usuários com UUID aleatório
novo (via `_make_user()`) para não herdar contagem de testes anteriores.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

os.environ.setdefault("SECRET_KEY", "test-secret-key-para-suite-de-rate-limit-nao-usar-em-prod")
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("RESEND_API_KEY", "")

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.main import app
from viraxis.api.security import create_access_token
from viraxis.domain.models.office import Office, OfficeStatus
from viraxis.domain.models.user import User, UserPlan, UserRole


def _now():
    return datetime.now(timezone.utc)


def _make_user(**overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email=f"ratelimit.qa+{uuid.uuid4().hex[:8]}@viraxis.dev",
        hashed_password="x",
        full_name="QA Rate Limit",
        plan=UserPlan.free,
        is_active=True,
        is_verified=True,
        notify_content_ready=True,
        role=UserRole.user,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_office(user_id, **overrides) -> Office:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Escritorio QA Rate Limit",
        niche="qa",
        status=OfficeStatus.active,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Office(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Fake AsyncSession — mesma estratégia de test_raw_videos_reanalyze.py
# ─────────────────────────────────────────────────────────────────────────────


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAsyncSession:
    def __init__(self):
        self.store: dict[type, object] = {}
        self.commits = 0

    def seed(self, obj):
        self.store[type(obj)] = obj
        return obj

    def add(self, obj):
        self.store[type(obj)] = obj

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def get(self, model, _id):
        return self.store.get(model)

    async def execute(self, stmt, *_args, **_kwargs):
        col_desc = getattr(stmt, "column_descriptions", None)
        if not col_desc:
            return _FakeExecResult(None)
        entity = col_desc[0].get("entity")
        return _FakeExecResult(self.store.get(entity))


class _FakeSignResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"url": "/storage/v1/object/upload/sign/biblioteca-videos/fake/rate-limit-test.mp4"}


class _FakeHttpxAsyncClient:
    """Substitui httpx.AsyncClient nas chamadas de `create_upload_url` — sempre
    devolve uma assinatura de upload bem-sucedida, sem bater no Supabase real."""

    def __init__(self, *_a, **_kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, *_a, **_kw):
        return _FakeSignResponse()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _auth_headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _override_user(user: User):
    async def _get_current_user_override():
        return user

    app.dependency_overrides[get_current_user] = _get_current_user_override


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _call_upload_url(client, user, office, monkeypatch, fake_session=None):
    session = fake_session if fake_session is not None else FakeAsyncSession()
    session.seed(office)

    async def _override_get_session():
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    _override_user(user)
    monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: True)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeHttpxAsyncClient)

    return await client.post(
        "/raw-videos/upload-url",
        json={"office_id": str(office.id), "filename": "video.mp4", "mime_type": "video/mp4"},
        headers=_auth_headers(user),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /raw-videos/upload-url — @limiter.limit("15/minute")
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimitUploadUrl:
    async def test_exceeding_limit_returns_429_with_retry_after(self, client, monkeypatch):
        """Bate no endpoint 16x rapidamente (limite = 15/minute) com o MESMO
        usuário e confirma que a 16ª leva 429 real, com corpo estruturado e
        header Retry-After — não um teste que sempre passa."""
        user = _make_user()
        office = _make_office(user.id)

        statuses = []
        last_response = None
        for _ in range(16):
            resp = await _call_upload_url(client, user, office, monkeypatch)
            statuses.append(resp.status_code)
            last_response = resp

        # As primeiras 15 chamadas devem ter sido aceitas (201) — prova que o
        # limite não está bloqueando tráfego legítimo dentro da cota.
        assert statuses[:15] == [201] * 15, statuses

        # A 16ª estoura o limite.
        assert statuses[15] == 429, statuses
        assert last_response.status_code == 429

        body = last_response.json()
        assert body["type"] == "RateLimitExceeded"
        assert "detail" in body
        assert "retry_after_seconds" in body
        assert isinstance(body["retry_after_seconds"], int)
        assert body["retry_after_seconds"] > 0

        # Header Retry-After real (RFC 7231) — é o que o BACKLOG pediu
        # explicitamente ("429 com Retry-After").
        assert "retry-after" in last_response.headers
        assert int(last_response.headers["retry-after"]) > 0

    async def test_rate_limit_is_per_user_not_global(self, client, monkeypatch):
        """Característica central do pedido: multi-tenant, limite por
        user_id — não por IP. Um usuário estourando o limite não deve
        afetar outro usuário completamente diferente batendo no mesmo
        endpoint logo em seguida (mesmo "IP" de teste para os dois)."""
        exhausted_user = _make_user()
        exhausted_office = _make_office(exhausted_user.id)

        # Esgota o limite do primeiro usuário.
        last_resp = None
        for _ in range(16):
            last_resp = await _call_upload_url(client, exhausted_user, exhausted_office, monkeypatch)
        assert last_resp.status_code == 429, "pré-condição do teste: usuário 1 precisa estar bloqueado"

        # Usuário 2, recém-criado, nunca bateu no endpoint — deve passar
        # normalmente mesmo vindo do mesmo cliente de teste (mesmo "IP").
        other_user = _make_user()
        other_office = _make_office(other_user.id)
        resp = await _call_upload_url(client, other_user, other_office, monkeypatch)

        assert resp.status_code == 201, (
            "usuário 2 foi bloqueado pelo limite do usuário 1 — "
            "rate limit está por IP/global, não por user_id"
        )

    async def test_within_limit_never_returns_429(self, client, monkeypatch):
        """Uso normal (bem abaixo do limite) nunca deve ser afetado."""
        user = _make_user()
        office = _make_office(user.id)

        for _ in range(5):
            resp = await _call_upload_url(client, user, office, monkeypatch)
            assert resp.status_code == 201, resp.text
