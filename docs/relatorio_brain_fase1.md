# VIRAXIS BRAIN — Relatorio Fase 1
**Agente:** BRAIN (Content Strategist)  
**Data:** 08/06/2026  
**Commit:** 2384a27 (main)  
**Status:** ✅ Implementado | ⏳ Pendente validacao E2E com Gemini real

---

## O que e o BRAIN

O BRAIN e o agente central da VIRAXIS. Ele nao produz conteudo — ele **decide** o que produzir e **documenta por que**. Cada decisao e um experimento registrado: hipotese, evidencias, alternativas descartadas e nivel de confianca.

Isso e o diferencial de produto: nao e uma caixa preta que gera conteudo. E um sistema de raciocinio auditavel que acumula aprendizado por escritorio.

---

## Arquitetura do BRAIN (Fase 1)

```
NicheProfile (banco)
       |
       v
BrainDecisionInput          <- serializa o perfil para o agente
       |
       v
CrewAI Agent (BRAIN)        <- LLM: Gemini 2.5 Pro via LiteLLM
       |
       v
CrewAI Task                 <- prompt estruturado + output_pydantic
       |
       v
BrainDecisionOutput         <- Pydantic: validado automaticamente
       |
       v
ContentDecision (banco)     <- persistido com status=pending
```

---

## Componentes Entregues

### 1. config.py — Settings Central

Pydantic-settings com `.env` automatico. Campos calculados:

- `database_url_async` — `postgresql+asyncpg://...` (para SQLAlchemy async)
- `database_url_sync` — `postgresql+psycopg2://...` (para Alembic CLI)

Singleton via `@lru_cache` — o `.env` e lido uma unica vez em toda a execucao.

**Decisao tecnica:** LLM provider e configuravel por variavel de ambiente (`LLM_MODEL=gemini/gemini-2.5-pro`). Trocar para Claude e mudar duas linhas no `.env`.

---

### 2. session.py — Async Session Factory

```python
engine = create_async_engine(database_url_async, pool_size=10, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
```

- `pool_pre_ping=True` — reconecta automaticamente se o Postgres reiniciar
- `expire_on_commit=False` — evita lazy-load acidental apos o commit
- `get_session()` — dependency injection pronto para FastAPI (`Depends(get_session)`)

---

### 3. BaseRepository[T] — CRUD Async Generico

Metodos disponíveis para qualquer model:

| Metodo | Descricao |
|---|---|
| `get(id)` | Busca por PK, retorna None se nao encontrado |
| `get_or_raise(id)` | Busca por PK, lanca ValueError se nao encontrado |
| `list(*filters, limit, offset, order_by)` | Lista com filtros e paginacao |
| `create(**kwargs)` | Cria e faz flush (sem commit — transacao do chamador) |
| `save(instance)` | Atualiza e faz flush |
| `delete(instance)` | Remove e faz flush |

**Decisao tecnica:** `flush()` sem `commit()` nos metodos base. O commit e responsabilidade do chamador (runner), que controla a transacao inteira. Isso evita commits parciais em caso de erro entre o fim do Crew e a persistencia.

---

### 4. ContentDecisionRepository

Queries especializadas alem do CRUD base:

- `list_by_office(office_id, status=None)` — decisoes mais recentes primeiro
- `get_latest_by_office(office_id)` — ultima decisao do escritorio
- `count_by_status(office_id, status)` — metricas de pipeline
- `update_status(decision, new_status)` — transicao de estado (pending -> executing -> done)
- `create_decision(...)` — assinatura nomeada sem kwargs genericos

---

### 5. NicheProfileRepository

- `get_by_office_id(office_id)` — retorna None se sem perfil
- `get_by_office_or_raise(office_id)` — lanca ValueError com mensagem clara
- `list_by_user(user_id)` — todos os escritorios de um usuario
- `upsert(...)` — cria se nao existe, atualiza campos fornecidos se existe

---

### 6. BrainDecisionInput — Schema de Entrada

Serializa o `NicheProfile` ORM para formato processavel pelo agente:

```python
BrainDecisionInput.from_niche_profile(profile)  # ORM -> Pydantic
input.to_context_string()                         # Pydantic -> texto para o prompt
```

Exemplo de saida de `to_context_string()`:
```
NICHO: Financas Pessoais para Jovens
PLATAFORMAS ALVO: tiktok, instagram
ARCHETYPES VIRAIS: revelacao (40%), transformacao (30%)
KEYWORDS: renda passiva, reserva emergencia, sair das dividas
ESTILO EDITORIAL: direto, 30-60s, gancho com pergunta retorica
```

