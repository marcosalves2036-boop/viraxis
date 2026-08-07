"""Regressão: UUID malformado deve retornar 422 (nunca 500).

Contexto (auditoria 2026-07, commit d1d4349 do DAVI): varios routers faziam
`UUID(str)` sem tratamento — qualquer cliente que mandasse um id malformado
("", "undefined", um numero, etc.) derrubava a request com um 500 generico
sem detalhe algum. O DAVI extraiu um helper unico `parse_uuid` em
`src/viraxis/api/utils.py` e aplicou em:
  - content_items.py (decision_id no body de POST .../content-items)
  - social_accounts.py (office_id em query/body de varios endpoints)
  - oauth.py (user_id/office_id extraidos do state JWT nos 4 callbacks:
    google, tiktok, instagram, meta)

Este arquivo valida esse comportamento com testes de HTTP reais (via
TestClient), sem banco real disponivel no ambiente de QA: os endpoints usam
um FakeSession (override de `get_session`) e monkeypatch pontual dos
metodos de repositorio que fariam I/O real, para isolar exclusivamente o
comportamento de validacao de UUID. Os testes de oauth.py adicionalmente
mockeiam `httpx.AsyncClient.get/post` para nao bater nas APIs reais do
Google/TikTok/Meta.

Regra de profundidade: cada teste faz uma assertion que pode genuinamente
falhar — nao ha `assert True`, stub vazio ou mock que nao verifica nada.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.main import app
from viraxis.api.routers.oauth import (
    GOOGLE_CHANNEL_URL,
    GOOGLE_TOKEN_URL,
    INSTAGRAM_GRAPH_BASE,
    META_IG_URL,
    META_ME_URL,
    META_TOKEN_URL,
    TIKTOK_TOKEN_URL,
    TIKTOK_USER_URL,
)
from viraxis.api.utils import parse_uuid
from viraxis.config import settings
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.office import Office, OfficeStatus
from viraxis.domain.models.social_account import SocialAccount, SocialPlatform
from viraxis.domain.models.user import User, UserPlan, UserRole
from viraxis.infrastructure.repositories.content_item import ContentItemRepository
from viraxis.infrastructure.repositories.social_account import SocialAccountRepository

MALFORMED_UUIDS = ["nao-e-um-uuid", "", "12345", "undefined", "null"]


# ─── Infra de teste: FakeSession / overrides ──────────────────────────────────
#
# Não há Postgres disponível neste ambiente de QA. Em vez de subir um banco
# real, isolamos exatamente o que os testes precisam verificar (o
# comportamento de `parse_uuid` nos routers) substituindo `get_session` por
# uma sessão fake cujo `.execute()` devolve resultados pré-configurados em
# fila (um por chamada, na ordem em que o endpoint as faz). Isso reflete
# fielmente o fluxo real do endpoint sem exigir infraestrutura de banco.


class _FakeScalars:
    def __init__(self, value):
        self._value = value

    def all(self):
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return self._value
        return [self._value]


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _FakeScalars(self._value)


class FakeSession:
    """Substitui AsyncSession para os testes de router. `results` é a fila de
    valores que cada chamada sucessiva a `.execute()` deve devolver (via
    `scalar_one_or_none`/`scalars().all()`), na ordem em que o endpoint sob
    teste executa suas queries."""

    def __init__(self, results: list | None = None):
        self._queue = list(results or [])
        self.added: list = []
        self.committed = False

    async def execute(self, *_args, **_kwargs):
        value = self._queue.pop(0) if self._queue else None
        return _FakeResult(value)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def _now():
    return datetime.now(timezone.utc)


def _make_office(user_id: uuid.UUID, id_: uuid.UUID | None = None) -> Office:
    return Office(
        id=id_ or uuid.uuid4(),
        user_id=user_id,
        name="Escritorio QA",
        niche="qa-niche",
        status=OfficeStatus.active,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_content_item(
    office_id: uuid.UUID,
    user_id: uuid.UUID,
    decision_id: uuid.UUID | None = None,
    id_: uuid.UUID | None = None,
) -> ContentItem:
    return ContentItem(
        id=id_ or uuid.uuid4(),
        office_id=office_id,
        user_id=user_id,
        decision_id=decision_id,
        title="Item QA",
        script="Roteiro de teste",
        status=ContentStatus.draft,
        duration_seconds=None,
        storage_path=None,
        thumbnail_path=None,
        production_meta={},
        publication_log=[],
        retention_layer={},
        deleted_at=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_social_account(
    user_id: uuid.UUID,
    id_: uuid.UUID | None = None,
    platform: SocialPlatform = SocialPlatform.tiktok,
    office_id: uuid.UUID | None = None,
) -> SocialAccount:
    return SocialAccount(
        id=id_ or uuid.uuid4(),
        user_id=user_id,
        office_id=office_id,
        platform=platform,
        platform_username="qa_platform_user",
        platform_user_id="qa-external-id",
        access_token_enc=None,
        refresh_token_enc=None,
        token_expires_at=None,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.fixture
def fake_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="qa@viraxis.dev",
        hashed_password="x",
        full_name="QA Tester",
        plan=UserPlan.free,
        is_active=True,
        is_verified=True,
        role=UserRole.user,
    )


@pytest.fixture
def client_factory(fake_user):
    """Devolve uma fábrica `make(fake_session=None) -> TestClient` com
    `get_current_user`/`get_session` sobrescritos. Overrides são limpos ao
    final do teste para não vazar entre casos."""

    def _make(fake_session: "FakeSession | None" = None) -> TestClient:
        session = fake_session if fake_session is not None else FakeSession()

        async def _override_user():
            return fake_user

        async def _override_session():
            yield session

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_session] = _override_session
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture
def mock_oauth_http(monkeypatch):
    """Substitui httpx.AsyncClient.get/post por handlers configuráveis por
    prefixo de URL — usado pelos testes de oauth.py para simular as respostas
    de Google/TikTok/Meta sem rede real."""
    handlers = {"get": {}, "post": {}}

    async def fake_get(_self, url, *_args, **_kwargs):
        for prefix, response in handlers["get"].items():
            if str(url).startswith(prefix):
                return response
        raise AssertionError(f"GET nao mockado neste teste: {url}")

    async def fake_post(_self, url, *_args, **_kwargs):
        for prefix, response in handlers["post"].items():
            if str(url).startswith(prefix):
                return response
        raise AssertionError(f"POST nao mockado neste teste: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return handlers


def _make_state(sub: str, office_id: str | None = None) -> str:
    """Constrói um state JWT válido (mesma forma de `oauth._create_state`)."""
    payload = {
        "sub": sub,
        "office_id": office_id,
        "nonce": "qa-nonce",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


# ─── Parte 1 — o helper `parse_uuid` isolado ──────────────────────────────────


class TestParseUuidHelper:
    def test_valid_uuid_string_returns_uuid_instance(self):
        valid = str(uuid.uuid4())
        result = parse_uuid(valid, "algum_campo")
        assert isinstance(result, uuid.UUID)
        assert str(result) == valid

    def test_uuid_instance_passthrough(self):
        u = uuid.uuid4()
        assert parse_uuid(u, "id") == u

    @pytest.mark.parametrize("bad_value", MALFORMED_UUIDS)
    def test_malformed_values_raise_422(self, bad_value):
        with pytest.raises(HTTPException) as exc_info:
            parse_uuid(bad_value, "office_id")
        assert exc_info.value.status_code == 422
        assert "office_id" in exc_info.value.detail

    def test_none_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_uuid(None, "decision_id")
        assert exc_info.value.status_code == 422

    def test_integer_value_raises_422_not_typeerror(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_uuid(12345, "account_id")
        assert exc_info.value.status_code == 422

    def test_field_name_appears_in_detail_for_debugging(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_uuid("xxx", "raw_video_id")
        assert "raw_video_id" in exc_info.value.detail


# ─── Parte 2 — content_items.py ───────────────────────────────────────────────


class TestContentItemsUuidValidation:
    def test_get_malformed_item_id_in_path_returns_422(self, client_factory):
        client = client_factory()
        resp = client.get(f"/offices/{uuid.uuid4()}/content-items/nao-e-um-uuid")
        assert resp.status_code == 422
        assert resp.status_code != 500

    def test_get_malformed_office_id_in_path_returns_422(self, client_factory):
        client = client_factory()
        resp = client.get(f"/offices/nao-e-um-uuid/content-items/{uuid.uuid4()}")
        assert resp.status_code == 422

    def test_get_valid_ids_office_not_found_returns_404_not_500(self, client_factory):
        client = client_factory(FakeSession(results=[None]))
        resp = client.get(f"/offices/{uuid.uuid4()}/content-items/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_get_valid_ids_item_not_found_returns_404_not_500(self, client_factory, fake_user):
        office = _make_office(user_id=fake_user.id)
        client = client_factory(FakeSession(results=[office, None]))
        resp = client.get(f"/offices/{office.id}/content-items/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_create_malformed_decision_id_in_body_returns_422(self, client_factory, fake_user):
        office = _make_office(user_id=fake_user.id)
        client = client_factory(FakeSession(results=[office]))
        resp = client.post(
            f"/offices/{office.id}/content-items",
            json={"title": "Titulo QA", "script": "Roteiro QA", "decision_id": "nao-e-um-uuid"},
        )
        assert resp.status_code == 422
        assert resp.status_code != 500
        assert "decision_id" in resp.json()["detail"]

    def test_create_empty_string_decision_id_treated_as_absent(
        self, client_factory, fake_user, monkeypatch
    ):
        """decision_id="" nao aciona parse_uuid: o endpoint usa `if
        body.decision_id:` antes de chamar o helper, entao string vazia e
        tratada como "nao informado" (igual None) — nao e um bug, mas o
        comportamento precisa ficar coberto por teste para nao regredir para
        um 500 caso a checagem `if body.decision_id` seja removida no futuro
        (nesse caso "" chegaria em parse_uuid e devolveria 422, o que
        tambem seria aceitavel — o que NUNCA pode acontecer e 500)."""
        office = _make_office(user_id=fake_user.id)
        fake_item = _make_content_item(office_id=office.id, user_id=fake_user.id, decision_id=None)

        async def _fake_create(_self, **_kwargs):
            return fake_item

        monkeypatch.setattr(ContentItemRepository, "create", _fake_create)

        client = client_factory(FakeSession(results=[office]))
        resp = client.post(
            f"/offices/{office.id}/content-items",
            json={"title": "Titulo QA", "script": "Roteiro QA", "decision_id": ""},
        )
        assert resp.status_code in (201, 422)
        assert resp.status_code != 500

    def test_create_valid_decision_id_completes_successfully(
        self, client_factory, fake_user, monkeypatch
    ):
        office = _make_office(user_id=fake_user.id)
        decision_id = uuid.uuid4()
        fake_item = _make_content_item(
            office_id=office.id, user_id=fake_user.id, decision_id=decision_id
        )

        async def _fake_create(_self, **_kwargs):
            return fake_item

        monkeypatch.setattr(ContentItemRepository, "create", _fake_create)

        client = client_factory(FakeSession(results=[office]))
        resp = client.post(
            f"/offices/{office.id}/content-items",
            json={
                "title": "Titulo QA",
                "script": "Roteiro QA",
                "decision_id": str(decision_id),
            },
        )
        assert resp.status_code == 201
        assert resp.json()["decision_id"] == str(decision_id)

    def test_create_without_decision_id_completes_successfully(
        self, client_factory, fake_user, monkeypatch
    ):
        """decision_id é opcional — omiti-lo não deve acionar parse_uuid."""
        office = _make_office(user_id=fake_user.id)
        fake_item = _make_content_item(office_id=office.id, user_id=fake_user.id, decision_id=None)

        async def _fake_create(_self, **_kwargs):
            return fake_item

        monkeypatch.setattr(ContentItemRepository, "create", _fake_create)

        client = client_factory(FakeSession(results=[office]))
        resp = client.post(
            f"/offices/{office.id}/content-items",
            json={"title": "Titulo QA", "script": "Roteiro QA"},
        )
        assert resp.status_code == 201
        assert resp.json()["decision_id"] is None

    def test_create_office_not_found_returns_404_not_500(self, client_factory):
        client = client_factory(FakeSession(results=[None]))
        resp = client.post(
            f"/offices/{uuid.uuid4()}/content-items",
            json={"title": "Titulo QA", "script": "Roteiro QA"},
        )
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_delete_malformed_item_id_returns_422(self, client_factory):
        client = client_factory()
        resp = client.delete(f"/offices/{uuid.uuid4()}/content-items/nao-e-um-uuid")
        assert resp.status_code == 422

    def test_patch_status_malformed_item_id_returns_422(self, client_factory):
        client = client_factory()
        resp = client.patch(
            f"/offices/{uuid.uuid4()}/content-items/nao-e-um-uuid/status",
            json={"status": "ready"},
        )
        assert resp.status_code == 422


# ─── Parte 3 — social_accounts.py ─────────────────────────────────────────────


class TestSocialAccountsUuidValidation:
    def test_list_malformed_office_id_query_returns_422(self, client_factory):
        client = client_factory()
        resp = client.get("/social-accounts", params={"office_id": "nao-e-um-uuid"})
        assert resp.status_code == 422
        assert resp.status_code != 500

    def test_list_empty_string_office_id_returns_422(self, client_factory):
        client = client_factory()
        resp = client.get("/social-accounts", params={"office_id": ""})
        # Query param vazio: FastAPI trata "" como valor presente (nao None),
        # entao cai no `if office_id:` -> parse_uuid("", ...) -> 422.
        # Se o frontend mandar office_id=&..., isso NAO pode virar 500.
        assert resp.status_code in (200, 422)
        assert resp.status_code != 500

    def test_list_valid_office_id_not_owned_returns_404_not_500(self, client_factory):
        client = client_factory(FakeSession(results=[None]))
        resp = client.get("/social-accounts", params={"office_id": str(uuid.uuid4())})
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_list_without_office_id_returns_200(self, client_factory):
        client = client_factory(FakeSession(results=[[]]))
        resp = client.get("/social-accounts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_malformed_office_id_in_body_returns_422(self, client_factory):
        client = client_factory(FakeSession(results=[None]))  # sem duplicata
        resp = client.post(
            "/social-accounts",
            json={
                "platform": "tiktok",
                "platform_username": "qa_user_1",
                "office_id": "nao-e-um-uuid",
            },
        )
        assert resp.status_code == 422
        assert resp.status_code != 500
        assert "office_id" in resp.json()["detail"]

    def test_create_valid_office_id_not_owned_returns_404_not_500(self, client_factory):
        client = client_factory(FakeSession(results=[None, None]))
        resp = client.post(
            "/social-accounts",
            json={
                "platform": "tiktok",
                "platform_username": "qa_user_2",
                "office_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_create_without_office_id_completes_successfully(self, client_factory):
        client = client_factory(FakeSession(results=[None]))
        resp = client.post(
            "/social-accounts",
            json={"platform": "tiktok", "platform_username": "qa_user_3"},
        )
        assert resp.status_code == 201
        assert resp.json()["office_id"] is None

    def test_get_malformed_account_id_returns_422(self, client_factory):
        client = client_factory()
        resp = client.get("/social-accounts/nao-e-um-uuid")
        assert resp.status_code == 422
        assert resp.status_code != 500

    def test_get_valid_account_id_not_found_returns_404_not_500(self, client_factory):
        client = client_factory(FakeSession(results=[None]))
        resp = client.get(f"/social-accounts/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_assign_malformed_account_id_in_path_returns_422(self, client_factory):
        client = client_factory()
        resp = client.patch(
            "/social-accounts/nao-e-um-uuid/assign",
            json={"office_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422

    def test_assign_malformed_office_id_in_body_returns_422(self, client_factory, fake_user):
        account = _make_social_account(user_id=fake_user.id)
        client = client_factory(FakeSession(results=[account]))
        resp = client.patch(
            f"/social-accounts/{account.id}/assign",
            json={"office_id": "nao-e-um-uuid"},
        )
        assert resp.status_code == 422
        assert resp.status_code != 500
        assert "office_id" in resp.json()["detail"]

    def test_assign_valid_office_id_not_owned_returns_404_not_500(self, client_factory, fake_user):
        account = _make_social_account(user_id=fake_user.id)
        client = client_factory(FakeSession(results=[account, None]))
        resp = client.patch(
            f"/social-accounts/{account.id}/assign",
            json={"office_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.status_code != 500

    def test_assign_null_office_id_unassigns_successfully(self, client_factory, fake_user):
        account = _make_social_account(user_id=fake_user.id)
        client = client_factory(FakeSession(results=[account]))
        resp = client.patch(
            f"/social-accounts/{account.id}/assign",
            json={"office_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["office_id"] is None

    def test_delete_malformed_account_id_returns_422(self, client_factory):
        client = client_factory()
        resp = client.delete("/social-accounts/nao-e-um-uuid")
        assert resp.status_code == 422
        assert resp.status_code != 500

    def test_delete_valid_account_id_not_found_returns_404_not_500(self, client_factory):
        client = client_factory(FakeSession(results=[None]))
        resp = client.delete(f"/social-accounts/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.status_code != 500


# ─── Parte 4 — oauth.py (4 fluxos: google, tiktok, instagram, meta) ──────────
#
# Correção aplicada em 2026-08-06 (KEVIN, P2 "fonte: qa"): a auditoria
# original encontrou uma inconsistência — `google_callback` NÃO tinha
# try/except ao redor do trecho que usa `parse_uuid`, então uma
# HTTPException(422) ali propagava direto como resposta HTTP real (422),
# enquanto `tiktok_callback`, `instagram_callback` e `meta_callback` já
# envolviam esse mesmo trecho num `except Exception` amplo que converte
# QUALQUER exceção (incluindo o 422 do parse_uuid) num redirect
# "status=error" para o frontend. Decisão registrada na docstring do módulo
# `oauth.py`: os 4 fluxos agora sempre redirecionam com "status=error" (nunca
# 500, nunca um 422/4xx bruto) — mais amigável para um endpoint cujo cliente
# real é o browser do usuário no meio de um redirect OAuth externo, não uma
# chamada de API tratada programaticamente pelo frontend. Os testes abaixo
# validam esse comportamento agora uniforme nos 4 fluxos.


class TestOauthCallbacksUuidValidation:
    def test_google_callback_malformed_sub_does_not_return_500(
        self, client_factory, mock_oauth_http
    ):
        mock_oauth_http["post"][GOOGLE_TOKEN_URL] = httpx.Response(
            200, json={"access_token": "fake-google-token", "expires_in": 3600}
        )
        mock_oauth_http["get"][GOOGLE_CHANNEL_URL] = httpx.Response(
            200, json={"items": [{"id": "chan1", "snippet": {"title": "Canal QA"}}]}
        )
        state = _make_state(sub="nao-e-um-uuid")
        client = client_factory()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        # google_callback agora segue o mesmo padrão dos outros 3 fluxos:
        # UUID malformado no state vira redirect "status=error", nunca um
        # 422 bruto nem um 500.
        assert resp.status_code in (302, 307)
        assert resp.status_code != 500
        assert resp.status_code != 422
        assert "status=error" in resp.headers["location"]

    def test_google_callback_valid_ids_redirects_success_not_500(
        self, client_factory, mock_oauth_http, monkeypatch
    ):
        mock_oauth_http["post"][GOOGLE_TOKEN_URL] = httpx.Response(
            200,
            json={
                "access_token": "fake-google-token",
                "refresh_token": "fake-refresh",
                "expires_in": 3600,
            },
        )
        mock_oauth_http["get"][GOOGLE_CHANNEL_URL] = httpx.Response(
            200, json={"items": [{"id": "chan1", "snippet": {"title": "Canal QA"}}]}
        )

        fake_account = _make_social_account(user_id=uuid.uuid4(), platform=SocialPlatform.youtube)

        async def _fake_existing(_self, _user_id, _platform, _username):
            return fake_account

        async def _fake_save(_self, account):
            return account

        monkeypatch.setattr(SocialAccountRepository, "get_by_user_platform_username", _fake_existing)
        monkeypatch.setattr(SocialAccountRepository, "save", _fake_save)

        state = _make_state(sub=str(uuid.uuid4()), office_id=str(uuid.uuid4()))
        client = client_factory()
        resp = client.get(
            "/auth/google/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert resp.status_code != 500
        assert "status=success" in resp.headers["location"]

    def test_tiktok_callback_malformed_sub_does_not_return_500(
        self, client_factory, mock_oauth_http
    ):
        mock_oauth_http["post"][TIKTOK_TOKEN_URL] = httpx.Response(
            200,
            json={
                "data": {
                    "access_token": "fake-tiktok-token",
                    "open_id": "oid1",
                    "expires_in": 86400,
                }
            },
        )
        mock_oauth_http["get"][TIKTOK_USER_URL] = httpx.Response(
            200, json={"data": {"user": {"display_name": "QA TikTok"}}}
        )
        state = _make_state(sub="nao-e-um-uuid")
        client = client_factory()
        resp = client.get(
            "/auth/tiktok/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        # tiktok_callback envolve o parse_uuid num except Exception amplo:
        # a HTTPException(422) é convertida num redirect de erro — nunca 500.
        assert resp.status_code in (302, 307)
        assert resp.status_code != 500
        assert "status=error" in resp.headers["location"]

    def test_meta_callback_malformed_sub_does_not_return_500(
        self, client_factory, mock_oauth_http
    ):
        mock_oauth_http["get"][META_TOKEN_URL] = httpx.Response(
            200, json={"access_token": "fake-meta-token", "expires_in": 5183944}
        )
        mock_oauth_http["get"][META_ME_URL] = httpx.Response(
            200, json={"id": "fbid1", "name": "QA Meta User"}
        )
        state = _make_state(sub="nao-e-um-uuid")
        client = client_factory()
        resp = client.get(
            "/auth/meta/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert resp.status_code != 500
        assert "status=error" in resp.headers["location"]

    def test_instagram_callback_malformed_sub_does_not_return_500(
        self, client_factory, mock_oauth_http
    ):
        mock_oauth_http["get"][META_TOKEN_URL] = httpx.Response(
            200, json={"access_token": "fake-ig-token", "expires_in": 5183944}
        )
        mock_oauth_http["get"][META_IG_URL] = httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "page1",
                        "name": "Page QA",
                        "access_token": "page-token",
                        "instagram_business_account": {"id": "igacct1"},
                    }
                ]
            },
        )
        mock_oauth_http["get"][f"{INSTAGRAM_GRAPH_BASE}/igacct1"] = httpx.Response(
            200, json={"id": "igacct1", "username": "qa_ig_user"}
        )
        state = _make_state(sub="nao-e-um-uuid")
        client = client_factory()
        resp = client.get(
            "/auth/instagram/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert resp.status_code != 500
        assert "status=error" in resp.headers["location"]
