"""Suite pytest para o gate de onboarding travado (P1 do BACKLOG).

Cobre `GET /users/me/onboarding` (`src/viraxis/api/routers/users.py`):
  - progresso derivado corretamente para cada combinacao dos 3 marcos
    (upload -> decisao do BRAIN -> video pronto);
  - `current_step` calculado certo em cada estagio (1..4);
  - persistencia do snapshot nos campos booleanos do User so quando o valor
    muda de fato (nao commita a toa);
  - `onboarding_completed_at` fixado permanentemente na primeira vez que os 3
    marcos sao atingidos, e o gate nunca reaparece mesmo que o pipeline
    subjacente "regrida" depois (ex.: usuario apaga o conteudo que originou a
    conclusao);
  - autenticacao exigida (401 sem token).

Estrategia de mock: a sessao de banco e um fake minimo que devolve os 3
resultados de `session.scalar(select(exists()...))` na ordem em que o
endpoint os dispara (upload -> decisao -> conteudo pronto) — mesmo padrao de
`_ItemsFakeSession` em `tests/test_pipeline.py`. Nao ha Postgres neste
ambiente (JSONB usado em RawVideo/ContentDecision/ContentItem nao compila em
SQLite), entao a query real do SQLAlchemy nao e exercitada aqui; o que se
testa e a logica de orquestracao do endpoint (o "cerebro" do gate), que e
onde mora o risco real de regressao.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.main import app
from viraxis.domain.models.user import User, UserPlan, UserRole


def _now():
    return datetime.now(timezone.utc)


def _user(**overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email="onboarding-qa@viraxis.dev",
        hashed_password="x",
        full_name="Onboarding QA",
        plan=UserPlan.free,
        is_active=True,
        is_verified=True,
        role=UserRole.user,
        notify_content_ready=True,
        has_uploaded_video=False,
        has_brain_decision=False,
        has_ready_content=False,
        onboarding_completed_at=None,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return User(**defaults)


class _OnboardingFakeSession:
    """Fila de resultados devolvidos por `session.scalar(...)`, na ordem
    upload -> decisao -> conteudo pronto (ver `_compute_onboarding_progress`).
    Registra `add`/`commit`/`refresh` para assertar se o endpoint persistiu.
    """

    def __init__(self, scalar_results: list[bool]):
        self._queue = list(scalar_results)
        self.added: list = []
        self.commit_count = 0
        self.refresh_count = 0

    async def scalar(self, *_a, **_k):
        return self._queue.pop(0) if self._queue else False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        self.refresh_count += 1


@pytest.fixture
def onboarding_client_factory():
    """Monta um TestClient com `get_current_user`/`get_session` sobrescritos.

    Uso: `client, user = onboarding_client_factory(user=..., scalar_results=[...])`.
    `scalar_results` e a fila (upload, decisao, pronto) que o fake devolve.
    """

    def _make(user: User, scalar_results: list[bool]):
        session = _OnboardingFakeSession(scalar_results)

        async def _override_user():
            return user

        async def _override_session():
            yield session

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_session] = _override_session
        return TestClient(app), session

    yield _make
    app.dependency_overrides.clear()


class TestOnboardingStatusProgress:
    """Cada combinacao dos 3 marcos deve produzir o `current_step` certo."""

    def test_no_progress_step_1_not_completed(self, onboarding_client_factory):
        user = _user()
        client, session = onboarding_client_factory(user, [False, False, False])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["has_uploaded_video"] is False
        assert body["has_brain_decision"] is False
        assert body["has_ready_content"] is False
        assert body["completed"] is False
        assert body["completed_at"] is None
        assert body["current_step"] == 1
        assert body["total_steps"] == 3

    def test_uploaded_only_step_2(self, onboarding_client_factory):
        user = _user()
        client, session = onboarding_client_factory(user, [True, False, False])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        body = r.json()
        assert body["has_uploaded_video"] is True
        assert body["has_brain_decision"] is False
        assert body["current_step"] == 2
        assert body["completed"] is False

    def test_uploaded_and_decision_step_3(self, onboarding_client_factory):
        user = _user()
        client, session = onboarding_client_factory(user, [True, True, False])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        body = r.json()
        assert body["has_uploaded_video"] is True
        assert body["has_brain_decision"] is True
        assert body["has_ready_content"] is False
        assert body["current_step"] == 3
        assert body["completed"] is False

    def test_all_three_marks_completed_step_4(self, onboarding_client_factory):
        user = _user()
        client, session = onboarding_client_factory(user, [True, True, True])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        body = r.json()
        assert body["has_uploaded_video"] is True
        assert body["has_brain_decision"] is True
        assert body["has_ready_content"] is True
        assert body["completed"] is True
        assert body["completed_at"] is not None
        assert body["current_step"] == 4


class TestOnboardingPersistence:
    """O endpoint persiste o snapshot no User e fixa `onboarding_completed_at`
    permanentemente — sem re-setar o commit quando nada mudou."""

    def test_first_time_all_three_persists_completed_at(self, onboarding_client_factory):
        user = _user()  # onboarding_completed_at ainda None
        client, session = onboarding_client_factory(user, [True, True, True])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        assert user.onboarding_completed_at is not None
        assert user in session.added
        assert session.commit_count == 1
        assert session.refresh_count == 1

    def test_no_change_skips_commit(self, onboarding_client_factory):
        # Usuario ja tem os 3 booleanos batendo com o pipeline e ja concluido
        # -> nada muda, o endpoint nao deve commitar a toa.
        completed_at = _now()
        user = _user(
            has_uploaded_video=True,
            has_brain_decision=True,
            has_ready_content=True,
            onboarding_completed_at=completed_at,
        )
        client, session = onboarding_client_factory(user, [True, True, True])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        assert session.commit_count == 0
        assert session.refresh_count == 0
        # `completed_at` inalterado (mesma instancia, nao regravado)
        assert user.onboarding_completed_at == completed_at

    def test_partial_progress_persists_boolean_snapshot(self, onboarding_client_factory):
        user = _user()
        client, session = onboarding_client_factory(user, [True, False, False])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        assert user.has_uploaded_video is True
        assert user.has_brain_decision is False
        assert user.onboarding_completed_at is None
        assert session.commit_count == 1


class TestOnboardingNeverReappears:
    """Uma vez `onboarding_completed_at` fixado, o gate fica destravado para
    sempre — mesmo que o usuario depois apague o video/decisao/conteudo que
    originou a conclusao (o pipeline "regride" para False)."""

    def test_completed_stays_completed_even_if_pipeline_regresses(
        self, onboarding_client_factory
    ):
        completed_at = _now()
        user = _user(
            has_uploaded_video=True,
            has_brain_decision=True,
            has_ready_content=True,
            onboarding_completed_at=completed_at,
        )
        # Usuario apagou o conteudo pronto -> query real agora devolveria False
        client, session = onboarding_client_factory(user, [True, True, False])

        r = client.get("/users/me/onboarding")

        assert r.status_code == 200
        body = r.json()
        # `completed` continua True porque `onboarding_completed_at` nunca e
        # limpo pelo endpoint (so setado, nunca resetado).
        assert body["completed"] is True
        assert body["current_step"] == 4
        assert user.onboarding_completed_at == completed_at


class TestOnboardingAuth:
    def test_requires_authentication(self):
        app.dependency_overrides.clear()
        client = TestClient(app)
        r = client.get("/users/me/onboarding")
        assert r.status_code in (401, 403)
