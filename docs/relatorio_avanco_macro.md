# VIRAXIS — Relatorio de Avanco Macro
**Data:** 08/06/2026  
**Versao:** 0.2.0-dev  
**Repositorio:** github.com/marcosalves2036-boop/viraxis (branch main, commit 2384a27)

---

## Visao Geral do Produto

VIRAXIS e uma plataforma SaaS de **Escritorios Virais Autonomos**: agentes de IA que produzem conteudo de curto formato de forma continua, documentando cada decisao tomada. O diferencial nao e gerar conteudo — e gerar conteudo **auditavel**, onde cada escolha de tema, archetype e plataforma tem uma hipotese registrada e um confidence score.

---

## Status por Fase

### FASE 0 — Fundacao de Infraestrutura ✅ CONCLUIDA

| Entrega | Status | Commit |
|---|---|---|
| Skeleton completo do projeto | ✅ | 812facd |
| 9 modelos SQLAlchemy (multi-tenant, async) | ✅ | 812facd |
| Migration Alembic inicial (9 tabelas) | ✅ | 812facd |
| Docker Compose (Postgres 16 + Redis 7) | ✅ | 812facd |
| Ambiente dev Windows (Python 3.12, venv) | ✅ | — |
| GitHub + CI baseline | ✅ | 812facd |

**Resultado:** Banco de dados funcional com schema completo. `alembic upgrade head` cria as 9 tabelas sem erro. Ambiente replicavel com `docker compose up -d`.

---

### FASE 1 — BRAIN Core ✅ CONCLUIDA

| Entrega | Status | Commit |
|---|---|---|
| Settings central (pydantic-settings) | ✅ | 2384a27 |
| AsyncEngine + session factory | ✅ | 2384a27 |
| BaseRepository[T] generico | ✅ | 2384a27 |
| ContentDecisionRepository | ✅ | 2384a27 |
| NicheProfileRepository | ✅ | 2384a27 |
| BrainDecisionInput/Output schemas | ✅ | 2384a27 |
| Agente CrewAI BRAIN (Gemini via LiteLLM) | ✅ | 2384a27 |
| Task com output_pydantic estruturado | ✅ | 2384a27 |
| Runner async (NicheProfile -> Crew -> ContentDecision) | ✅ | 2384a27 |

**Resultado:** Primeira decisao autonoma documentada e possivel. O BRAIN consegue analisar um NicheProfile e gravar um ContentDecision no banco com hipotese, reasoning e confidence score.

**Pendente nesta fase:**
- Execucao ao vivo do `_demo()` com Gemini real (validacao E2E)
- Ajuste fino do prompt com base nos primeiros outputs reais

---

### FASE 2 — Pipeline de Producao 🔜 PROXIMA

| Entrega | Status |
|---|---|
| SCOUT agent (coleta de trends, TikTok/YouTube) | Pendente |
| Celery tasks (orquestracao async de agentes) | Pendente |
| FastAPI — endpoints basicos (offices, decisions) | Pendente |
| WRITER agent (geracao de script) | Pendente |
| Integracao R2 (storage de midia) | Pendente |

---

### FASE 3 — Producao e Publicacao 🔜 FUTURA

| Entrega | Status |
|---|---|
| EDITOR agent (edicao automatica de video) | Planejado |
| PUBLISHER agent (TikTok/Instagram/YouTube API) | Planejado |
| Dashboard de performance (metricas, decisoes) | Planejado |
| Multi-tenant com planos (free/pro/business) | Planejado |
| Auth JWT + onboarding de novos escritorios | Planejado |

---

## Arquitetura Atual

```
src/viraxis/
├── config.py                          # Settings central (pydantic-settings)
├── domain/
│   └── models/                        # 9 modelos SQLAlchemy async
│       ├── user, office, niche_profile
│       ├── content_decision           # Diferencial core (decisao auditavel)
│       ├── content_item, trend_snapshot
│       ├── social_account, performance_metric
│       └── agent_run_log
├── infrastructure/
│   ├── database/
│   │   ├── base.py                    # DeclarativeBase + naming conventions
│   │   └── session.py                 # AsyncEngine + AsyncSessionLocal
│   └── repositories/
│       ├── base.py                    # BaseRepository[T] generico
│       ├── content_decision.py        # Queries especializadas
│       └── niche_profile.py           # upsert + get_by_office_id
└── agents/
    └── brain/
        ├── schemas.py                 # BrainDecisionInput/Output (Pydantic)
        ├── agent.py                   # CrewAI Agent (Gemini/LiteLLM)
        ├── tasks.py                   # CrewAI Task (output_pydantic)
        └── runner.py                  # Orquestrador async E2E
```

---

## Indicadores de Qualidade

| Criterio | Status |
|---|---|
| Sem N+1 queries (lazy="raise" em todos os relacionamentos) | ✅ |
| Async de ponta a ponta (asyncpg + AsyncSession) | ✅ |
| LLM provider intercambivel (Gemini -> Claude com 1 linha) | ✅ |
| Decisoes de IA auditaveis (hypothesis + reasoning no banco) | ✅ |
| Multi-tenant desde a fundacao (user_id + office_id em todas as tabelas) | ✅ |
| Repositorios desacoplados do ORM (testaveis em isolamento) | ✅ |
| Sem credenciais no repositorio (.env no .gitignore) | ✅ |

---

## Proximos Passos Imediatos

1. **Rodar `_demo()` ao vivo** — validar loop completo BRAIN + Gemini + banco
2. **Ajuste de prompt** com base nos primeiros outputs reais do Gemini
3. **SCOUT agent** — coleta de trends para alimentar o BRAIN com sinais reais
4. **FastAPI baseline** — endpoints de autenticacao e gerenciamento de escritorios

---

*Gerado por Davi (agente dev VIRAXIS) — 08/06/2026*
