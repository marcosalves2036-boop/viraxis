"""FastAPI app — VIRAXIS API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from viraxis.api.routers import agent_run_logs, auth, billing, content_items, dev, offices, social_accounts, users

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
app.include_router(offices.router)
app.include_router(content_items.router)     # PR-1 Fase 2
app.include_router(agent_run_logs.router)    # PR-2 Fase 2
app.include_router(social_accounts.router)   # PR-5 Fase 2
app.include_router(billing.router)           # PR-8 Fase 2
app.include_router(users.router)
app.include_router(dev.router)


# Health
@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "service": "viraxis-api", "version": "0.3.0"}
