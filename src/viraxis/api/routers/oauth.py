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
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_session
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.config import settings
from viraxis.domain.models.social_account import SocialAccount, SocialPlatform
from viraxis.infrastructure.repositories.social_account import SocialAccountRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["oauth"])

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Deriva chave Fernet de 32 bytes a partir do secret_key."""
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    import base64
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _encrypt_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode()).decode()


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
async def tiktok_connect(
    access_token: str = Query(...),
    office_id: str | None = Query(None),
):
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

    _step = "init"
    try:
        _step = "token_exchange"
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

            _step = "user_info"
            user_resp = await client.get(
                TIKTOK_USER_URL,
                params={"fields": "open_id,union_id,avatar_url,display_name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            logger.info("TikTok user info status=%s body=%s", user_resp.status_code, user_resp.text[:300])
            user_data = user_resp.json().get("data", {}).get("user", {})
            display_name = user_data.get("display_name", open_id or "tiktok_user")
        # ── DB save — retry loop para Neon cold-start ───────────────────────
        _step = "db_encrypt"
        access_enc = _encrypt_token(access_token)
        refresh_token_val = token_data.get("refresh_token", "")
        refresh_enc = _encrypt_token(refresh_token_val) if refresh_token_val else None
        expires_in = token_data.get("expires_in", 86400)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        _step = "db_connect"
        _db_saved = False
        for _attempt in range(4):  # até 4 tentativas com backoff
            try:
                async with AsyncSessionLocal() as db_sess:
                    _step = "db_query"
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
                    _step = "db_commit"
                    await db_sess.commit()
                _db_saved = True
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

        if not _db_saved:
            raise RuntimeError("DB save loop exited without saving")

        logger.info("TikTok conectado: user=%s open_id=%s", user_id, open_id)
        return _frontend_redirect("success", "tiktok", office_id=office_id)

    except Exception as exc:
        logger.exception("TikTok callback exception at step=%s: %s", _step, exc)
        return _frontend_redirect("error", "tiktok", f"@{_step}:{type(exc).__name__}:{str(exc)[:100]}", office_id)


# ─── Meta (Facebook / Instagram) ──────────────────────────────────────────────

META_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
META_ME_URL = "https://graph.facebook.com/v19.0/me"
META_IG_URL = "https://graph.facebook.com/v19.0/me/accounts"
META_SCOPES = (
    "public_profile,email,"
    "pages_show_list,pages_read_engagement,"
    "instagram_basic,instagram_content_publish"
)


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
    }
    return RedirectResponse(url=f"{META_AUTH_URL}?{urlencode(params)}")


@router.get("/meta/callback")
async def meta_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if error:
        return _frontend_redirect("error", "meta", error_description or error)

    state_data = _verify_state(state)
    user_id = state_data["sub"]
    office_id = state_data.get("office_id")

    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.get(META_TOKEN_URL, params={
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "redirect_uri": settings.meta_redirect_uri,
            "code": code,
        })
        if token_resp.status_code != 200:
            logger.error("Meta token exchange failed: %s", token_resp.text)
            return _frontend_redirect("error", "meta", "token_exchange_failed", office_id)

        tokens = token_resp.json()
        access_token = tokens["access_token"]

        me_resp = await client.get(
            META_ME_URL,
            params={"fields": "id,name,email", "access_token": access_token},
        )
        me = me_resp.json()
        fb_user_id = me.get("id", "")
        fb_name = me.get("name", "facebook_user")

    access_enc = _encrypt_token(access_token)
    expires_in = tokens.get("expires_in", 5183944)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    repo = SocialAccountRepository(session)
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
        session.add(account)

    await session.commit()
    logger.info("Meta conectado: user=%s fb_id=%s", user_id, fb_user_id)
    return _frontend_redirect("success", "facebook", office_id=office_id)
