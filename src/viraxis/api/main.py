"""FastAPI app — VIRAXIS API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from viraxis.api.routers import agent_run_logs, auth, billing, content_items, dev, oauth, offices, raw_videos, social_accounts, users

app = FastAPI(
    title="VIRAXIS API",
    version="0.3.0",
    description="Autonomous Viral Content Offices — API",
    docs_url="/docs",
    redoc_url="/redoc",
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
app.include_router(oauth.router)         # OAuth social platforms
app.include_router(raw_videos.router)
app.include_router(offices.router)
app.include_router(content_items.router)     # PR-1 Fase 2
app.include_router(agent_run_logs.router)    # PR-2 Fase 2
app.include_router(social_accounts.router)   # PR-5 Fase 2
app.include_router(billing.router)           # PR-8 Fase 2
app.include_router(users.router)
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
@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "service": "viraxis-api", "version": "0.3.0"}


@app.get("/health/db", tags=["infra"])
async def health_db() -> dict:
    """Testa conectividade TCP + asyncpg com o Neon DB."""
    import asyncio, socket
    from viraxis.config import settings

    # Extrai host/porta da DATABASE_URL
    from urllib.parse import urlparse
    parsed = urlparse(settings.database_url)
    host = parsed.hostname or "unknown"
    port = parsed.port or 5432

    # 1. TCP raw
    tcp_ok = False
    tcp_err = ""
    try:
        loop = asyncio.get_event_loop()
        def _tcp():
            s = socket.create_connection((host, port), timeout=5)
            s.close()
            return True
        tcp_ok = await loop.run_in_executor(None, _tcp)
    except Exception as e:
        tcp_err = f"{type(e).__name__}: {e}"

    # 2. asyncpg
    pg_ok = False
    pg_err = ""
    try:
        import asyncpg
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=host, port=port,
                user=parsed.username, password=parsed.password,
                database=(parsed.path or "/neondb").lstrip("/"),
                ssl="require",
            ),
            timeout=8,
        )
        await conn.fetchval("SELECT 1")
        await conn.close()
        pg_ok = True
    except Exception as e:
        pg_err = f"{type(e).__name__}: {e}"

    return {
        "host": host, "port": port,
        "tcp": "ok" if tcp_ok else f"FAIL: {tcp_err}",
        "asyncpg": "ok" if pg_ok else f"FAIL: {pg_err}",
    }
