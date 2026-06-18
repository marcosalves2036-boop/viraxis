"""Clientes de publicacao por plataforma — PR-7 Fase 2.

Sprint 1: stubs que simulam publicacao. Retornam sucesso com external_id fake.
Sprint 3: implementacao real via APIs oficiais (TikTok Content Posting API, etc.)

Design:
  - Cada funcao recebe o token descriptografado (plaintext) — a descriptografia
    acontece no runner antes de chamar os clientes.
  - Retornam (external_id, url) ou lancam PublishPlatformError.
  - Sem estado — funcoes puras para facilitar testes.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


class PublishPlatformError(Exception):
    """Erro ao publicar em uma plataforma especifica."""


# ── TikTok ─────────────────────────────────────────────────────────────────────

def publish_to_tiktok(
    access_token: str,
    video_path: str | None,
    caption: str,
    hashtags: list[str],
) -> tuple[str, str]:
    """Publica video no TikTok via Content Posting API.

    Sprint 1: stub.
    Sprint 3: POST https://open.tiktokapis.com/v2/post/publish/video/init/

    Returns:
        (external_id, url)
    """
    logger.info("TikTok publish stub | caption=%.60s | hashtags=%s", caption, hashtags)
    ext_id = f"tiktok_stub_{uuid.uuid4().hex[:12]}"
    return ext_id, f"https://www.tiktok.com/@viraxis/video/{ext_id}"


# ── Instagram ──────────────────────────────────────────────────────────────────

def publish_to_instagram(
    access_token: str,
    video_path: str | None,
    caption: str,
    hashtags: list[str],
) -> tuple[str, str]:
    """Publica Reel no Instagram via Graph API.

    Sprint 1: stub.
    Sprint 3: POST https://graph.facebook.com/v19.0/{ig-user-id}/media
              seguido de POST .../media_publish

    Returns:
        (external_id, url)
    """
    logger.info("Instagram publish stub | caption=%.60s | hashtags=%s", caption, hashtags)
    ext_id = f"ig_stub_{uuid.uuid4().hex[:12]}"
    return ext_id, f"https://www.instagram.com/reel/{ext_id}/"


# ── YouTube ────────────────────────────────────────────────────────────────────

def publish_to_youtube(
    access_token: str,
    video_path: str | None,
    title: str,
    description: str,
    hashtags: list[str],
) -> tuple[str, str]:
    """Publica Short no YouTube via Data API v3.

    Sprint 1: stub.
    Sprint 3: POST https://www.googleapis.com/upload/youtube/v3/videos

    Returns:
        (external_id, url)
    """
    logger.info("YouTube publish stub | title=%.60s | hashtags=%s", title, hashtags)
    ext_id = f"yt_stub_{uuid.uuid4().hex[:12]}"
    return ext_id, f"https://www.youtube.com/shorts/{ext_id}"


# ── Kwai ───────────────────────────────────────────────────────────────────────

def publish_to_kwai(
    access_token: str,
    video_path: str | None,
    caption: str,
    hashtags: list[str],
) -> tuple[str, str]:
    """Publica video no Kwai via Kwai Creator API.

    Sprint 1: stub.
    Sprint 3: implementar via Kwai for Developers.

    Returns:
        (external_id, url)
    """
    logger.info("Kwai publish stub | caption=%.60s | hashtags=%s", caption, hashtags)
    ext_id = f"kwai_stub_{uuid.uuid4().hex[:12]}"
    return ext_id, f"https://www.kwai.com/short-video/{ext_id}"


# ── Dispatcher ─────────────────────────────────────────────────────────────────

def publish_to_platform(
    platform: str,
    access_token: str,
    video_path: str | None,
    title: str,
    caption: str,
    hashtags: list[str],
) -> tuple[str, str]:
    """Despacha a publicacao para o cliente correto da plataforma.

    Returns:
        (external_id, url)

    Raises:
        PublishPlatformError: Plataforma nao suportada ou falha na API.
    """
    dispatch = {
        "tiktok": lambda: publish_to_tiktok(access_token, video_path, caption, hashtags),
        "instagram": lambda: publish_to_instagram(access_token, video_path, caption, hashtags),
        "youtube": lambda: publish_to_youtube(access_token, video_path, title, caption, hashtags),
        "kwai": lambda: publish_to_kwai(access_token, video_path, caption, hashtags),
    }

    handler = dispatch.get(platform.lower())
    if not handler:
        raise PublishPlatformError(f"Plataforma nao suportada: {platform}")

    try:
        return handler()
    except PublishPlatformError:
        raise
    except Exception as exc:
        raise PublishPlatformError(
            f"Falha ao publicar em {platform}: {exc}"
        ) from exc
