"""FastAPI app — VIRAXIS API."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from viraxis.api.routers import agent_run_logs, analytics, auth, billing, brain, content_items, dev, oauth, offices, raw_videos, social_accounts, users

_error_logger = logging.getLogger("viraxis.errors")

app = FastAPI(
    title="VIRAXIS API",
    version="0.3.0",
    description="Autonomous Viral Content Offices — API",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Exception handler global ──────────────────────────────────────────────────
#
# Sem isto, qualquer excecao nao tratada em qualquer endpoint (ex: um bug em
# um router, uma falha de rede inesperada num provider externo, um bug de
# lógica que a gente nao previu) caia no handler padrao do Starlette, que
# devolve "Internal Server Error" como TEXTO PURO (nao JSON — quebra clientes
# que esperam application/json) e SEM NENHUM LOG estruturado — o unico rastro
# fica no traceback bruto do processo, dificil de correlacionar com a request
# que o causou. Isto dificultava diagnostico em producao (Render logs viravam
# um mar de tracebacks sem contexto de qual rota/metodo falhou).
#
# Este handler:
#   1. Loga a excecao completa (stack trace) via logger.exception, prefixada
#      com metodo+path da request, para ficar facil de achar no Render.
#   2. Devolve JSON consistente com o resto da API (nunca texto puro), sem
#      vazar detalhes internos (stack trace, nomes de variaveis, queries SQL)
#      para o cliente — só o nome da classe da excecao, util para triagem sem
#      expor superficie de ataque.
#
# IMPORTANTE: `@app.exception_handler(Exception)` NAO sobrescreve o tratamento
# que o FastAPI ja faz para HTTPException/RequestValidationError — o Starlette
# resolve o handler mais especifico primeiro (percorre o MRO da excecao e usa
# o handler registrado mais proximo da classe concreta), entao HTTPException
# levantadas nos routers (404, 422, 401, etc.) continuam respondendo com o
# status_code e detail originais normalmente. Este handler só é acionado para
# excecoes que NINGUEM tratou explicitamente.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _error_logger.exception(
        "Excecao nao tratada | %s %s | %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__,
        },
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://viraxis.com",
        "https://viraxis.vercel.app",
        "https://viraxis-viraxis.vercel.app",
        "https://viraxis-git-main-viraxis.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# Routers
app.include_router(auth.router)
app.include_router(brain.router)
app.include_router(oauth.router)         # OAuth social platforms
app.include_router(raw_videos.router)
app.include_router(offices.router)
app.include_router(content_items.router)     # PR-1 Fase 2
app.include_router(agent_run_logs.router)    # PR-2 Fase 2
app.include_router(social_accounts.router)   # PR-5 Fase 2
app.include_router(billing.router)           # PR-8 Fase 2
app.include_router(users.router)
app.include_router(analytics.router)      # Dashboard de analytics
app.include_router(dev.router)



import asyncio
import logging

_startup_logger = logging.getLogger("viraxis.startup")

async def _recover_one(dec) -> None:
    """Executa o renderer para uma decisão presa, com tratamento de erro isolado."""
    try:
        from viraxis.agents.renderer.v2_direct import run_renderer_v2
        _startup_logger.info("Startup recovery: disparando renderer para decisão %s (%s)", dec.id, dec.selected_topic)
        await run_renderer_v2(
            office_id=dec.office_id,
            user_id=dec.user_id,
            decision_id=dec.id,
            extra_instructions=dec.extra_instructions,
        )
        _startup_logger.info("Startup recovery: decisão %s concluída", dec.id)
    except Exception as e:
        _startup_logger.error("Startup recovery: renderer falhou para %s — %s", dec.id, e, exc_info=True)


async def _recover_stuck_decisions() -> None:
    """Re-dispara decisões presas em 'approved' após restart do servidor."""
    await asyncio.sleep(8)  # aguarda DB connections estabilizarem
    try:
        from sqlalchemy import select
        from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus
        from viraxis.infrastructure.database.session import AsyncSessionLocal

        # Detecta decisões em "executing" sem content_item ativo (renderer nunca rodou ou crashou antes do item ser criado)
        from viraxis.domain.models.content_item import ContentItem, ContentStatus
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ContentDecision).where(
                    ContentDecision.status.in_([DecisionStatus.approved, DecisionStatus.executing])
                )
            )
            candidates = result.scalars().all()

        # Filtra apenas os que não têm item ativo em rendering/review/ready
        stuck = []
        async with AsyncSessionLocal() as session:
            for dec in candidates:
                item_result = await session.execute(
                    select(ContentItem).where(
                        ContentItem.decision_id == dec.id,
                        ContentItem.deleted_at.is_(None),
                        ContentItem.status.in_([ContentStatus.rendering, ContentStatus.review, ContentStatus.ready]),
                    ).limit(1)
                )
                if item_result.scalar_one_or_none() is None:
                    stuck.append(dec)

        if not stuck:
            _startup_logger.info("Startup recovery: nenhuma decisão presa.")
            return

        _startup_logger.warning("Startup recovery: %d decisão(ões) presas — re-disparando", len(stuck))
        await asyncio.gather(*[_recover_one(dec) for dec in stuck], return_exceptions=True)

    except Exception as e:
        _startup_logger.error("Startup recovery falhou: %s", e, exc_info=True)


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(_recover_stuck_decisions())

# Health
#
# Antes desta mudanca, /health devolvia {"status": "ok"} estatico — sem
# nenhuma checagem real de dependencia. O keep-alive (.github/workflows/
# keepalive.yml, a cada 10min) trata qualquer HTTP 200 como "servico vivo".
# Isso ja causou um incidente real: o projeto Supabase ficou INACTIVE
# (pausado por inatividade, resolve DNS como NXDOMAIN) e passou despercebido
# por um ciclo inteiro porque /health continuava respondendo 200 mesmo sem
# conseguir falar com o Storage.
#
# Este endpoint agora verifica de verdade:
#   1. Neon/Postgres — SELECT 1 via asyncpg direto (bypassa o pool do
#      SQLAlchemy de proposito: queremos detectar problema de conectividade
#      de rede/credencial, nao um pool exaurido por outra rota).
#   2. Supabase Storage — GET no endpoint de bucket via REST API.
# Se qualquer uma falhar, devolve status=degraded + HTTP 503 (em vez de 200),
# para que o keep-alive (ajustado nesta mesma mudanca) falhe o workflow e
# notifique. Timeout curto em cada checagem (5s) para não travar o health
# check nem o cold start do Render.
async def _check_database() -> dict:
    """SELECT 1 direto via asyncpg — não usa o pool do SQLAlchemy para não
    misturar sintomas (conexão exaurida por outra rota vs. banco fora do ar)."""
    import asyncio as _asyncio
    from urllib.parse import urlparse

    from viraxis.config import settings

    if not settings.database_url:
        return {"ok": False, "detail": "DATABASE_URL não configurada"}

    try:
        import asyncpg

        parsed = urlparse(settings.database_url)
        conn = await _asyncio.wait_for(
            asyncpg.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database=(parsed.path or "/neondb").lstrip("/"),
                ssl="require",
            ),
            timeout=5.0,
        )
        try:
            value = await _asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=5.0)
        finally:
            await conn.close()
        if value != 1:
            return {"ok": False, "detail": f"SELECT 1 retornou valor inesperado: {value!r}"}
        return {"ok": True}
    except _asyncio.TimeoutError:
        return {"ok": False, "detail": "Timeout ao conectar/consultar o Postgres (Neon)"}
    except Exception as e:  # noqa: BLE001 — health check precisa capturar QUALQUER falha
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


async def _check_storage() -> dict:
    """GET no bucket configurado do Supabase Storage via REST API."""
    from viraxis.config import settings

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {"ok": False, "detail": "SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY não configuradas"}

    try:
        import httpx

        url = f"{settings.supabase_url}/storage/v1/bucket/{settings.supabase_bucket}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return {"ok": True}
        return {"ok": False, "detail": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


@app.get("/health", tags=["infra"])
async def health() -> JSONResponse:
    db_check, storage_check = await asyncio.gather(
        _check_database(), _check_storage(), return_exceptions=False
    )

    checks = {"database": db_check, "storage": storage_check}
    healthy = db_check["ok"] and storage_check["ok"]

    if not healthy:
        _startup_logger.warning("Health check degradado: %s", checks)

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "service": "viraxis-api",
            "version": "0.3.0",
            "checks": checks,
        },
    )


@app.get("/content-items/ffmpeg-check", tags=["infra"])
async def ffmpeg_check() -> dict:
    """Diagnóstico: confirma se o binário FFmpeg está disponível no container.

    Usado para validar o ambiente de produção antes de rodar o pipeline de
    corte de vídeo (editing_plan → process-video), que depende do FFmpeg
    estar instalado no container Docker.
    """
    import shutil
    import subprocess

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return {"ffmpeg_available": False, "version": None, "path": None}

    version_str = None
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first_line = (result.stdout or result.stderr or "").splitlines()
        version_str = first_line[0] if first_line else None
    except Exception as e:  # noqa: BLE001
        return {
            "ffmpeg_available": False,
            "version": None,
            "path": ffmpeg_path,
            "error": f"{type(e).__name__}: {e}",
        }

    return {"ffmpeg_available": True, "version": version_str, "path": ffmpeg_path}
