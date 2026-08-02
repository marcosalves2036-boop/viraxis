"""Suite pytest para POST /raw-videos/{id}/reanalyze (P1 do BACKLOG).

Contexto do endpoint: re-dispara a análise de IA de um RawVideo com
status=failed sem exigir novo upload (reusa o arquivo já no Supabase
Storage). É bloqueante para a task do Arthur de "Retry na UI".

Banco: RawVideo usa colunas JSONB (tags, ai_analysis), incompatíveis com o
dialeto SQLite usado em test_auth.py/conftest.py — mesma limitação já
documentada em test_pipeline.py. Usamos aqui a mesma estratégia: uma sessão
async fake mínima (FakeAsyncSession) injetada via dependency_override de
`get_session`, guardando um objeto por tipo (suficiente porque cada teste
tem no máximo um RawVideo relevante em jogo). `get_current_user` também é
sobrescrito para devolver um User já construído em memória, sem bater no
banco real (JWT/hash não são o que este teste cobre — já cobertos em
test_auth.py).

Mocks nas BORDAS apenas: `_supabase_configured`, `_signed_url` e
`analyze_uploaded_video` (chamada real dispararia download real de vídeo +
Gemini + Whisper). A lógica de autorização, validação de status e a
orquestração do endpoint em si rodam de verdade.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

os.environ.setdefault("SECRET_KEY", "test-secret-key-para-suite-de-reanalyze-nao-usar-em-prod")
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("RESEND_API_KEY", "")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.main import app
from viraxis.api.security import create_access_token
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.domain.models.user import User, UserPlan, UserRole


def _now():
    return datetime.now(timezone.utc)


def _make_user(**overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email="reanalyze.qa@viraxis.dev",
        hashed_password="x",
        full_name="QA Reanalyze",
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


def _make_raw_video(office_id, user_id, **overrides) -> RawVideo:
    defaults = dict(
        id=uuid.uuid4(),
        office_id=office_id,
        user_id=user_id,
        original_filename="bruto.mp4",
        r2_key=f"{user_id}/{office_id}/bruto.mp4",
        r2_url="https://fake-supabase.qa/signed/old-expired.mp4",
        file_size_bytes=1_000_000,
        duration_seconds=None,
        mime_type="video/mp4",
        status=RawVideoStatus.failed,
        title=None,
        description=None,
        tags=[],
        ai_analysis={"status": "failed", "error": "Tempo esgotado ao baixar o vídeo.", "error_type": "timeout"},
        error_type="timeout",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return RawVideo(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Fake AsyncSession — mesma estratégia de tests/test_pipeline.py
# ─────────────────────────────────────────────────────────────────────────────


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAsyncSession:
    """Guarda 1 objeto "atual" por tipo; resolve `select(Model)...`/`.get()`
    devolvendo-o. Suficiente porque cada teste tem no máximo 1 RawVideo em jogo."""

    def __init__(self):
        self.store: dict[type, object] = {}
        self.commits = 0
        self.refreshes = 0

    def seed(self, obj):
        self.store[type(obj)] = obj
        return obj

    def add(self, obj):
        self.store[type(obj)] = obj

    async def flush(self):
        return None

    async def refresh(self, obj):
        self.refreshes += 1

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


@pytest_asyncio.fixture
async def fake_session():
    return FakeAsyncSession()


@pytest_asyncio.fixture
async def client(fake_session):
    async def _override_get_session():
        yield fake_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()

    # (override registrado abaixo, por teste, para poder trocar o usuário)


def _auth_headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _override_user(user: User):
    async def _get_current_user_override():
        return user

    app.dependency_overrides[get_current_user] = _get_current_user_override


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# POST /raw-videos/{id}/reanalyze
# ─────────────────────────────────────────────────────────────────────────────


class TestReanalyzeEndpoint:
    async def test_reanalyze_failed_video_requeues_and_dispatches_background_analysis(
        self, client, fake_session, monkeypatch
    ):
        office_id = uuid.uuid4()
        user = _make_user()
        video = _make_raw_video(office_id, user.id, status=RawVideoStatus.failed, error_type="timeout")
        fake_session.seed(video)

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)

        monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: True)

        signed_url_mock = AsyncMock(return_value="https://fake-supabase.qa/signed/new-fresh-url.mp4")
        monkeypatch.setattr("viraxis.api.routers.raw_videos._signed_url", signed_url_mock)

        analyze_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("viraxis.api.routers.raw_videos.analyze_uploaded_video", analyze_mock)

        resp = await client.post(f"/raw-videos/{video.id}/reanalyze", headers=_auth_headers(user))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "processing"
        assert body["error_type"] is None
        assert body["r2_url"] == "https://fake-supabase.qa/signed/new-fresh-url.mp4"

        # Estado real do objeto no "banco" (fake) foi mutado corretamente.
        assert video.status == RawVideoStatus.processing
        assert video.error_type is None
        assert video.ai_analysis["status"] == "reanalyzing"
        assert video.ai_analysis["previous_failure"]["error_type"] == "timeout"
        assert fake_session.commits == 1

        # Reusa o MESMO fluxo assíncrono do upload original: BackgroundTask
        # chamando analyze_uploaded_video com o video_id e a signed URL nova.
        analyze_mock.assert_awaited_once_with(str(video.id), "https://fake-supabase.qa/signed/new-fresh-url.mp4")
        # Não gerou um novo arquivo no bucket — reusa o r2_key já existente.
        signed_url_mock.assert_awaited_once_with(video.r2_key)

    async def test_reanalyze_rejects_video_that_is_not_failed(self, client, fake_session, monkeypatch):
        office_id = uuid.uuid4()
        user = _make_user()
        video = _make_raw_video(office_id, user.id, status=RawVideoStatus.ready, error_type=None)
        fake_session.seed(video)

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)
        monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: True)
        analyze_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("viraxis.api.routers.raw_videos.analyze_uploaded_video", analyze_mock)

        resp = await client.post(f"/raw-videos/{video.id}/reanalyze", headers=_auth_headers(user))

        assert resp.status_code == 422, resp.text
        assert "failed" in resp.json()["detail"]
        # Nada foi disparado nem alterado — recusa acontece antes de qualquer mutação.
        analyze_mock.assert_not_awaited()
        assert video.status == RawVideoStatus.ready
        assert fake_session.commits == 0

    @pytest.mark.parametrize("bad_status", [RawVideoStatus.pending, RawVideoStatus.processing])
    async def test_reanalyze_rejects_pending_and_processing_status(
        self, client, fake_session, monkeypatch, bad_status
    ):
        office_id = uuid.uuid4()
        user = _make_user()
        video = _make_raw_video(office_id, user.id, status=bad_status, error_type=None)
        fake_session.seed(video)

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)
        monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: True)

        resp = await client.post(f"/raw-videos/{video.id}/reanalyze", headers=_auth_headers(user))
        assert resp.status_code == 422, resp.text

    async def test_reanalyze_returns_404_when_video_belongs_to_another_user(self, client, fake_session, monkeypatch):
        office_id = uuid.uuid4()
        owner = _make_user(email="owner@viraxis.dev")
        intruder = _make_user(email="intruder@viraxis.dev")
        video = _make_raw_video(office_id, owner.id, status=RawVideoStatus.failed)
        fake_session.seed(video)

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(intruder)
        monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: True)
        analyze_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("viraxis.api.routers.raw_videos.analyze_uploaded_video", analyze_mock)

        resp = await client.post(f"/raw-videos/{video.id}/reanalyze", headers=_auth_headers(intruder))

        assert resp.status_code == 404, resp.text
        analyze_mock.assert_not_awaited()
        # O vídeo do dono real não foi tocado por causa de uma requisição de outro usuário.
        assert video.status == RawVideoStatus.failed

    async def test_reanalyze_returns_404_when_video_does_not_exist(self, client, fake_session, monkeypatch):
        user = _make_user()

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)

        resp = await client.post(f"/raw-videos/{uuid.uuid4()}/reanalyze", headers=_auth_headers(user))
        assert resp.status_code == 404, resp.text

    async def test_reanalyze_returns_503_when_storage_not_configured(self, client, fake_session, monkeypatch):
        office_id = uuid.uuid4()
        user = _make_user()
        video = _make_raw_video(office_id, user.id, status=RawVideoStatus.failed)
        fake_session.seed(video)

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)
        monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: False)

        resp = await client.post(f"/raw-videos/{video.id}/reanalyze", headers=_auth_headers(user))

        assert resp.status_code == 503, resp.text
        # Recusa antes de mutar o status — não fica preso em "processing" sem
        # jamais ser reprocessado.
        assert video.status == RawVideoStatus.failed

    async def test_reanalyze_returns_502_when_signed_url_generation_fails(self, client, fake_session, monkeypatch):
        office_id = uuid.uuid4()
        user = _make_user()
        video = _make_raw_video(office_id, user.id, status=RawVideoStatus.failed)
        fake_session.seed(video)

        async def _override_get_session():
            yield fake_session

        app.dependency_overrides[get_session] = _override_get_session
        _override_user(user)
        monkeypatch.setattr("viraxis.api.routers.raw_videos._supabase_configured", lambda: True)
        monkeypatch.setattr(
            "viraxis.api.routers.raw_videos._signed_url", AsyncMock(return_value=None)
        )

        resp = await client.post(f"/raw-videos/{video.id}/reanalyze", headers=_auth_headers(user))

        assert resp.status_code == 502, resp.text
        assert video.status == RawVideoStatus.failed
        assert fake_session.commits == 0

    async def test_reanalyze_requires_authentication(self, client, fake_session):
        resp = await client.post(f"/raw-videos/{uuid.uuid4()}/reanalyze")
        assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
# upload_analyzer: error_type estruturado por categoria de falha crítica
# ─────────────────────────────────────────────────────────────────────────────


class TestUploadAnalyzerErrorType:
    """Confirma que analyze_uploaded_video persiste raw_videos.error_type com
    a categoria certa (download_failed | timeout | analysis_failed), campo
    novo consumido pelo endpoint /reanalyze e por retry automático futuro."""

    @pytest_asyncio.fixture
    async def captured_update(self, monkeypatch):
        """Substitui AsyncSessionLocal por uma sessão fake que só captura os
        `values` do UPDATE em raw_videos.status='failed' — não bate no Postgres."""
        calls: list[dict] = []

        class _CapturingSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, stmt, *_a, **_kw):
                compiled_values = getattr(stmt, "_values", None)
                # SQLAlchemy Update construct expõe os values via .values() já
                # aplicados internamente; extraímos via compile em modo debug.
                try:
                    values = dict(stmt.compile().params)
                except Exception:
                    values = {}
                calls.append(values)
                return None

            async def commit(self):
                return None

        def _session_factory():
            return _CapturingSession()

        monkeypatch.setattr(
            "viraxis.infrastructure.upload_analyzer.AsyncSessionLocal", _session_factory
        )
        return calls

    async def test_http_status_error_persists_download_failed(self, captured_update, monkeypatch):
        import httpx as httpx_mod
        from viraxis.infrastructure import upload_analyzer

        class _FailingStream:
            async def __aenter__(self):
                request = httpx_mod.Request("GET", "https://fake.qa/video.mp4")
                response = httpx_mod.Response(404, request=request)
                raise httpx_mod.HTTPStatusError("not found", request=request, response=response)

            async def __aexit__(self, *exc):
                return False

        class _FailingClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def stream(self, *_a, **_kw):
                return _FailingStream()

        monkeypatch.setattr(upload_analyzer.httpx, "AsyncClient", lambda **kw: _FailingClient())

        video_id = str(uuid.uuid4())
        await upload_analyzer.analyze_uploaded_video(video_id, "https://fake.qa/video.mp4")

        # 2 UPDATEs acontecem no total: (1) marca status=processing no início,
        # (2) marca status=failed com error_type no branch de erro crítico.
        # É este 2º que importa para o campo novo.
        assert len(captured_update) == 2
        failure_call = next(c for c in captured_update if "error_type" in c)
        assert failure_call.get("error_type") == "download_failed"
        assert failure_call.get("status") == RawVideoStatus.failed

    async def test_timeout_persists_timeout_error_type(self, captured_update, monkeypatch):
        import httpx as httpx_mod
        from viraxis.infrastructure import upload_analyzer

        class _TimeoutClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def stream(self, *_a, **_kw):
                raise httpx_mod.TimeoutException("timed out")

        monkeypatch.setattr(upload_analyzer.httpx, "AsyncClient", lambda **kw: _TimeoutClient())

        video_id = str(uuid.uuid4())
        await upload_analyzer.analyze_uploaded_video(video_id, "https://fake.qa/video.mp4")

        assert len(captured_update) == 2
        failure_call = next(c for c in captured_update if "error_type" in c)
        assert failure_call.get("error_type") == "timeout"
        assert failure_call.get("status") == RawVideoStatus.failed

    async def test_unexpected_exception_persists_analysis_failed(self, captured_update, monkeypatch):
        from viraxis.infrastructure import upload_analyzer

        class _BrokenClient:
            async def __aenter__(self):
                raise RuntimeError("boom - falha inesperada de infra")

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(upload_analyzer.httpx, "AsyncClient", lambda **kw: _BrokenClient())

        video_id = str(uuid.uuid4())
        await upload_analyzer.analyze_uploaded_video(video_id, "https://fake.qa/video.mp4")

        assert len(captured_update) == 2
        failure_call = next(c for c in captured_update if "error_type" in c)
        assert failure_call.get("error_type") == "analysis_failed"
        assert failure_call.get("status") == RawVideoStatus.failed
