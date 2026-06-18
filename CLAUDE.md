# VIRAXIS — Guia para o Claude

Plataforma autônoma de produção de conteúdo viral. O sistema usa agentes de IA (CrewAI) para identificar tendências, gerar roteiros e publicar vídeos em redes sociais, operando dentro de "escritórios virtuais" multi-tenant.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 async + Alembic (PostgreSQL)
- **Agentes**: CrewAI com LiteLLM (Groq/OpenAI/Gemini via `LLM_MODEL` env var)
- **Queue**: Celery + Redis (worker + beat)
- **Auth**: JWT (python-jose) + bcrypt
- **Storage**: Cloudflare R2 (opcional no dev)
- **Billing**: Stripe (checkout, portal, webhook)
- **Infra**: Docker Compose, GitHub Actions CI/CD

## Estrutura do projeto

```
src/viraxis/
├── agents/
│   ├── brain/        # Agente estratégico — analisa nicho e decide próximo vídeo
│   ├── scout/        # Agente de pesquisa — analisa vídeos virais (yt-dlp)
│   ├── renderer/     # Agente criativo — gera roteiro estruturado (4 seções)
│   └── publisher/    # Agente de publicação — posta nas redes sociais
├── api/
│   └── routers/      # auth, offices, content_items, billing, social_accounts, users
├── domain/models/    # SQLAlchemy ORM: User, Office, NicheProfile, ContentDecision,
│                     #   ContentItem, TrendSnapshot, SocialAccount, AgentRunLog
├── infrastructure/
│   ├── repositories/ # BaseRepository[T] genérico + repos específicos
│   └── ytdlp_client.py
├── worker/           # celery_app.py + tasks.py (run_brain/scout/renderer/publisher)
└── config.py         # Settings Pydantic v2 com alias de env vars
```

## Convenções obrigatórias

**Multi-tenant**: toda query filtra por `office_id` + `user_id`. Nunca retornar dados de outro tenant.

**Soft delete**: usar `deleted_at: Mapped[datetime | None]`. Nunca `DELETE` em produção.

**Repositories**: sempre herdar de `BaseRepository[T]`. Nunca executar SQL raw nos routers.

**Agentes async**: runners usam `asyncio.to_thread(_run_crew_sync)` — CrewAI é síncrono, a API é async.

**AgentRunLog**: todo runner cria `AgentRunLog.create_running()` antes, `mark_success/mark_failed` no finally.

**Tokens OAuth**: sempre criptografados com Fernet (`cryptography`). Nunca retornar em respostas da API.

**Escrita de arquivos**: usar bash `cat >` ou Python `open(..., encoding='utf-8')` para arquivos grandes — o Edit tool pode truncar.

## Modelos principais

```python
User          → plano (free/pro/business), stripe_customer_id
Office        → escritório virtual, pertence a User
NicheProfile  → nicho do canal (brain_params, content_style, target_audience)
ContentDecision → decisão do BRAIN (pending → approved → executing → done)
ContentItem   → roteiro gerado pelo RENDERER (draft → ready → published)
TrendSnapshot → análise do SCOUT (vídeo viral + processed_signals JSON)
SocialAccount → conta de rede social com token Fernet criptografado
AgentRunLog   → log de execução de qualquer agente (running → success/failed)
```

## Pipeline de conteúdo

```
SCOUT analisa vídeo viral
    → TrendSnapshot salvo
    ↓
BRAIN analisa NicheProfile + TrendSnapshots
    → ContentDecision criada (status=pending)
    ↓
[Aprovação manual ou automática]
    ↓
RENDERER gera roteiro a partir da ContentDecision
    → ContentItem criado (status=draft)
    ↓
PUBLISHER posta nas redes sociais via SocialAccount
    → ContentItem.status = published
    → ContentDecision.status = done
```

## Celery tasks

Cada agente tem uma task correspondente em `worker/tasks.py`:
- `run_brain_task(office_id, user_id, temperature)`
- `run_scout_task(office_id, user_id, url)`
- `run_renderer_task(office_id, user_id, decision_id, temperature)`
- `run_publisher_task(office_id, user_id, content_item_id, targets)`
- `cleanup_agent_logs_task()` — Beat, diariamente às 3h

Imports dos runners são **lazy** (dentro da função) para evitar falha no start do Celery.

## Variáveis de ambiente críticas

```bash
DATABASE_URL          # postgresql+asyncpg://... (ou POSTGRES_* separados)
REDIS_URL             # redis://redis:6379/0
SECRET_KEY            # 64 chars hex aleatório
LLM_API_KEY           # gsk_... (Groq) ou sk-... (OpenAI)
LLM_MODEL             # groq/llama-3.3-70b-versatile
STRIPE_SECRET_KEY     # sk_test_... (deixar vazio desabilita billing)
```

## Migrations Alembic

```
0001_initial_schema        → tabelas base (users, offices, niche_profiles, etc.)
0002_add_user_role         → campo role em users
0003_content_items_fase2   → content_items, performance_metrics, soft delete
0004_add_stripe_fields     → stripe_customer_id, subscription_id, status, plan_expires_at
```

Rodar com: `alembic upgrade head`

## Status do projeto

**Sprint 1 Fase 2 — COMPLETO** (todos os 8 PRs merged em main)

Próximos passos (Sprint 2):
- Frontend Next.js / React
- Integrações reais de publicação (TikTok API, Instagram Graph API)
- Dashboard de analytics
- Testes automatizados (pytest + httpx)

## Como rodar localmente (Codespaces ou Docker)

```bash
# 1. Copiar env
cp .env.example .env
# editar .env: adicionar LLM_API_KEY

# 2. Subir infraestrutura
docker compose up -d postgres redis

# 3. Migrations
PYTHONPATH=src alembic upgrade head

# 4. API
PYTHONPATH=src uvicorn viraxis.api.main:app --reload --port 8000

# 5. Worker (terminal separado)
PYTHONPATH=src celery -A viraxis.worker.celery_app worker -Q viraxis -l info -c 2
```

Docs: http://localhost:8000/docs

## Aliases no Codespace (após post-create.sh)

```bash
vx-api      → inicia a API com reload
vx-worker   → inicia o Celery worker
vx-db       → abre psql
vx-migrate  → roda alembic upgrade head
vx-logs     → docker compose logs -f
```
