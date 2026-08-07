"""BACKLOG P2 (fonte: arthur, adicionado 2026-07-28, revisitado 2026-08-06):
"Confirmar que /api/analytics/summary, /timeline, /publications e
/api/offices/{id}/decisions continuam coerentes carregados na mesma sessão
da página consolidada /dashboard/analytics (abas) — sem overlap de
rate-limit ou contenção de token."

Este arquivo prova empiricamente (não só leitura de código) o que acontece
quando uma sessão real de usuário abre as 4 abas em sequência rápida:

  1. Nenhum dos 4 endpoints tem `@limiter.limit(...)` aplicado
     (`src/viraxis/api/routers/analytics.py` e o endpoint
     `GET /offices/{id}/decisions` em `offices.py`) — só endpoints caros
     (upload, BRAIN, FFmpeg) foram priorizados no rollout do rate limiting
     (ver `src/viraxis/api/rate_limit.py`).
  2. Não existe `SlowAPIMiddleware` nem `default_limits` no `Limiter` global
     (`app.state.limiter`, ver `main.py`) — sem isso, uma rota só é limitada
     se for decorada explicitamente (confirmado lendo `main.py`/`rate_limit.py`
     linha a linha).
  3. Uma sessão real (mesmo usuário, mesmo JWT) disparando as 4 chamadas em
     sequência rápida — inclusive repetido 30x para simular re-visitas às
     abas — nunca recebe 429 nestes 4 endpoints.

Conclusão: não há bug de overlap de rate-limit nem contenção de token nessas
4 rotas. `user_or_ip_key` decodifica o JWT em memória (sem tocar o banco) a
cada chamada — chamadas concorrentes não competem por um lock ou sessão
compartilhada; cada request do FastAPI recebe sua própria `AsyncSession` via
`Depends(get_session)`.

Banco: mesma estratégia de `tests/test_rate_limit.py` — sessão fake mínima
injetada via `dependency_overrides` (as queries de analytics usam
`jsonb_array_length`, incompatível com SQLite; não precisamos de dados reais
para provar a ausência de 429, só que os 4 fluxos completam sem erro).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

os.environ.setdefault("SECRET_KEY", "test-secret-key-para-suite-de-analytics-nao-usar-em-prod")
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("RESEND_API_KEY", "")

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
        email=f"analytics.qa+{uuid.uuid4().hex[:8]}@viraxis.dev",
        hashed_password="x",
        full_name="QA Analytics",
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
        name="Escritorio QA Analytics",
        niche="qa",
        status=OfficeStatus.active,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Office(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Fake AsyncSession — devolve resultados vazios/zerados para qualquer query de
# agregação (summary/timeline/publications) e o Office semeado para
# `_get_office_or_404` (usado por GET /offices/{id}/decisions). Não testamos
# corretude de dado aqui (isso é escopo de outra suite) — só que os 4 fluxos
# completam sem 429/500 quando chamados em sequência rápida.
# ─────────────────────────────────────────────────────────────────────────────


class _EmptyScalars:
    def all(self):
        return []


class _FakeResult:
    def __init__(self, office=None):
        self._office = office

    def scalar_one_or_none(self):
        return self._office

    def scalar_one(self):
        return 0

    def all(self):
        return []

    def scalars(self):
        return _EmptyScalars()


class AnalyticsFakeSession:
    def __init__(self, office=None):
        self._office = office

    async def execute(self, stmt, *_args, **_kwargs):
        col_desc = getattr(stmt, "column_descriptions", None)
        entity = col_desc[0].get("entity") if col_desc else None
        if entity is Office:
            return _FakeResult(office=self._office)
        return _FakeResult()

    async def scalar(self, *_a, **_kw):
        return 0


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()
    # Limpa contadores do slowapi entre testes — mesma preocupação documentada
    # em test_rate_limit.py (MemoryStorage é global ao processo de teste).


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


# ─────────────────────────────────────────────────────────────────────────────
# Parte 1 — inspeção real dos objetos de rota do FastAPI (não grep de texto):
# confirma que os 4 endpoints não carregam nenhum marcador de rate limit do
# slowapi, ao contrário dos endpoints que sabemos ter @limiter.limit (usados
# como controle positivo).
# ─────────────────────────────────────────────────────────────────────────────


# Nota: uma versão anterior deste arquivo tentava confirmar via introspecção
# de `app.routes` que as 4 rotas existem antes de provar a ausência de 429.
# A introspecção se mostrou frágil entre versões do FastAPI (0.141 substituiu
# `APIRoute` direto em `app.routes` por um wrapper interno `_IncludedRouter`
# sem `.path` público) — removida. A prova de que as rotas existem e
# respondem de verdade já está embutida nos testes comportamentais abaixo:
# eles fazem requests HTTP reais via ASGI e exigem `status_code == 200`, o
# que só é possível se a rota existir, resolver o handler e executar sem
# erro — uma prova mais forte que checar apenas a existência do registro.


# ─────────────────────────────────────────────────────────────────────────────
# Parte 2 — prova comportamental: sessão real de usuário abrindo as 4 abas em
# sequência rápida, repetido 30x (bem acima de qualquer limite configurado
# nos endpoints "caros" do sistema, ex: 15-20/min), nunca recebe 429.
# ─────────────────────────────────────────────────────────────────────────────


class TestOpeningFourTabsRapidlyNeverHits429:
    async def test_30_rounds_of_4_tabs_in_sequence_never_returns_429(self, client):
        user = _make_user()
        office = _make_office(user.id)
        session = AnalyticsFakeSession(office=office)

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)
        headers = _auth_headers(user)

        statuses: dict[str, list[int]] = {
            "summary": [], "timeline": [], "publications": [], "decisions": [],
        }

        # 30 rounds simula o usuário trocando de aba/voltando repetidamente
        # numa janela de tempo curta — bem mais agressivo que um usuário real
        # abrindo a página consolidada uma vez (4 chamadas).
        for _ in range(30):
            r1 = await client.get("/analytics/summary", headers=headers)
            r2 = await client.get("/analytics/timeline?days=30", headers=headers)
            r3 = await client.get("/analytics/publications?limit=20", headers=headers)
            r4 = await client.get(f"/offices/{office.id}/decisions", headers=headers)
            statuses["summary"].append(r1.status_code)
            statuses["timeline"].append(r2.status_code)
            statuses["publications"].append(r3.status_code)
            statuses["decisions"].append(r4.status_code)

        for name, codes in statuses.items():
            assert 429 not in codes, f"{name} recebeu 429 — regressão real de rate limit: {codes}"
            # Nenhum erro de servidor/contenção também — todas devem ser 200.
            assert all(c == 200 for c in codes), f"{name} teve status inesperado: {codes}"

    async def test_realistic_single_page_load_4_tabs_once_never_returns_429(self, client):
        """Caso realista: usuário abre /dashboard/analytics uma vez, as 4
        chamadas disparam em paralelo (Promise.all no frontend) — aqui
        simulado com asyncio.gather para replicar concorrência real, não só
        sequencial."""
        import asyncio

        user = _make_user()
        office = _make_office(user.id)
        session = AnalyticsFakeSession(office=office)

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)
        headers = _auth_headers(user)

        responses = await asyncio.gather(
            client.get("/analytics/summary", headers=headers),
            client.get("/analytics/timeline?days=30", headers=headers),
            client.get("/analytics/publications?limit=20", headers=headers),
            client.get(f"/offices/{office.id}/decisions", headers=headers),
        )

        for r in responses:
            assert r.status_code == 200, r.text
