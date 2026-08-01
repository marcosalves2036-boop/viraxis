"""Suite de testes do pipeline core (P1): BRAIN -> RENDERER -> scene_extractor ->
video_composer_v2 -> process-video.

A cobertura anterior (test_auth.py, test_uuid_validation.py) só tocava auth e
parsing de UUID — o caminho crítico do produto (decisão de conteúdo, geração
de roteiro, extração de cenas, composição de vídeo e o endpoint que dispara
tudo isso) não tinha nenhum teste.

Estratégia de mock — nas BORDAS, não na lógica:
  - LLM/CrewAI: `_run_crew_sync` (BRAIN) e `litellm.acompletion` (RENDERER)
    são substituídos por saídas canônicas. A lógica real de orquestração
    (mapeamento de campos, resolução de temperatura, modo com/sem referência,
    retry, formatação de script) roda de verdade.
  - Banco: não há Postgres disponível neste ambiente de QA (mesma limitação
    documentada em conftest.py — os models usam JSONB do dialeto Postgres,
    incompatível com SQLite). Os runners (`run_brain`, `run_renderer_v2`)
    abrem sessões via `AsyncSessionLocal()` diretamente (não injetável por
    FastAPI Depends), então usamos uma sessão fake mínima (`FakeAsyncSession`)
    que resolve `select(Model)...` devolvendo o objeto certo por tipo — os
    testes deste arquivo têm no máximo um objeto relevante por tipo em jogo,
    então isso é suficiente para exercitar o fluxo real sem reimplementar SQL.
  - FFmpeg/TTS/geração de imagem: `_run_ffmpeg`, `synthesize_pt`,
    `generate_scene_image`, `_probe_duration`, `upload_to_storage`,
    `sign_storage_path` são substituídos por stubs determinísticos — a lógica
    real de composição (cenas -> segmentos -> concat -> legendas -> upload,
    com fallback de imagem e de legenda) roda de verdade.

Regra de profundidade (mesma do resto da suite): nenhuma assertion vazia,
nenhum mock que não verifica nada — cada teste pode genuinamente falhar se o
código sob teste regredir.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

# As variáveis de ambiente precisam existir ANTES de qualquer import de
# viraxis.config (Settings é lido uma única vez via lru_cache). conftest.py já
# faz isso para a suíte de auth, mas definimos de novo aqui defensivamente
# caso este arquivo seja coletado/rodado isoladamente.
os.environ.setdefault("SECRET_KEY", "test-secret-key-para-suite-de-pipeline-nao-usar-em-prod")
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("RESEND_API_KEY", "")
os.environ.setdefault("LLM_API_KEY", "fake-llm-key-qa")
os.environ.setdefault("SUPABASE_URL", "https://fake-supabase.qa")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "fake-service-role-key")

import pytest
from fastapi.testclient import TestClient

from viraxis.agents.brain.schemas import BrainDecisionInput, BrainDecisionOutput, RawVideoContext
from viraxis.agents.renderer.schemas import EditingPlanOutput, RendererOutput
from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus, DecisionType
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.niche_profile import NicheProfile
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.domain.models.trend_snapshot import TrendSnapshot
from viraxis.infrastructure.scene_extractor import extract_scenes, split_scene_part


def _now():
    return datetime.now(timezone.utc)


# =====================================================================
# Infra de teste: sessão fake mínima para os runners BRAIN/RENDERER
# =====================================================================
#
# `run_brain` e `run_renderer_v2` abrem `AsyncSessionLocal()` diretamente
# (não são endpoints FastAPI com Depends injetável). Para testar a lógica
# real de orquestração sem Postgres, substituímos `AsyncSessionLocal` por
# uma fábrica que devolve esta sessão fake. Ela resolve qualquer
# `select(Model)...` devolvendo o(s) objeto(s) armazenados daquele tipo —
# suficiente porque cada teste tem no máximo um objeto relevante por tipo.


class _FakeScalars:
    def __init__(self, items):
        self._items = items or []

    def all(self):
        return list(self._items)


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        if self._value is None:
            raise LookupError("FakeAsyncSession: nenhum resultado para scalar_one().")
        return self._value

    def scalars(self):
        if self._value is None:
            return _FakeScalars([])
        if isinstance(self._value, list):
            return _FakeScalars(self._value)
        return _FakeScalars([self._value])


class FakeAsyncSession:
    """Sessão async fake: guarda 1 objeto "atual" por tipo e resolve
    `select(Model)...` devolvendo-o. `session.get(Model, id)` idem."""

    def __init__(self):
        self.store: dict[type, object] = {}
        self.added: list = []
        self.commits = 0

    def seed(self, obj):
        self.store[type(obj)] = obj
        return obj

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.store[type(obj)] = obj
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def get(self, model, _id):
        return self.store.get(model)

    async def execute(self, stmt, *_args, **_kwargs):
        col_desc = getattr(stmt, "column_descriptions", None)
        if not col_desc:
            # UPDATE/texto cru (ex: _update_progress) — não inspecionado pelos testes.
            return _FakeExecResult(None)
        entity = col_desc[0].get("entity")
        return _FakeExecResult(self.store.get(entity))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_niche_profile(**overrides) -> NicheProfile:
    defaults = dict(
        id=uuid.uuid4(),
        office_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        niche_name="Financas Pessoais para Jovens",
        target_platforms=["tiktok", "instagram"],
        viral_archetypes={"revelacao": 0.4, "transformacao": 0.3},
        content_style={"voice_style": "direto e descomplicado", "style": "educational"},
        top_keywords=["investimento", "dividas"],
        brain_params={"temperature": 0.55},
        raw_notes="Publico 18-30 anos.",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return NicheProfile(**defaults)


def _make_raw_video(office_id, **overrides) -> RawVideo:
    defaults = dict(
        id=uuid.uuid4(),
        office_id=office_id,
        user_id=uuid.uuid4(),
        original_filename="bruto.mp4",
        r2_key=f"{office_id}/bruto.mp4",
        r2_url="https://fake-supabase.qa/signed/bruto.mp4",
        file_size_bytes=1_000_000,
        duration_seconds=42.0,
        mime_type="video/mp4",
        status=RawVideoStatus.ready,
        title="Video Bruto de Referencia",
        description="Um video cru sobre financas.",
        tags=["financas"],
        ai_analysis=None,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return RawVideo(**defaults)


def _make_content_decision(office_id, user_id, **overrides) -> ContentDecision:
    defaults = dict(
        id=uuid.uuid4(),
        office_id=office_id,
        user_id=user_id,
        decision_type=DecisionType.content_topic,
        status=DecisionStatus.pending,
        hypothesis="Este conteudo vai performar porque o archetype revelacao domina o nicho.",
        reasoning={"sinais_identificados": ["a"], "alternativas_descartadas": ["b"], "justificativa_final": "c"},
        selected_archetype="revelacao",
        selected_topic="3 erros que te mantem endividado",
        selected_platform="tiktok",
        confidence_score=0.82,
        extra_instructions=None,
        raw_video_id=None,
        input_signals={},
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return ContentDecision(**defaults)


def _make_content_item(office_id, user_id, decision_id, **overrides) -> ContentItem:
    defaults = dict(
        id=uuid.uuid4(),
        office_id=office_id,
        user_id=user_id,
        decision_id=decision_id,
        title="Rascunho QA",
        script="Roteiro QA",
        status=ContentStatus.draft,
        storage_path=None,
        thumbnail_path=None,
        duration_seconds=None,
        production_meta={},
        publication_log=[],
        retention_layer={},
        deleted_at=None,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return ContentItem(**defaults)


# =====================================================================
# Parte 1 — BrainDecisionInput.to_context_string() (lógica pura)
# =====================================================================


class TestBrainDecisionInputContextString:
    """`to_context_string()` monta o prompt textual que o LLM recebe — os
    rótulos de temporada e a formatação de vídeos/keywords são lógica de
    produto real (calibra ousadia/criatividade do BRAIN), não boilerplate."""

    def _base_input(self, **overrides) -> BrainDecisionInput:
        defaults = dict(
            niche_name="Financas Pessoais",
            target_platforms=["tiktok"],
            viral_archetypes={"revelacao": 0.6},
            content_style={"tom": "direto"},
            top_keywords=["investimento"],
            brain_params={},
        )
        defaults.update(overrides)
        return BrainDecisionInput(**defaults)

    def test_alta_temporada_label_quando_media_multiplicador_maior_igual_1_2(self):
        inp = self._base_input(seasonal_multipliers=[1.3, 1.4, 1.2])
        ctx = inp.to_context_string()
        assert "ALTA TEMPORADA" in ctx
        assert "1.30x" in ctx

    def test_baixa_temporada_label_quando_media_multiplicador_menor_que_0_9(self):
        inp = self._base_input(seasonal_multipliers=[0.5, 0.6])
        ctx = inp.to_context_string()
        assert "BAIXA TEMPORADA" in ctx

    def test_temporada_normal_label_quando_media_entre_0_9_e_1_2(self):
        inp = self._base_input(seasonal_multipliers=[1.0, 0.95])
        ctx = inp.to_context_string()
        assert "Temporada normal" in ctx

    def test_sem_dados_sazonais_usa_texto_neutro(self):
        inp = self._base_input(seasonal_multipliers=[])
        ctx = inp.to_context_string()
        assert "nenhum dado sazonal disponível" in ctx

    def test_videos_brutos_disponiveis_aparecem_formatados(self):
        video = RawVideoContext(
            id="abcdef1234567890", title="Meu Video", duration_seconds=90.0,
            tags=["a", "b"], description="desc",
        )
        inp = self._base_input(available_raw_videos=[video])
        ctx = inp.to_context_string()
        assert "abcdef12" in ctx  # ID truncado em 8 chars
        assert "Meu Video" in ctx
        assert "90s" in ctx

    def test_sem_videos_disponiveis_mostra_mensagem_padrao(self):
        inp = self._base_input(available_raw_videos=[])
        ctx = inp.to_context_string()
        assert "nenhum vídeo bruto disponível ainda" in ctx

    def test_sem_archetypes_mostra_mensagem_padrao(self):
        inp = self._base_input(viral_archetypes={})
        ctx = inp.to_context_string()
        assert "nenhum mapeado ainda" in ctx


# =====================================================================
# Parte 2 — Validação de schemas (BrainDecisionOutput, RendererOutput,
# EditingPlanOutput) — lógica pura de contrato, sem I/O
# =====================================================================


class TestBrainDecisionOutputSchema:
    def _valid_kwargs(self, **overrides):
        defaults = dict(
            decision_type="content_topic",
            hypothesis="Este conteudo vai performar porque o archetype revelacao domina.",
            reasoning={"sinais_identificados": [], "alternativas_descartadas": [], "justificativa_final": ""},
            confidence_score=0.75,
        )
        defaults.update(overrides)
        return defaults

    def test_output_valido_e_aceito(self):
        out = BrainDecisionOutput(**self._valid_kwargs())
        assert out.confidence_score == 0.75

    def test_hipotese_curta_demais_e_rejeitada(self):
        with pytest.raises(Exception):
            BrainDecisionOutput(**self._valid_kwargs(hypothesis="curta demais"))

    def test_confidence_score_acima_de_1_e_rejeitado(self):
        with pytest.raises(Exception):
            BrainDecisionOutput(**self._valid_kwargs(confidence_score=1.5))

    def test_confidence_score_negativo_e_rejeitado(self):
        with pytest.raises(Exception):
            BrainDecisionOutput(**self._valid_kwargs(confidence_score=-0.1))

    def test_decision_type_invalido_e_rejeitado(self):
        with pytest.raises(Exception):
            BrainDecisionOutput(**self._valid_kwargs(decision_type="tipo_que_nao_existe"))


class TestRendererSchemas:
    def test_renderer_output_exige_exatamente_4_secoes(self):
        section = dict(section="hook", content="Fala de gancho valida", duration_estimate_seconds=5)
        with pytest.raises(Exception):
            RendererOutput(
                title="Titulo",
                sections=[section, section, section],  # só 3 — min_length=4
                full_script="texto",
                total_duration_estimate_seconds=30,
                archetype_applied="revelacao",
                platform_adaptations="tiktok",
                confidence_score=0.8,
            )

    def test_editing_plan_exige_pelo_menos_1_corte(self):
        with pytest.raises(Exception):
            EditingPlanOutput(
                title="Titulo",
                hook_timestamp=5.0,
                suggested_cuts=[],  # min_length=1
                estimated_final_duration=30.0,
                archetype_used="revelacao",
                production_notes="notas",
            )

    def test_editing_plan_valido_e_aceito(self):
        plan = EditingPlanOutput(
            title="Titulo Final",
            hook_timestamp=3.0,
            suggested_cuts=[
                {"timestamp_start": 0, "timestamp_end": 10, "instruction_type": "keep", "description": "manter abertura"}
            ],
            estimated_final_duration=45.0,
            archetype_used="revelacao",
            production_notes="ritmo rapido",
        )
        assert plan.mode == "editing_plan"
        assert plan.suggested_cuts[0].priority == "recommended"  # default


# =====================================================================
# Parte 3 — run_brain() — orquestração real (DB e LLM mockados na borda)
# =====================================================================


@pytest.fixture
def brain_office_id():
    return uuid.uuid4()


@pytest.fixture
def brain_user_id():
    return uuid.uuid4()


def _patch_brain_repos(monkeypatch, *, niche, ready_videos=None,
                        create_decision_impl=None, run_log_holder=None):
    """Substitui os métodos de repositório usados por run_brain por stubs em
    memória — mantém a lógica de orquestração real (mapeamento de campos,
    resolução de temperatura, modo com/sem referência) sob teste, sem DB."""
    import viraxis.agents.brain.runner as runner_mod

    async def _fake_get_by_office_or_raise(_self, _office_id):
        return niche

    async def _fake_get_ready_by_office(_self, _office_id):
        return ready_videos or []

    calls = {"create_running": [], "mark_success": [], "mark_failed": [], "create_decision": []}

    async def _fake_create_running(_self, **kwargs):
        calls["create_running"].append(kwargs)

        class _FakeRunLog:
            id = uuid.uuid4()

        log = _FakeRunLog()
        if run_log_holder is not None:
            run_log_holder["log"] = log
        return log

    async def _fake_mark_success(_self, log, output_data=None):
        calls["mark_success"].append({"log": log, "output_data": output_data})
        return log

    async def _fake_mark_failed(_self, log, error_message, traceback=None):
        calls["mark_failed"].append({"log": log, "error_message": error_message})
        return log

    async def _fake_create_decision(_self, **kwargs):
        calls["create_decision"].append(kwargs)
        if create_decision_impl:
            return create_decision_impl(kwargs)
        return _make_content_decision(
            kwargs["office_id"], kwargs["user_id"],
            decision_type=kwargs["decision_type"],
            hypothesis=kwargs["hypothesis"],
            reasoning=kwargs["reasoning"],
            selected_topic=kwargs.get("selected_topic"),
            selected_archetype=kwargs.get("selected_archetype"),
            selected_platform=kwargs.get("selected_platform"),
            confidence_score=kwargs.get("confidence_score"),
            raw_video_id=kwargs.get("raw_video_id"),
        )

    monkeypatch.setattr(runner_mod.NicheProfileRepository, "get_by_office_or_raise", _fake_get_by_office_or_raise)
    monkeypatch.setattr(runner_mod.RawVideoRepository, "get_ready_by_office", _fake_get_ready_by_office)
    monkeypatch.setattr(runner_mod.AgentRunLogRepository, "create_running", _fake_create_running)
    monkeypatch.setattr(runner_mod.AgentRunLogRepository, "mark_success", _fake_mark_success)
    monkeypatch.setattr(runner_mod.AgentRunLogRepository, "mark_failed", _fake_mark_failed)
    monkeypatch.setattr(runner_mod.ContentDecisionRepository, "create_decision", _fake_create_decision)
    return calls


class TestRunBrain:
    async def test_new_script_mode_maps_llm_output_into_content_decision(
        self, monkeypatch, brain_office_id, brain_user_id
    ):
        """Modo '100% IA' (sem raw_video_id): o output do LLM deve virar uma
        ContentDecision com os mesmos campos, raw_video_id=None."""
        import viraxis.agents.brain.runner as runner_mod

        niche = _make_niche_profile(office_id=brain_office_id, user_id=brain_user_id, brain_params={"temperature": 0.55})
        session = FakeAsyncSession()
        monkeypatch.setattr(runner_mod, "AsyncSessionLocal", lambda: session)
        calls = _patch_brain_repos(monkeypatch, niche=niche)

        canned_output = BrainDecisionOutput(
            decision_type="archetype_selection",
            hypothesis="Este conteudo vai performar porque revelacao domina o nicho com 60% de peso historico.",
            reasoning={"sinais_identificados": ["revelacao 60%"], "alternativas_descartadas": ["humor"], "justificativa_final": "peso historico"},
            selected_topic="Como sair das dividas em 90 dias",
            selected_archetype="revelacao",
            selected_platform="tiktok",
            confidence_score=0.88,
            raw_video_id=None,
        )

        captured_temperature = {}

        def _fake_run_crew_sync(niche_input, temperature):
            captured_temperature["value"] = temperature
            captured_temperature["niche_input"] = niche_input
            return canned_output

        monkeypatch.setattr(runner_mod, "_run_crew_sync", _fake_run_crew_sync)

        from viraxis.agents.brain.runner import run_brain

        decision = await run_brain(brain_office_id, brain_user_id)

        # Temperatura resolvida de brain_params (nenhum argumento explícito passado)
        assert captured_temperature["value"] == pytest.approx(0.55)
        # Mapeamento de campos do output do LLM para a ContentDecision
        assert decision.decision_type == DecisionType.archetype_selection
        assert decision.hypothesis == canned_output.hypothesis
        assert decision.selected_topic == "Como sair das dividas em 90 dias"
        assert decision.confidence_score == pytest.approx(0.88)
        assert decision.raw_video_id is None
        assert len(calls["create_decision"]) == 1
        assert len(calls["mark_success"]) == 1
        assert len(calls["mark_failed"]) == 0

    async def test_explicit_temperature_argument_overrides_brain_params(
        self, monkeypatch, brain_office_id, brain_user_id
    ):
        import viraxis.agents.brain.runner as runner_mod

        niche = _make_niche_profile(office_id=brain_office_id, user_id=brain_user_id, brain_params={"temperature": 0.55})
        session = FakeAsyncSession()
        monkeypatch.setattr(runner_mod, "AsyncSessionLocal", lambda: session)
        _patch_brain_repos(monkeypatch, niche=niche)

        canned_output = BrainDecisionOutput(
            decision_type="content_topic",
            hypothesis="Este conteudo vai performar porque ha um pico sazonal de interesse no tema agora.",
            reasoning={"sinais_identificados": [], "alternativas_descartadas": [], "justificativa_final": ""},
            confidence_score=0.6,
        )
        captured = {}

        def _fake_run_crew_sync(niche_input, temperature):
            captured["value"] = temperature
            return canned_output

        monkeypatch.setattr(runner_mod, "_run_crew_sync", _fake_run_crew_sync)

        from viraxis.agents.brain.runner import run_brain

        await run_brain(brain_office_id, brain_user_id, temperature=0.9)
        assert captured["value"] == pytest.approx(0.9)

    async def test_reference_mode_links_raw_video_and_builds_context(
        self, monkeypatch, brain_office_id, brain_user_id
    ):
        """Modo 'com referência': o vídeo bruto selecionado precisa aparecer no
        BrainDecisionInput (reference_video) e o raw_video_id do parâmetro
        precisa ser propagado para a ContentDecision final."""
        import viraxis.agents.brain.runner as runner_mod

        niche = _make_niche_profile(office_id=brain_office_id, user_id=brain_user_id)
        raw_video = _make_raw_video(brain_office_id, title="Video Cru Selecionado")
        session = FakeAsyncSession()
        session.seed(raw_video)
        monkeypatch.setattr(runner_mod, "AsyncSessionLocal", lambda: session)
        calls = _patch_brain_repos(monkeypatch, niche=niche, ready_videos=[raw_video])

        canned_output = BrainDecisionOutput(
            decision_type="content_topic",
            hypothesis="Este video vai performar porque o hook forte esta nos primeiros 5 segundos.",
            reasoning={"sinais_identificados": [], "alternativas_descartadas": [], "justificativa_final": ""},
            selected_topic=f"[video:{str(raw_video.id)[:8]}] Titulo editado",
            confidence_score=0.7,
            raw_video_id=str(raw_video.id),
        )

        captured_input = {}

        def _fake_run_crew_sync(niche_input, temperature):
            captured_input["value"] = niche_input
            return canned_output

        monkeypatch.setattr(runner_mod, "_run_crew_sync", _fake_run_crew_sync)

        from viraxis.agents.brain.runner import run_brain

        decision = await run_brain(brain_office_id, brain_user_id, raw_video_id=raw_video.id)

        niche_input: BrainDecisionInput = captured_input["value"]
        assert niche_input.reference_video is not None
        assert niche_input.reference_video.id == str(raw_video.id)
        assert niche_input.reference_video.title == "Video Cru Selecionado"
        assert decision.raw_video_id == raw_video.id
        assert calls["create_decision"][0]["raw_video_id"] == raw_video.id

    async def test_reference_mode_video_not_found_raises_value_error(
        self, monkeypatch, brain_office_id, brain_user_id
    ):
        import viraxis.agents.brain.runner as runner_mod

        niche = _make_niche_profile(office_id=brain_office_id, user_id=brain_user_id)
        session = FakeAsyncSession()  # RawVideo NÃO semeado -> session.get devolve None
        monkeypatch.setattr(runner_mod, "AsyncSessionLocal", lambda: session)
        calls = _patch_brain_repos(monkeypatch, niche=niche)
        monkeypatch.setattr(runner_mod, "_run_crew_sync", lambda *a, **k: pytest.fail("não deveria chamar o LLM"))

        from viraxis.agents.brain.runner import run_brain

        with pytest.raises(ValueError, match="não encontrado"):
            await run_brain(brain_office_id, brain_user_id, raw_video_id=uuid.uuid4())

        assert len(calls["create_decision"]) == 0

    async def test_crew_failure_marks_run_log_failed_and_reraises(
        self, monkeypatch, brain_office_id, brain_user_id
    ):
        import viraxis.agents.brain.runner as runner_mod

        niche = _make_niche_profile(office_id=brain_office_id, user_id=brain_user_id)
        session = FakeAsyncSession()
        monkeypatch.setattr(runner_mod, "AsyncSessionLocal", lambda: session)
        calls = _patch_brain_repos(monkeypatch, niche=niche)

        def _boom(_niche_input, _temperature):
            raise RuntimeError("LLM indisponível no momento")

        monkeypatch.setattr(runner_mod, "_run_crew_sync", _boom)

        from viraxis.agents.brain.runner import run_brain

        with pytest.raises(RuntimeError, match="LLM indisponível"):
            await run_brain(brain_office_id, brain_user_id)

        assert len(calls["mark_failed"]) == 1
        assert "LLM indisponível" in calls["mark_failed"][0]["error_message"]
        assert len(calls["create_decision"]) == 0

    async def test_missing_niche_profile_propagates_value_error(
        self, monkeypatch, brain_office_id, brain_user_id
    ):
        import viraxis.agents.brain.runner as runner_mod

        session = FakeAsyncSession()
        monkeypatch.setattr(runner_mod, "AsyncSessionLocal", lambda: session)

        async def _raise_missing(_self, _office_id):
            raise ValueError(f"NicheProfile para office_id={brain_office_id} não encontrado.")

        monkeypatch.setattr(runner_mod.NicheProfileRepository, "get_by_office_or_raise", _raise_missing)

        from viraxis.agents.brain.runner import run_brain

        with pytest.raises(ValueError, match="NicheProfile"):
            await run_brain(brain_office_id, brain_user_id)


# =====================================================================
# Parte 4 — scene_extractor (lógica pura — sem mocks necessários)
# =====================================================================


class TestSplitScenePart:
    def test_formato_novo_dict_separa_narracao_e_visual(self):
        narr, vis = split_scene_part({"narracao": "fala aqui", "descricao_visual": "imagem aqui"})
        assert narr == "fala aqui"
        assert vis == "imagem aqui"

    def test_formato_legado_string_usa_mesmo_texto_para_ambos(self):
        narr, vis = split_scene_part("texto unico legado")
        assert narr == "texto unico legado"
        assert vis == "texto unico legado"

    def test_dict_sem_visual_cai_para_narracao(self):
        narr, vis = split_scene_part({"narracao": "so fala"})
        assert narr == "so fala"
        assert vis == "so fala"

    def test_dict_vazio_retorna_strings_vazias(self):
        narr, vis = split_scene_part({})
        assert narr == ""
        assert vis == ""

    def test_none_retorna_strings_vazias(self):
        narr, vis = split_scene_part(None)
        assert narr == ""
        assert vis == ""


class TestExtractScenes:
    def _roteiro_completo(self):
        return {
            "roteiro": {
                "hook": {"narracao": "Voce sabia que 90% erram isso?", "descricao_visual": "pessoa surpresa"},
                "desenvolvimento": [
                    {"narracao": "Primeiro erro e nao ter reserva.", "descricao_visual": "cofre vazio"},
                    {"narracao": "Segundo erro e gastar no cartao.", "descricao_visual": "cartao de credito"},
                ],
                "climax": {"narracao": "O resultado disso e a divida crescendo.", "descricao_visual": "grafico subindo"},
                "cta": {"narracao": "Segue pra mais dicas como essa!", "descricao_visual": "logo da marca"},
            }
        }

    def test_extrai_5_cenas_na_ordem_hook_dev_dev_climax_cta(self):
        scenes = extract_scenes(self._roteiro_completo())
        assert len(scenes) == 5
        assert [s.index for s in scenes] == [0, 1, 2, 3, 4]
        assert scenes[0].narration.startswith("Voce sabia")
        assert scenes[-1].narration.startswith("Segue pra mais dicas")

    def test_cena_de_cta_nao_tem_imagem(self):
        scenes = extract_scenes(self._roteiro_completo())
        cta = scenes[-1]
        assert cta.has_image is False
        assert cta.visual_description == ""

    def test_cenas_de_hook_dev_climax_tem_imagem(self):
        scenes = extract_scenes(self._roteiro_completo())
        for s in scenes[:-1]:
            assert s.has_image is True
            assert s.visual_description != ""

    def test_desenvolvimento_como_item_unico_dict_vira_lista_de_1(self):
        meta = {"roteiro": {
            "hook": {"narracao": "abertura"},
            "desenvolvimento": {"narracao": "unico desenvolvimento"},
            "climax": {"narracao": "fim"},
            "cta": {"narracao": "chamada"},
        }}
        scenes = extract_scenes(meta)
        assert len(scenes) == 4  # hook + 1 dev + climax + cta

    def test_formato_legado_string_pura_tambem_funciona(self):
        meta = {"roteiro": {
            "hook": "gancho legado",
            "desenvolvimento": ["dev 1 legado", "dev 2 legado"],
            "climax": "climax legado",
            "cta": "cta legado",
        }}
        scenes = extract_scenes(meta)
        assert len(scenes) == 5
        assert scenes[0].narration == "gancho legado"
        assert scenes[0].visual_description == "gancho legado"

    def test_partes_sem_narracao_sao_ignoradas(self):
        meta = {"roteiro": {
            "hook": {"narracao": "", "descricao_visual": "imagem sem fala"},
            "desenvolvimento": [{"narracao": "dev valido"}],
            "climax": {"narracao": ""},
            "cta": {"narracao": "cta valido"},
        }}
        scenes = extract_scenes(meta)
        # hook (sem narração) e climax (sem narração) devem ser pulados
        assert len(scenes) == 2
        assert scenes[0].narration == "dev valido"
        assert scenes[1].narration == "cta valido"

    def test_roteiro_vazio_levanta_value_error(self):
        with pytest.raises(ValueError, match="sem cenas"):
            extract_scenes({"roteiro": {}})

    def test_production_meta_sem_roteiro_levanta_value_error(self):
        with pytest.raises(ValueError):
            extract_scenes({})

    def test_duration_hint_respeita_minimo_e_maximo(self):
        meta_curto = {"roteiro": {"hook": {"narracao": "Oi"}, "desenvolvimento": [], "climax": {"narracao": ""}, "cta": {"narracao": ""}}}
        scenes_curto = extract_scenes(meta_curto)
        assert scenes_curto[0].duration_hint >= 2  # _MIN_DURATION_HINT

        texto_longo = "palavra " * 200  # bem mais que 12s * 15 chars/s
        meta_longo = {"roteiro": {"hook": {"narracao": texto_longo}, "desenvolvimento": [], "climax": {"narracao": ""}, "cta": {"narracao": ""}}}
        scenes_longo = extract_scenes(meta_longo)
        assert scenes_longo[0].duration_hint <= 12  # _MAX_DURATION_HINT


# =====================================================================
# Parte 5 — run_renderer_v2() — orquestração real (LLM e DB mockados)
# =====================================================================


def _fake_llm_response(payload: dict):
    class _Msg:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content):
            self.message = _Msg(content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    return _Resp(json.dumps(payload, ensure_ascii=False))


_NEW_SCRIPT_PAYLOAD = {
    "roteiro": {
        "hook": {"narracao": "Voce sabia disso?", "descricao_visual": "pessoa chocada"},
        "desenvolvimento": [
            {"narracao": "Primeiro ponto importante.", "descricao_visual": "grafico"},
        ],
        "climax": {"narracao": "E ai tudo muda.", "descricao_visual": "explosao de cores"},
        "cta": "Segue pra mais!",
    },
    "titulos": ["3 Segredos Que Ninguem Te Conta 😱", "Guia Definitivo", "Alternativa Criativa"],
    "thumbnails": [{"descricao": "d", "cores_principais": ["#FFF"], "elementos": [], "texto_overlay": "t", "composicao": "c"}] * 3,
    "seo": {"titulo_otimizado": "t", "descricao": "d", "tags": ["a"], "hashtags": ["#a"], "categoria": "cat"},
    "plano_postagem": {"melhor_dia": "Sabado", "melhor_horario": "19h", "frequencia_ideal": "3x", "estrategia_reposts": "e", "notas": "n"},
    "checklist_producao": ["item1", "item2"],
    "duracao_estimada_segundos": 42,
}

_EDITING_PLAN_PAYLOAD = {
    "plano_edicao": {
        "hook_timestamp": 5,
        "cortes": [
            {"inicio": 0, "fim": 5, "tipo": "cut", "descricao": "cortar introducao lenta", "prioridade": "essencial"},
            {"inicio": 5, "fim": 30, "tipo": "keep", "descricao": "manter parte forte", "prioridade": "essencial"},
        ],
        "textos_tela": [{"inicio": 0, "fim": 3, "texto": "OLHA ISSO"}],
        "trilha_sonora": "upbeat eletronico",
        "duracao_final_segundos": 25,
        "notas_producao": "cortes rapidos, sem pausas",
    },
    "titulos": ["Titulo Editado 1", "Titulo 2", "Titulo 3"],
    "thumbnails": [{"descricao": "d", "cores_principais": ["#FFF"], "elementos": [], "texto_overlay": "t", "composicao": "c"}] * 3,
    "seo": {"titulo_otimizado": "t", "descricao": "d", "tags": ["a"], "hashtags": ["#a"], "categoria": "cat"},
    "plano_postagem": {"melhor_dia": "Sabado", "melhor_horario": "19h", "frequencia_ideal": "3x", "estrategia_reposts": "e", "notas": "n"},
    "checklist_producao": ["item1"],
    "duracao_estimada_segundos": 25,
}


@pytest.fixture
def renderer_office_id():
    return uuid.uuid4()


@pytest.fixture
def renderer_user_id():
    return uuid.uuid4()


def _patch_renderer_niche(monkeypatch, niche):
    import viraxis.agents.renderer.v2_direct as v2_mod

    async def _fake_get_by_office_or_raise(_self, _office_id):
        return niche

    monkeypatch.setattr(v2_mod.NicheProfileRepository, "get_by_office_or_raise", _fake_get_by_office_or_raise)


class TestRunRendererV2:
    async def test_new_script_mode_produces_review_item_with_formatted_script(
        self, monkeypatch, renderer_office_id, renderer_user_id
    ):
        import viraxis.agents.renderer.v2_direct as v2_mod

        niche = _make_niche_profile(office_id=renderer_office_id, user_id=renderer_user_id)
        decision = _make_content_decision(renderer_office_id, renderer_user_id, raw_video_id=None)
        session = FakeAsyncSession()
        session.seed(decision)
        monkeypatch.setattr(v2_mod, "AsyncSessionLocal", lambda: session)
        _patch_renderer_niche(monkeypatch, niche)

        async def _fake_acompletion(**_kwargs):
            return _fake_llm_response(_NEW_SCRIPT_PAYLOAD)

        monkeypatch.setattr("litellm.acompletion", _fake_acompletion)

        from viraxis.agents.renderer.v2_direct import run_renderer_v2

        item = await run_renderer_v2(renderer_office_id, renderer_user_id, decision.id)

        assert item.status == ContentStatus.review
        assert item.title == "3 Segredos Que Ninguem Te Conta 😱"
        assert item.duration_seconds == pytest.approx(42.0)
        assert "HOOK" in item.script
        assert "Voce sabia disso?" in item.script  # narração presente
        # `item.script` é a versão humana/editor (inclui notas visuais 🖼️
        # de propósito); quem separa fala de imagem para o TTS é
        # `_extract_script_for_tts` (coberto na Parte 8 abaixo).
        assert "pessoa chocada" in item.script
        assert item.production_meta["mode"] == "new_script"
        assert decision.status == DecisionStatus.done

    async def test_editing_plan_mode_produces_edit_plan_script(
        self, monkeypatch, renderer_office_id, renderer_user_id
    ):
        import viraxis.agents.renderer.v2_direct as v2_mod

        niche = _make_niche_profile(office_id=renderer_office_id, user_id=renderer_user_id)
        raw_video = _make_raw_video(renderer_office_id, duration_seconds=60.0)
        decision = _make_content_decision(renderer_office_id, renderer_user_id, raw_video_id=raw_video.id)
        session = FakeAsyncSession()
        session.seed(decision)
        session.seed(raw_video)
        monkeypatch.setattr(v2_mod, "AsyncSessionLocal", lambda: session)
        _patch_renderer_niche(monkeypatch, niche)

        async def _fake_acompletion(**_kwargs):
            return _fake_llm_response(_EDITING_PLAN_PAYLOAD)

        monkeypatch.setattr("litellm.acompletion", _fake_acompletion)

        from viraxis.agents.renderer.v2_direct import run_renderer_v2

        item = await run_renderer_v2(renderer_office_id, renderer_user_id, decision.id)

        assert item.status == ContentStatus.review
        assert item.title == "Titulo Editado 1"
        assert item.duration_seconds == pytest.approx(25.0)
        assert "PLANO DE EDIÇÃO" in item.script
        assert "cortar introducao lenta" in item.script
        assert item.production_meta["mode"] == "editing_plan"
        assert item.production_meta["plano_edicao"]["hook_timestamp"] == 5
        assert item.production_meta["raw_video"]["id"] == str(raw_video.id)
        assert decision.status == DecisionStatus.done

    async def test_retries_on_invalid_json_then_succeeds(
        self, monkeypatch, renderer_office_id, renderer_user_id
    ):
        import viraxis.agents.renderer.v2_direct as v2_mod

        niche = _make_niche_profile(office_id=renderer_office_id, user_id=renderer_user_id)
        decision = _make_content_decision(renderer_office_id, renderer_user_id, raw_video_id=None)
        session = FakeAsyncSession()
        session.seed(decision)
        monkeypatch.setattr(v2_mod, "AsyncSessionLocal", lambda: session)
        _patch_renderer_niche(monkeypatch, niche)

        call_count = {"n": 0}

        async def _flaky_acompletion(**_kwargs):
            # Falha de parsing real nas 2 primeiras tentativas (JSON malformado),
            # sucesso na 3a — exercita o loop de retry (MAX_RETRIES=3) de verdade.
            call_count["n"] += 1
            if call_count["n"] < 3:
                class _BadResp:
                    choices = [type("C", (), {"message": type("M", (), {"content": "isto nao e json{{{"})()})()]
                return _BadResp()
            return _fake_llm_response(_NEW_SCRIPT_PAYLOAD)

        monkeypatch.setattr("litellm.acompletion", _flaky_acompletion)
        # `asyncio.sleep` é importado localmente dentro do loop de retry — o
        # `import asyncio` local reaproveita o módulo stdlib real, então
        # substituir o atributo no módulo `asyncio` importado aqui também
        # afeta essa chamada local (mesmo objeto de módulo).
        monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: _noop_awaitable())

        from viraxis.agents.renderer.v2_direct import run_renderer_v2

        item = await run_renderer_v2(renderer_office_id, renderer_user_id, decision.id)

        assert call_count["n"] == 3
        assert item.status == ContentStatus.review
        assert item.title == "3 Segredos Que Ninguem Te Conta 😱"

    async def test_all_retries_fail_marks_item_failed_and_raises(
        self, monkeypatch, renderer_office_id, renderer_user_id
    ):
        import viraxis.agents.renderer.v2_direct as v2_mod

        niche = _make_niche_profile(office_id=renderer_office_id, user_id=renderer_user_id)
        decision = _make_content_decision(renderer_office_id, renderer_user_id, raw_video_id=None)
        session = FakeAsyncSession()
        session.seed(decision)
        monkeypatch.setattr(v2_mod, "AsyncSessionLocal", lambda: session)
        _patch_renderer_niche(monkeypatch, niche)

        async def _always_broken(**_kwargs):
            class _BadResp:
                choices = [type("C", (), {"message": type("M", (), {"content": "nunca vai ser json valido {{{"})()})()]
            return _BadResp()

        monkeypatch.setattr("litellm.acompletion", _always_broken)
        monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: _noop_awaitable())

        mark_failed_calls = []

        async def _fake_mark_failed(item_id, decision_id, error):
            mark_failed_calls.append((item_id, decision_id, error))

        monkeypatch.setattr(v2_mod, "_mark_failed", _fake_mark_failed)

        from viraxis.agents.renderer.v2_direct import run_renderer_v2

        with pytest.raises(RuntimeError, match="falhou após"):
            await run_renderer_v2(renderer_office_id, renderer_user_id, decision.id)

        assert len(mark_failed_calls) == 1
        failed_item_id, failed_decision_id, _err = mark_failed_calls[0]
        assert failed_decision_id == decision.id
        # O ContentItem foi criado (block 2) antes da falha do LLM (block 4) —
        # deve ser o mesmo item registrado na store da sessão fake.
        stored_item = session.store[ContentItem]
        assert failed_item_id == stored_item.id


async def _noop_awaitable():
    return None


# =====================================================================
# Parte 6 — video_composer_v2.compose_ai_video_v2 — orquestração real
# (FFmpeg/TTS/geração de imagem mockados na borda)
# =====================================================================


_COMPOSER_META = {
    "roteiro": {
        "hook": {"narracao": "Gancho forte para prender atencao.", "descricao_visual": "cena 1"},
        "desenvolvimento": [
            {"narracao": "Desenvolvimento um com bastante conteudo.", "descricao_visual": "cena 2"},
            {"narracao": "Desenvolvimento dois fechando a ideia.", "descricao_visual": "cena 3"},
        ],
        "climax": {"narracao": "O climax revela a virada da historia.", "descricao_visual": "cena 4"},
        "cta": {"narracao": "Segue pra mais conteudo como este.", "descricao_visual": "logo"},
    }
}


def _patch_composer_io(monkeypatch, *, image_should_fail=False, burn_should_fail=False,
                        ffmpeg_calls: list | None = None):
    import viraxis.infrastructure.video_composer_v2 as vc

    calls = ffmpeg_calls if ffmpeg_calls is not None else []

    async def _fake_run_ffmpeg(args):
        calls.append(args)
        joined = " ".join(str(a) for a in args)
        if burn_should_fail and "subtitles=" in joined:
            raise RuntimeError("FFmpeg falhou simulado no burn-in")
        return None

    async def _fake_synthesize_pt(_text, _voice):
        return b"FAKE_AUDIO_BYTES_" * 100

    async def _fake_generate_scene_image(_desc, seed=None):
        if image_should_fail:
            from viraxis.infrastructure.image_generator import ImageGenerationError
            raise ImageGenerationError("todos os provedores falharam (simulado)")
        return b"FAKE_IMAGE_BYTES_" * 100

    async def _fake_probe_duration(_path):
        return 3.0

    async def _fake_upload_to_storage(_path, dest_path, content_type="video/mp4"):
        return dest_path

    async def _fake_sign_storage_path(dest_path, expires_in=604800):
        return f"https://fake-supabase.qa/signed/{dest_path}"

    monkeypatch.setattr(vc, "_run_ffmpeg", _fake_run_ffmpeg)
    monkeypatch.setattr(vc, "synthesize_pt", _fake_synthesize_pt)
    monkeypatch.setattr(vc, "generate_scene_image", _fake_generate_scene_image)
    monkeypatch.setattr(vc, "_probe_duration", _fake_probe_duration)
    monkeypatch.setattr(vc, "upload_to_storage", _fake_upload_to_storage)
    monkeypatch.setattr(vc, "sign_storage_path", _fake_sign_storage_path)
    return calls


class TestComposeAiVideoV2:
    async def test_happy_path_generates_segment_per_scene_plus_concat_and_burn(self, monkeypatch):
        calls = _patch_composer_io(monkeypatch)
        from viraxis.infrastructure.video_composer_v2 import compose_ai_video_v2

        item_id = str(uuid.uuid4())
        progress_events = []

        async def _cb(pct, stage):
            progress_events.append((pct, stage))

        dest_path, signed_url = await compose_ai_video_v2(_COMPOSER_META, "script fallback nao usado", item_id, progress_cb=_cb)

        assert dest_path == f"ai_generated/{item_id}.mp4"
        assert signed_url == f"https://fake-supabase.qa/signed/{dest_path}"

        # 5 cenas (hook + 2 dev + climax + cta) => 5 segmentos + 1 concat + 1 burn-in
        assert len(calls) == 7
        joined_calls = [" ".join(str(a) for a in c) for c in calls]
        zoompan_calls = [c for c in joined_calls if "zoompan" in c]
        lavfi_calls = [c for c in joined_calls if "-f lavfi" in c or ("-f" in c and "lavfi" in c)]
        # hook + 2 dev + climax têm imagem (Ken Burns); CTA é sempre fundo sólido
        assert len(zoompan_calls) == 4
        assert any("color=c=" in c for c in joined_calls)  # segmento sólido do CTA

        # progresso reportado do início ao fim
        assert progress_events[-1] == (100, "concluído")
        assert any(stage == "montando o vídeo" for _pct, stage in progress_events)

    async def test_image_generation_failure_falls_back_to_solid_segment_for_every_scene(self, monkeypatch):
        calls = _patch_composer_io(monkeypatch, image_should_fail=True)
        from viraxis.infrastructure.video_composer_v2 import compose_ai_video_v2

        item_id = str(uuid.uuid4())
        await compose_ai_video_v2(_COMPOSER_META, "", item_id)

        joined_calls = [" ".join(str(a) for a in c) for c in calls]
        zoompan_calls = [c for c in joined_calls if "zoompan" in c]
        # com geração de imagem sempre falhando, NENHUM segmento deve usar Ken Burns
        assert len(zoompan_calls) == 0

    async def test_subtitle_burn_failure_falls_back_to_video_without_captions(self, monkeypatch):
        """Se o burn-in de legendas falhar, o vídeo ainda deve ser enviado (sem
        legenda é melhor que sem vídeo nenhum) — não pode derrubar o pipeline."""
        upload_calls = []

        calls = _patch_composer_io(monkeypatch, burn_should_fail=True)
        import viraxis.infrastructure.video_composer_v2 as vc

        original_upload = vc.upload_to_storage

        async def _tracking_upload(path, dest_path, content_type="video/mp4"):
            upload_calls.append((path, dest_path))
            return await original_upload(path, dest_path, content_type)

        monkeypatch.setattr(vc, "upload_to_storage", _tracking_upload)

        from viraxis.infrastructure.video_composer_v2 import compose_ai_video_v2

        item_id = str(uuid.uuid4())
        dest_path, signed_url = await compose_ai_video_v2(_COMPOSER_META, "", item_id)

        assert dest_path == f"ai_generated/{item_id}.mp4"
        assert len(upload_calls) == 1  # upload aconteceu mesmo com burn-in falhando
        # o path enviado deve ser o vídeo concatenado (sem sufixo "final"),
        # já que o burn-in falhou e o fallback usa o concat direto
        assert upload_calls[0][0].name == "concat.mp4"

    async def test_falls_back_to_single_scene_when_roteiro_missing(self, monkeypatch):
        """`_resolve_scenes` usa o `script_text` inteiro como cena única quando
        não há roteiro estruturado no production_meta."""
        calls = _patch_composer_io(monkeypatch)
        from viraxis.infrastructure.video_composer_v2 import compose_ai_video_v2

        item_id = str(uuid.uuid4())
        await compose_ai_video_v2({}, "Um script corrido qualquer sem estrutura de cenas.", item_id)

        # 1 cena (sem imagem, pois `has_image` default é True mas sem "cta" role
        # explícito o fallback usa Scene default has_image=True) => 1 segmento + concat + burn
        assert len(calls) == 3


# =====================================================================
# Parte 7 — POST /offices/{office_id}/content-items/{item_id}/process-video
# =====================================================================


from viraxis.api.deps import get_current_user, get_session
from viraxis.api.main import app
from viraxis.domain.models.office import Office, OfficeStatus
from viraxis.domain.models.user import User, UserPlan, UserRole


class _ItemsFakeSession:
    """Mesma ideia da FakeSession de test_uuid_validation.py: fila de
    resultados devolvidos por `.execute()` na ordem em que o endpoint
    executa suas queries (office -> item)."""

    def __init__(self, results=None):
        self._queue = list(results or [])
        self.added = []
        self.committed = False

    async def execute(self, *_a, **_k):
        value = self._queue.pop(0) if self._queue else None

        class _R:
            def __init__(self, v):
                self._v = v

            def scalar_one_or_none(self):
                return self._v

        return _R(value)

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


@pytest.fixture
def process_video_user():
    return User(
        id=uuid.uuid4(), email="qa-pipeline@viraxis.dev", hashed_password="x",
        full_name="QA Pipeline", plan=UserPlan.free, is_active=True, is_verified=True,
        role=UserRole.user,
    )


@pytest.fixture
def process_video_client_factory(process_video_user):
    def _make(fake_session=None):
        session = fake_session if fake_session is not None else _ItemsFakeSession()

        async def _override_user():
            return process_video_user

        async def _override_session():
            yield session

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_session] = _override_session
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def _pv_office(user_id):
    return Office(id=uuid.uuid4(), user_id=user_id, name="Escritorio QA", niche="qa", status=OfficeStatus.active,
                  created_at=_now(), updated_at=_now())


def _pv_item(office_id, user_id, **overrides):
    return _make_content_item(office_id, user_id, decision_id=None, **overrides)


class TestProcessVideoEndpoint:
    def test_new_script_mode_dispatches_background_task_and_sets_rendering(
        self, monkeypatch, process_video_client_factory, process_video_user
    ):
        import viraxis.api.routers.content_items as ci_mod

        office = _pv_office(process_video_user.id)
        item = _pv_item(office.id, process_video_user.id, status=ContentStatus.review,
                         production_meta={"mode": "new_script", "roteiro": {"hook": {"narracao": "oi"}}})

        dispatched = []

        async def _fake_bg(item_id):
            dispatched.append(item_id)

        monkeypatch.setattr(ci_mod, "_compose_ai_video_v2_background", _fake_bg)

        client = process_video_client_factory(_ItemsFakeSession(results=[office, item]))
        resp = client.post(f"/offices/{office.id}/content-items/{item.id}/process-video")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "new_script"
        assert body["status"] == "rendering"
        assert body["storage_path"] == f"ai_generated/{item.id}.mp4"
        assert item.status == ContentStatus.rendering
        assert dispatched == [item.id]

    def test_editing_plan_mode_dispatches_background_task(
        self, monkeypatch, process_video_client_factory, process_video_user
    ):
        import viraxis.api.routers.content_items as ci_mod

        office = _pv_office(process_video_user.id)
        item = _pv_item(office.id, process_video_user.id, status=ContentStatus.review,
                         production_meta={"plano_edicao": {"cortes": []}, "raw_video_id": str(uuid.uuid4())})

        dispatched = []

        async def _fake_bg(item_id):
            dispatched.append(item_id)

        monkeypatch.setattr(ci_mod, "_apply_editing_plan_background", _fake_bg)

        client = process_video_client_factory(_ItemsFakeSession(results=[office, item]))
        resp = client.post(f"/offices/{office.id}/content-items/{item.id}/process-video")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "editing_plan"
        assert body["storage_path"] == f"edited/{item.id}.mp4"
        assert dispatched == [item.id]

    def test_missing_production_meta_returns_422(self, process_video_client_factory, process_video_user):
        office = _pv_office(process_video_user.id)
        item = _pv_item(office.id, process_video_user.id, production_meta={})
        client = process_video_client_factory(_ItemsFakeSession(results=[office, item]))
        resp = client.post(f"/offices/{office.id}/content-items/{item.id}/process-video")
        assert resp.status_code == 422
        assert "production_meta" in resp.json()["detail"]

    def test_item_already_rendering_returns_422(self, process_video_client_factory, process_video_user):
        office = _pv_office(process_video_user.id)
        item = _pv_item(office.id, process_video_user.id, status=ContentStatus.rendering,
                         production_meta={"mode": "new_script"})
        client = process_video_client_factory(_ItemsFakeSession(results=[office, item]))
        resp = client.post(f"/offices/{office.id}/content-items/{item.id}/process-video")
        assert resp.status_code == 422
        assert "sendo gerado" in resp.json()["detail"]

    def test_new_script_without_narratable_text_returns_422(self, process_video_client_factory, process_video_user):
        office = _pv_office(process_video_user.id)
        # meta não-vazio mas sem roteiro estruturado, sem renderer_output, e
        # item.script vazio -> _extract_script_for_tts devolve "" -> 422
        item = _pv_item(office.id, process_video_user.id, status=ContentStatus.review,
                         script="", production_meta={"algo": "irrelevante"})
        client = process_video_client_factory(_ItemsFakeSession(results=[office, item]))
        resp = client.post(f"/offices/{office.id}/content-items/{item.id}/process-video")
        assert resp.status_code == 422
        assert "script para narração" in resp.json()["detail"]

    def test_unknown_mode_returns_422(self, process_video_client_factory, process_video_user):
        office = _pv_office(process_video_user.id)
        item = _pv_item(office.id, process_video_user.id, status=ContentStatus.review,
                         production_meta={"mode": "modo_que_nao_existe"})
        client = process_video_client_factory(_ItemsFakeSession(results=[office, item]))
        resp = client.post(f"/offices/{office.id}/content-items/{item.id}/process-video")
        assert resp.status_code == 422
        assert "mode desconhecido" in resp.json()["detail"]

    def test_item_not_found_returns_404(self, process_video_client_factory, process_video_user):
        office = _pv_office(process_video_user.id)
        client = process_video_client_factory(_ItemsFakeSession(results=[office, None]))
        resp = client.post(f"/offices/{office.id}/content-items/{uuid.uuid4()}/process-video")
        assert resp.status_code == 404


# =====================================================================
# Parte 8 — _extract_script_for_tts (lógica pura de extração de texto p/ TTS)
# =====================================================================


class TestExtractScriptForTts:
    def test_extrai_apenas_narracao_do_roteiro_estruturado_v2(self):
        from viraxis.api.routers.content_items import _extract_script_for_tts

        item = _make_content_item(
            uuid.uuid4(), uuid.uuid4(), None,
            production_meta={
                "roteiro": {
                    "hook": {"narracao": "fala do gancho", "descricao_visual": "NUNCA deveria aparecer"},
                    "desenvolvimento": [{"narracao": "fala do desenvolvimento", "descricao_visual": "tambem nao"}],
                    "climax": {"narracao": "fala do climax", "descricao_visual": "nem esta"},
                    "cta": "fala do cta",
                }
            },
        )
        text = _extract_script_for_tts(item)
        assert "fala do gancho" in text
        assert "fala do desenvolvimento" in text
        assert "fala do climax" in text
        assert "fala do cta" in text
        assert "NUNCA deveria aparecer" not in text
        assert "tambem nao" not in text

    def test_fallback_para_renderer_output_full_script(self):
        from viraxis.api.routers.content_items import _extract_script_for_tts

        item = _make_content_item(
            uuid.uuid4(), uuid.uuid4(), None,
            production_meta={"renderer_output": {"full_script": "roteiro completo do crewai"}},
        )
        text = _extract_script_for_tts(item)
        assert text == "roteiro completo do crewai"

    def test_fallback_final_usa_script_bruto_removendo_markdown(self):
        from viraxis.api.routers.content_items import _extract_script_for_tts

        item = _make_content_item(
            uuid.uuid4(), uuid.uuid4(), None,
            production_meta={},
            script="# Titulo\n\n**negrito** e _italico_",
        )
        text = _extract_script_for_tts(item)
        assert "#" not in text
        assert "*" not in text
        assert "Titulo" in text
