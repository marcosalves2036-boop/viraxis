"""Rate limiting por `user_id` (multi-tenant) — slowapi.

Contexto (BACKLOG P1 "Hardening de produção"): nenhum endpoint da API tinha
limite de requisições. Os endpoints mais caros — BRAIN/RENDERER (LLM via
Groq), análise de vídeo (Gemini/Whisper), corte de vídeo (FFmpeg) — podiam
ser chamados sem nenhum freio: um double-click no frontend, um retry
malfeito no cliente, ou abuso deliberado disparavam custo real de API
externa ou CPU pesada no processo repetidamente, sem qualquer proteção.

Por que por `user_id` e não por IP: o sistema é multi-tenant atrás de um
único domínio (`viraxis.onrender.com`). Vários usuários legítimos podem
compartilhar IP (rede corporativa, CGNAT, VPN corporativa) — limitar por IP
puniria usuários inocentes pelo comportamento de outro. E um único usuário
malicioso troca de IP com trivialidade. `user_id` vem do mesmo JWT que já
autentica cada request (`decode_token`, o mesmo usado por
`api.deps.get_current_user`) — decodificado aqui de forma síncrona e sem
bater no banco, só para extrair a chave do limite. Cai para IP quando não
há um Bearer token válido (ex: token ausente/expirado/malformado) — nesse
caso a request de qualquer forma não vai passar de `get_current_user`.

Armazenamento: em memória (`limits`' `MemoryStorage`, padrão do slowapi).
O serviço roda como processo único no Render (`uvicorn` sem `--workers`,
ver `Dockerfile`/`render.yaml`) — não há necessidade de compartilhar o
contador entre processos hoje. Se o serviço um dia escalar para múltiplas
réplicas/workers, trocar para `storage_uri=settings.redis_url` (Redis já é
dependência do projeto — hoje presente no `pyproject.toml` mas não
utilizado em produção, ver `docker-compose.yml`) para que o contador seja
compartilhado entre instâncias.
"""

import logging

from fastapi import Request
from jose import JWTError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from viraxis.api.security import decode_token

logger = logging.getLogger("viraxis.rate_limit")


def user_or_ip_key(request: Request) -> str:
    """Chave do rate limit: `user:<user_id>` quando há um Bearer JWT válido
    no header `Authorization`, senão `ip:<remote_addr>`.

    Deliberadamente não usa `Depends(get_current_user)` — isso exigiria uma
    consulta ao banco (`UserRepository.get`) só para calcular a chave do
    limite, antes mesmo de sabermos se a request vai ser processada. O
    `sub` do JWT já é o identificador estável do usuário; não precisamos
    validar que a conta ainda existe/está ativa para fins de rate limit
    (isso já é responsabilidade de `get_current_user` na dependency chain
    normal do endpoint).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        if token:
            try:
                user_id = decode_token(token)
                return f"user:{user_id}"
            except JWTError:
                pass
    return f"ip:{get_remote_address(request)}"


# Limiter global da aplicação.
#
# `headers_enabled=False` (deliberado): a injeção automática de headers do
# slowapi (`X-RateLimit-*`) espera receber o objeto `Response` real que o
# FastAPI passaria via `response: Response = Depends(...)` — mas nossos
# endpoints devolvem Pydantic models (`response_model=...`), não
# `starlette.responses.Response` diretamente. Com `headers_enabled=True` o
# slowapi tenta injetar headers nesse retorno em TODA resposta de sucesso e
# lança `Exception("parameter response must be an instance of ...")`,
# quebrando o endpoint inteiro — confirmado experimentalmente (suite de
# testes quebrava em `TestProcessVideoEndpoint` e `TestReanalyzeEndpoint`
# assim que os decorators foram adicionados). Desligamos a injeção
# automática e calculamos o `Retry-After` manualmente, só no caminho 429
# (abaixo), onde nós mesmos controlamos o objeto `Response`.
limiter = Limiter(key_func=user_or_ip_key, headers_enabled=False)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 com corpo JSON no mesmo formato do resto da API (`detail`/`type`)
    e header `Retry-After`, para que o frontend (ARTHUR) saiba quanto tempo
    esperar antes de tentar de novo, em vez de martelar o endpoint."""
    key = user_or_ip_key(request)
    logger.warning(
        "Rate limit excedido | %s %s | chave=%s | limite=%s",
        request.method,
        request.url.path,
        key,
        exc.detail,
    )

    retry_after_seconds = 60
    view_rate_limit = getattr(request.state, "view_rate_limit", None)
    if view_rate_limit is not None:
        try:
            import time as _time

            rate_limit_item, identifiers = view_rate_limit
            window_reset_at, _remaining = limiter.limiter.get_window_stats(
                rate_limit_item, *identifiers
            )
            retry_after_seconds = max(1, int(window_reset_at - _time.time()) + 1)
        except Exception:  # noqa: BLE001 — nunca deixar o cálculo do header derrubar a resposta 429
            logger.warning("Falha ao calcular Retry-After exato — usando fallback de 60s", exc_info=True)

    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Limite de requisições excedido. Tente novamente em instantes.",
            "type": "RateLimitExceeded",
            "limit": exc.detail,
            "retry_after_seconds": retry_after_seconds,
        },
        headers={"Retry-After": str(retry_after_seconds)},
    )
    return response
