"""OAuth callbacks — Google/YouTube, TikTok, Meta (Facebook/Instagram).

Fluxo:
  1. Frontend → GET /auth/{platform}/connect?access_token={jwt}&office_id={id}
  2. Backend  → redireciona para plataforma com state assinado
  3. Plataforma → GET /auth/{platform}/callback?code=...&state=...
  4. Backend  → troca code por tokens, salva SocialAccount, redireciona frontend
"""

import base64
import hashlib
import logging
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.config import settings
from viraxis.domain.models.social_account import SocialAccount, SocialPlatform
from viraxis.domain.models.user import User
from viraxis.infrastructure.repositories.social_account import SocialAccountRepository
from viraxis.infrastructure.token_crypto import encrypt_token as _encrypt_token
from viraxis.infrastructure.token_crypto import get_fernet as _get_fernet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["oauth"])

# ─── Helpers ──────────────────────────────────────────────────────────────────
# _encrypt_token / _get_fernet agora vivem em viraxis.infrastructure.token_crypto
# (compartilhado com agents/publisher/runner.py, que precisa DESCRIPTOGRAFAR
# com a mesma derivacao de chave usada aqui para criptografar).


def _create_state(user_id: str, office_id: str | None, code_verifier: str | None = None) -> str:
    """Cria state JWT de curta duração (10 min) para proteção CSRF."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload: dict = {"sub": user_id, "office_id": office_id, "nonce": secrets.token_hex(8), "exp": expire}
    if code_verifier:
        payload["cv"] = code_verifier
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _pkce_pair() -> tuple[str, str]:
    """Gera (code_verifier, code_challenge) para PKCE."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _verify_state(state: str) -> dict:
    try:
        return jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=400, detail="State OAuth inválido ou expirado")