---

### 7. BrainDecisionOutput — Schema de Saida

Pydantic com validacoes:

| Campo | Tipo | Validacao |
|---|---|---|
| `decision_type` | `Literal[5 tipos]` | enum fechado |
| `hypothesis` | `str` | min 20 chars, max 1000 |
| `reasoning` | `dict` | chaves: sinais_identificados, alternativas_descartadas, justificativa_final |
| `selected_topic` | `str \| None` | max 512 chars |
| `selected_archetype` | `str \| None` | max 128 chars |
| `selected_platform` | `str \| None` | max 64 chars |
| `confidence_score` | `float` | 0.0 <= x <= 1.0 |

O CrewAI instrui o LLM a retornar JSON valido neste schema via `output_pydantic=BrainDecisionOutput`.

---

### 8. Agente BRAIN (agent.py)

```python
Agent(
    role="Estrategista de Conteudo Viral",
    llm=LLM(model="gemini/gemini-2.5-pro"),
    allow_delegation=False,
    max_iter=3,
)
```

- `allow_delegation=False` — o BRAIN nao sub-delega, e autonomo
- `max_iter=3` — maximo de 3 rodadas de auto-reflexao interna antes de entregar
- Backstory instrui o agente a operar como analista de dados, nao por intuicao

---

### 9. Task CrewAI (tasks.py)

Prompt estruturado em 5 etapas:
1. Identificar sinais relevantes do nicho
2. Formular hipotese com dados especificos
3. Documentar alternativas descartadas
4. Escolher o `decision_type` adequado
5. Calibrar `confidence_score` com honestidade

Guia de calibracao de confidence entregue ao agente:
- 0.9+ : dados robustos, padrao claro
- 0.7-0.9: boa evidencia, alguma incerteza  
- 0.5-0.7: dados limitados, decisao exploratorias
- <0.5 : dados insuficientes (sinalizar no reasoning)

---

### 10. Runner Async (runner.py)

Fluxo completo em `run_brain(office_id, user_id)`:

```
1. async with AsyncSessionLocal() as session:
2.     niche = await NicheProfileRepository.get_by_office_or_raise(office_id)
3.     output = await asyncio.to_thread(_run_crew_sync, niche_input, temperature)
4.     decision = await ContentDecisionRepository.create_decision(...)
5.     await session.commit()
6.     return decision
```

**Decisao tecnica critica:** `asyncio.to_thread()` para o `crew.kickoff()`. O CrewAI e sincronico internamente — rodar diretamente num event loop async bloquearia todas as outras coroutines. O `to_thread` executa o Crew numa thread separada, mantendo o event loop livre.

**`_demo()` incluido:** cria um NicheProfile de teste (Financas Pessoais para Jovens), roda o BRAIN e imprime a decisao formatada. Executar com:
```bash
python -m viraxis.agents.brain.runner
```

---

## Pendencias da Fase 1

| Item | Prioridade | Detalhes |
|---|---|---|
| Execucao E2E com Gemini real | Alta | Rodar `_demo()` e validar output |
| Ajuste de prompt | Media | Apos ver primeiros outputs reais |
| Teste unitario do runner (mock do Crew) | Media | Antes de integrar ao Celery |
| Logging estruturado (structlog) | Baixa | Substituir os `logger.info` basicos |

---

## Proximo Passo: Teste Ao Vivo

Para executar o primeiro ciclo completo do BRAIN:

```powershell
cd "C:\Users\Marcos\Claude\Projects\SAAS - Escritorio virtual\viraxis_db"
.venv\Scripts\activate
docker compose up -d
python -m viraxis.agents.brain.runner
```

Isso vai:
1. Criar um NicheProfile de demo no banco
2. Chamar o Gemini 2.5 Pro via LiteLLM
3. Gravar o primeiro `ContentDecision` autonomo da VIRAXIS no banco
4. Imprimir a decisao completa com hipotese e reasoning

---

## Depois da Fase 1: SCOUT

O BRAIN atual decide com base em dados inseridos manualmente no `NicheProfile`. O **SCOUT** vai automatizar a coleta desses dados — monitorando TikTok, YouTube e Google Trends para atualizar `trend_snapshots` e `top_keywords` em tempo real. Com o SCOUT funcionando, o BRAIN passa a decidir com base em sinais reais de mercado.

---

*Gerado por Davi (agente dev VIRAXIS) — 08/06/2026*