def _verify_access_token(access_token: str) -> str:
    """Verifica JWT do usuário e retorna user_id."""
    try:
        payload = jwt.decode(access_token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token de acesso inválido")


def _frontend_redirect(status: str, platform: str, message: str = "", office_id: str | None = None) -> RedirectResponse:
    params: dict = {"platform": platform, "status": status}
    if message:
        params["message"] = message
    if office_id:
        params["office_id"] = office_id
    return RedirectResponse(url=f"{settings.frontend_url}/oauth/callback?{urlencode(params)}")


# ─── Google / YouTube ─────────────────────────────────────────────────────────

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


@router.get("/google/connect")
async def google_connect(
    access_token: str = Query(..., description="JWT do usuário autenticado"),
    office_id: str | None = Query(None),
):
    """Inicia fluxo OAuth Google. Frontend passa o JWT como query param."""
    user_id = _verify_access_token(access_token)
    state = _create_state(user_id, office_id)
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if error:
        return _frontend_redirect("error", "google", error)

    state_data = _verify_state(state)
    user_id = state_data["sub"]
    office_id = state_data.get("office_id")

    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            logger.error("Google token exchange failed: %s", token_resp.text)
            return _frontend_redirect("error", "google", "token_exchange_failed", office_id)

        tokens = token_resp.json()
        access_token = tokens["access_token"]

        # Buscar info do canal YouTube
        channel_resp = await client.get(
            GOOGLE_CHANNEL_URL,
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        channel_data = channel_resp.json()
        channels = channel_data.get("items", [])

        if channels:
            channel = channels[0]
            platform_user_id = channel["id"]
            platform_username = channel["snippet"]["title"]
        else:
            # Fallback: info do perfil Google
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info = userinfo_resp.json()
            platform_user_id = info.get("id", "")
            platform_username = info.get("name", info.get("email", "youtube_user"))

    access_enc = _encrypt_token(access_token)
    refresh_enc = _encrypt_token(tokens["refresh_token"]) if tokens.get("refresh_token") else None
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

    repo = SocialAccountRepository(session)
    existing = await repo.get_by_user_platform_username(
        UUID(user_id), SocialPlatform.youtube, platform_username
    )
    if existing:
        existing.access_token_enc = access_enc
        existing.refresh_token_enc = refresh_enc
        existing.token_expires_at = expires_at
        existing.is_active = True
        if office_id:
            existing.office_id = UUID(office_id)
        await repo.save(existing)
    else:
        account = SocialAccount(
            user_id=UUID(user_id),
            office_id=UUID(office_id) if office_id else None,
            platform=SocialPlatform.youtube,
            platform_username=platform_username,
            platform_user_id=platform_user_id,
            access_token_enc=access_enc,
            refresh_token_enc=refresh_enc,
            token_expires_at=expires_at,
            is_active=True,
        )
        session.add(account)

    await session.commit()
    logger.info("YouTube conectado: user=%s channel=%s", user_id, platform_username)
    return _frontend_redirect("success", "youtube", office_id=office_id)


# ─── TikTok ───────────────────────────────────────────────────────────────────

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_SCOPES = "user.info.basic,video.upload"


@router.get("/tiktok/connect")
@router.get("/tiktok/authorize")
async def tiktok_connect(
    access_token: str = Query(...),
    office_id: str | None = Query(None),
):
    """Inicia fluxo OAuth TikTok. Exposto em /tiktok/connect (padrão interno,
    espelha /google/connect) e /tiktok/authorize (alias esperado pelo frontend/Publisher).
    """
    user_id = _verify_access_token(access_token)
    # PKCE desabilitado temporariamente para diagnóstico de sandbox
    state = _create_state(user_id, office_id)
    params = {
        "client_key": settings.tiktok_client_key,
        "redirect_uri": settings.tiktok_redirect_uri,
        "response_type": "code",
        "scope": TIKTOK_SCOPES,
        "state": state,
    }
    return RedirectResponse(url=f"{TIKTOK_AUTH_URL}?{urlencode(params)}")


@router.get("/tiktok/status")
async def tiktok_status(
    office_id: str | None = Query(None, description="Filtra pela conta vinculada a este escritório"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna se o usuário autenticado tem uma conta TikTok conectada.

    Autenticação via Bearer JWT (Authorization header), igual aos demais
    endpoints protegidos da API (ex: /social-accounts). Não expõe tokens.
    """
    repo = SocialAccountRepository(session)
    accounts = await repo.list_by_user(
        current_user.id, platform=SocialPlatform.tiktok, active_only=True
    )

    if office_id:
        accounts = [a for a in accounts if str(a.office_id) == office_id]

    if not accounts:
        return {"connected": False, "platform": "tiktok", "account": None}

    # Usuário pode ter mais de uma conta TikTok vinculada (multi-office);
    # se office_id não for informado, retorna a mais recente.
    account = accounts[0]
    return {
        "connected": True,
        "platform": "tiktok",
        "account": {
            "id": str(account.id),
            "platform_username": account.platform_username,
            "platform_user_id": account.platform_user_id,
            "office_id": str(account.office_id) if account.office_id else None,
            "token_expires_at": (
                account.token_expires_at.isoformat() if account.token_expires_at else None
            ),
            "is_active": account.is_active,
        },
    }


@router.get("/tiktok/callback")
async def tiktok_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if error:
        return _frontend_redirect("error", "tiktok", error_description or error)

    state_data = _verify_state(state)
    user_id = state_data["sub"]
    office_id = state_data.get("office_id")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": settings.tiktok_client_key,
                    "client_secret": settings.tiktok_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.tiktok_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            logger.info("TikTok token exchange status=%s body=%s", token_resp.status_code, token_resp.text[:500])
            if token_resp.status_code != 200:
                logger.error("TikTok token exchange failed: %s", token_resp.text)
                return _frontend_redirect("error", "tiktok", "token_exchange_failed", office_id)

            resp_json = token_resp.json()
            # TikTok sandbox retorna formato FLAT: {"error":"invalid_grant","error_description":"..."}
            # (não o formato aninhado {"data":{}, "error":{"code":"ok"}})
            error_val = resp_json.get("error")
            if error_val and isinstance(error_val, str) and error_val != "ok":
                err_msg = resp_json.get("error_description") or error_val
                logger.error("TikTok token error (flat): error=%s msg=%s", error_val, err_msg)
                return _frontend_redirect("error", "tiktok", err_msg, office_id)
            elif isinstance(error_val, dict) and error_val.get("code", "ok") != "ok":
                err_msg = error_val.get("message", "token_exchange_failed")
                logger.error("TikTok token error (nested): %s", resp_json)
                return _frontend_redirect("error", "tiktok", err_msg, office_id)

            token_data = resp_json.get("data", resp_json)
            if "access_token" not in token_data:
                logger.error("TikTok no access_token in response: %s", resp_json)
                return _frontend_redirect("error", "tiktok", "no_access_token", office_id)

            access_token = token_data["access_token"]
            open_id = token_data.get("open_id", "")
            user_resp = await client.get(
                TIKTOK_USER_URL,
                params={"fields": "open_id,union_id,avatar_url,display_name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            logger.info("TikTok user info status=%s body=%s", user_resp.status_code, user_resp.text[:300])
            user_data = user_resp.json().get("data", {}).get("user", {})
            display_name = user_data.get("display_name", open_id or "tiktok_user")
        # ── DB save — retry loop para Neon cold-start ───────────────────────
        access_enc = _encrypt_token(access_token)
        refresh_token_val = token_data.get("refresh_token", "")
        refresh_enc = _encrypt_token(refresh_token_val) if refresh_token_val else None
        expires_in = token_data.get("expires_in", 86400)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        for _attempt in range(4):  # até 4 tentativas com backoff
            try:
                async with AsyncSessionLocal() as db_sess:
                    repo = SocialAccountRepository(db_sess)
                    existing = await repo.get_by_user_platform_username(
                        UUID(user_id), SocialPlatform.tiktok, display_name
                    )
                    if existing:
                        existing.access_token_enc = access_enc
                        existing.refresh_token_enc = refresh_enc
                        existing.token_expires_at = expires_at
                        existing.is_active = True
                        if office_id:
                            existing.office_id = UUID(office_id)
                        await repo.save(existing)
                    else:
                        account = SocialAccount(
                            user_id=UUID(user_id),
                            office_id=UUID(office_id) if office_id else None,
                            platform=SocialPlatform.tiktok,
                            platform_username=display_name,
                            platform_user_id=open_id,
                            access_token_enc=access_enc,
                            refresh_token_enc=refresh_enc,
                            token_expires_at=expires_at,
                            is_active=True,
                        )
                        db_sess.add(account)
                    await db_sess.commit()
                    break
            except (ConnectionRefusedError, OSError) as _ce:
                wait = 2 ** _attempt  # 1, 2, 4, 8 segundos
                logger.warning(
                    "Neon cold-start attempt %d/4: %s — aguardando %ds",
                    _attempt + 1, _ce, wait,
                )
                if _attempt >= 3:
                    raise
                await asyncio.sleep(wait)

        logger.info("TikTok conectado: user=%s open_id=%s", user_id, open_id)
        return _frontend_redirect("success", "tiktok", office_id=office_id)

    except Exception as exc:
        logger.exception("TikTok callback exception: %s", exc)
        return _frontend_redirect("error", "tiktok", "internal_error", office_id)


# ─── Instagram Business (fluxo dedicado) ──────────────────────────────────────
#
# Descobre a Instagram Business Account vinculada a uma Page do Facebook do
# usuario e salva como SocialAccount(platform="instagram"). Compartilha as
# credenciais do app Meta (META_APP_ID / META_APP_SECRET) mas usa uma
# redirect_uri e escopos proprios, espelhando o padrao do fluxo TikTok
# (rotas /connect + /authorize, /status, /callback).

INSTAGRAM_SCOPES = (
    "instagram_basic,instagram_content_publish,"
    "pages_read_engagement,pages_show_list"
)
INSTAGRAM_GRAPH_BASE = "https://graph.facebook.com/v19.0"


@router.get("/instagram/connect")
@router.get("/instagram/authorize")
async def instagram_connect(
    access_token: str = Query(..., description="JWT do usuário autenticado"),
    office_id: str | None = Query(None),
):
    """Inicia fluxo OAuth Instagram Business. Exposto em /instagram/connect
    (padrão interno, espelha /tiktok/connect) e /instagram/authorize (alias
    esperado pelo frontend/Publisher, igual TikTok).
    """
    user_id = _verify_access_token(access_token)
    state = _create_state(user_id, office_id)
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.instagram_redirect_uri,
        "response_type": "code",
        "scope": INSTAGRAM_SCOPES,
        "state": state,
        "auth_type": "rerequest",  # força novo consentimento a cada tentativa
    }
    return RedirectResponse(url=f"{META_AUTH_URL}?{urlencode(params)}")


@router.get("/instagram/status")
async def instagram_status(
    office_id: str | None = Query(None, description="Filtra pela conta vinculada a este escritório"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna se o usuário autenticado tem uma Instagram Business Account
    conectada. Autenticação via Bearer JWT (igual /tiktok/status).
    """
    repo = SocialAccountRepository(session)
    accounts = await repo.list_by_user(
        current_user.id, platform=SocialPlatform.instagram, active_only=True
    )

    if office_id:
        accounts = [a for a in accounts if str(a.office_id) == office_id]

    if not accounts:
        return {"connected": False, "platform": "instagram", "account": None}

    account = accounts[0]
    return {
        "connected": True,
        "platform": "instagram",
        "account": {
            "id": str(account.id),
            "platform_username": account.platform_username,
            "platform_user_id": account.platform_user_id,
            "office_id": str(account.office_id) if account.office_id else None,
            "token_expires_at": (
                account.token_expires_at.isoformat() if account.token_expires_at else None
            ),
            "is_active": account.is_active,
        },
    }


@router.get("/instagram/callback")
async def instagram_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    """Troca `code` por access_token, descobre a Page do Facebook do usuário
    e a Instagram Business Account vinculada a ela, e salva o resultado como
    SocialAccount(platform="instagram") com token Fernet-criptografado.

    Fluxo Graph API:
      1. Troca code -> user access_token (curto prazo)
      2. Troca user access_token curto -> longo prazo (~60 dias, fb_exchange_token)
      3. GET /me/accounts com o token longo -> lista de Pages + seus
         Page Access Tokens (também de longa duração, pois derivados de um
         user token longo) + campo instagram_business_account expandido
      4. Escolhe a primeira Page com instagram_business_account vinculada
      5. GET /{ig-user-id}?fields=username para obter o @ da conta
      6. Salva SocialAccount com platform_user_id=ig-user-id e o Page Access
         Token (é ele que autoriza publicação via /{ig-user-id}/media)
    """
    if error:
        return _frontend_redirect("error", "instagram", error_description or error)

    state_data = _verify_state(state)
    user_id = state_data["sub"]
    office_id = state_data.get("office_id")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # ---- 1. code -> user access_token (curto prazo) ----
            token_resp = await client.get(META_TOKEN_URL, params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.instagram_redirect_uri,
                "code": code,
            })
            if token_resp.status_code != 200:
                logger.error(
                    "Instagram token exchange failed %d: %s",
                    token_resp.status_code, token_resp.text[:500],
                )
                return _frontend_redirect("error", "instagram", "token_exchange_failed", office_id)

            tokens = token_resp.json()
            if "error" in tokens:
                err = tokens["error"]
                err_msg = err.get("message", "token_exchange_failed") if isinstance(err, dict) else str(err)
                logger.error("Instagram token error: %s", tokens)
                return _frontend_redirect("error", "instagram", err_msg, office_id)

            short_lived_token = tokens.get("access_token")
            if not short_lived_token:
                logger.error("Instagram: sem access_token na resposta: %s", tokens)
                return _frontend_redirect("error", "instagram", "no_access_token", office_id)

            # ---- 2. curto prazo -> longo prazo (~60 dias) ----
            user_access_token = short_lived_token
            expires_in = tokens.get("expires_in", 5183944)  # ~60 dias fallback
            long_resp = await client.get(META_TOKEN_URL, params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "fb_exchange_token": short_lived_token,
            })
            if long_resp.status_code == 200:
                long_data = long_resp.json()
                if long_data.get("access_token"):
                    user_access_token = long_data["access_token"]
                    expires_in = long_data.get("expires_in", expires_in)
            else:
                logger.warning(
                    "Instagram: falha ao trocar por token de longa duração (%d): %s — usando token curto",
                    long_resp.status_code, long_resp.text[:300],
                )

            # ---- 3. Pages do usuário + IG Business Account vinculada ----
            pages_resp = await client.get(META_IG_URL, params={
                "fields": "id,name,access_token,instagram_business_account",
                "access_token": user_access_token,
            })
            if pages_resp.status_code != 200:
                logger.error(
                    "Instagram: falha ao buscar Pages (%d): %s",
                    pages_resp.status_code, pages_resp.text[:500],
                )
                return _frontend_redirect("error", "instagram", "pages_fetch_failed", office_id)

            pages_data = pages_resp.json().get("data", [])
            if not pages_data:
                logger.warning("Instagram: usuário %s não possui Pages do Facebook", user_id)
                return _frontend_redirect("error", "instagram", "no_facebook_pages", office_id)

            # ---- 4. Primeira Page com Instagram Business Account ----
            ig_account_id: str | None = None
            page_access_token: str | None = None
            page_name = ""
            for page in pages_data:
                ig_biz = page.get("instagram_business_account")
                if ig_biz and ig_biz.get("id"):
                    ig_account_id = ig_biz["id"]
                    page_access_token = page.get("access_token") or user_access_token
                    page_name = page.get("name", "")
                    break

            if not ig_account_id or not page_access_token:
                logger.warning(
                    "Instagram: nenhuma Page com IG Business Account vinculada para user=%s (pages=%d)",
                    user_id, len(pages_data),
                )
                return _frontend_redirect("error", "instagram", "no_instagram_business_account", office_id)

            # ---- 5. Detalhes da conta Instagram (@username) ----
            ig_username = f"ig_{ig_account_id}"
            ig_info_resp = await client.get(
                f"{INSTAGRAM_GRAPH_BASE}/{ig_account_id}",
                params={"fields": "id,username,profile_picture_url", "access_token": page_access_token},
            )
            if ig_info_resp.status_code == 200:
                ig_info = ig_info_resp.json()
                ig_username = ig_info.get("username", ig_username)
            else:
                logger.warning(
                    "Instagram: falha ao buscar detalhes da conta %s (%d): %s",
                    ig_account_id, ig_info_resp.status_code, ig_info_resp.text[:300],
                )

        # ---- 6. Persistir SocialAccount (com retry para Neon cold-start) ----
        access_enc = _encrypt_token(page_access_token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        for _attempt in range(4):
            try:
                async with AsyncSessionLocal() as db_sess:
                    repo = SocialAccountRepository(db_sess)
                    existing = await repo.get_by_user_platform_username(
                        UUID(user_id), SocialPlatform.instagram, ig_username
                    )
                    if existing:
                        existing.access_token_enc = access_enc
                        existing.platform_user_id = ig_account_id
                        existing.token_expires_at = expires_at
                        existing.is_active = True
                        if office_id:
                            existing.office_id = UUID(office_id)
                        await repo.save(existing)
                    else:
                        account = SocialAccount(
                            user_id=UUID(user_id),
                            office_id=UUID(office_id) if office_id else None,
                            platform=SocialPlatform.instagram,
                            platform_username=ig_username,
                            platform_user_id=ig_account_id,
                            access_token_enc=access_enc,
                            refresh_token_enc=None,
                            token_expires_at=expires_at,
                            is_active=True,
                        )
                        db_sess.add(account)
                    await db_sess.commit()
                break
            except (ConnectionRefusedError, OSError) as _ce:
                wait = 2 ** _attempt
                logger.warning(
                    "Instagram Neon cold-start attempt %d/4: %s — aguardando %ds",
                    _attempt + 1, _ce, wait,
                )
                if _attempt >= 3:
                    raise
                await asyncio.sleep(wait)

        logger.info(
            "Instagram conectado: user=%s ig_account=%s username=%s page=%s",
            user_id, ig_account_id, ig_username, page_name,
        )
        return _frontend_redirect("success", "instagram", office_id=office_id)

    except Exception as exc:
        logger.exception("Instagram callback exception: %s", exc)
        return _frontend_redirect("error", "instagram", "internal_error", office_id)


# ─── Meta (Facebook / Instagram) ──────────────────────────────────────────────

META_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
META_ME_URL = "https://graph.facebook.com/v19.0/me"
META_IG_URL = "https://graph.facebook.com/v19.0/me/accounts"
META_SCOPES = "public_profile,email"
# NOTE: When Meta app is approved, expand to:
# "public_profile,email,pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish"


@router.get("/meta/connect")
async def meta_connect(
    access_token: str = Query(...),
    office_id: str | None = Query(None),
):
    user_id = _verify_access_token(access_token)
    state = _create_state(user_id, office_id)
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "response_type": "code",
        "scope": META_SCOPES,
        "state": state,
        "auth_type": "rerequest",  # force fresh code each time
    }
    return RedirectResponse(url=f"{META_AUTH_URL}?{urlencode(params)}")


@router.get("/meta/callback")
async def meta_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    if error:
        return _frontend_redirect("error", "meta", error_description or error)

    state_data = _verify_state(state)
    user_id = state_data["sub"]
    office_id = state_data.get("office_id")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.get(META_TOKEN_URL, params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.meta_redirect_uri,
                "code": code,
            })
            if token_resp.status_code != 200:
                logger.error("Meta token exchange failed %d: %s", token_resp.status_code, token_resp.text)
                return _frontend_redirect("error", "meta", "token_exchange_failed", office_id)

            tokens = token_resp.json()
            if "error" in tokens:
                err = tokens["error"]
                err_msg = err.get("message", "token_exchange_failed") if isinstance(err, dict) else str(err)
                logger.error("Meta token error: %s", tokens)
                return _frontend_redirect("error", "meta", err_msg, office_id)

            access_token = tokens["access_token"]

            me_resp = await client.get(
                META_ME_URL,
                params={"fields": "id,name,email", "access_token": access_token},
            )
            me = me_resp.json()
            logger.info("Meta me status=%s body=%s", me_resp.status_code, me_resp.text[:300])
            fb_user_id = me.get("id", "")
            fb_name = me.get("name", "facebook_user")

        access_enc = _encrypt_token(access_token)
        expires_in = tokens.get("expires_in", 5183944)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        for _attempt in range(4):
            try:
                async with AsyncSessionLocal() as db_sess:
                    repo = SocialAccountRepository(db_sess)
                    existing = await repo.get_by_user_platform_username(
                        UUID(user_id), SocialPlatform.facebook, fb_name
                    )
                    if existing:
                        existing.access_token_enc = access_enc
                        existing.token_expires_at = expires_at
                        existing.is_active = True
                        if office_id:
                            existing.office_id = UUID(office_id)
                        await repo.save(existing)
                    else:
                        account = SocialAccount(
                            user_id=UUID(user_id),
                            office_id=UUID(office_id) if office_id else None,
                            platform=SocialPlatform.facebook,
                            platform_username=fb_name,
                            platform_user_id=fb_user_id,
                            access_token_enc=access_enc,
                            refresh_token_enc=None,
                            token_expires_at=expires_at,
                            is_active=True,
                        )
                        db_sess.add(account)
                    await db_sess.commit()
                break
            except (ConnectionRefusedError, OSError) as _ce:
                wait = 2 ** _attempt
                logger.warning("Meta Neon cold-start attempt %d/4: %s — retrying in %ds", _attempt + 1, _ce, wait)
                if _attempt >= 3:
                    raise
                await asyncio.sleep(wait)

        logger.info("Meta conectado: user=%s fb_id=%s", user_id, fb_user_id)
        return _frontend_redirect("success", "facebook", office_id=office_id)

    except Exception as exc:
        logger.exception("Meta callback exception: %s", exc)
        return _frontend_redirect("error", "meta", "internal_error", office_id)
