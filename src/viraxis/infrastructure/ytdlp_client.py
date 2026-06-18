"""Cliente yt-dlp async — wrapper com timeout, tratamento de erros e feature flag de transcrição.

PR-3 Fase 2.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT_S = 60
_SUPPORTED_DOMAINS = {
    "youtube.com", "youtu.be",
    "twitch.tv",
    "tiktok.com", "vm.tiktok.com",
}

# Feature flag — transcrição via Whisper desabilitada por padrão no MVP
SCOUT_ENABLE_TRANSCRIPTION = os.getenv("SCOUT_ENABLE_TRANSCRIPTION", "false").lower() == "true"


class YtdlpError(Exception):
    """Erro ao baixar/extrair metadados via yt-dlp."""


class UnsupportedPlatformError(YtdlpError):
    """URL de plataforma não suportada."""


class VideoUnavailableError(YtdlpError):
    """Vídeo privado, removido ou indisponível."""


class DownloadTimeoutError(YtdlpError):
    """Timeout no download."""


@dataclass
class VideoMetadata:
    """Metadados extraídos do vídeo pelo yt-dlp."""
    url: str
    platform: str  # youtube | tiktok | twitch
    title: str
    description: str
    duration_seconds: float | None
    thumbnail_url: str | None
    view_count: int | None
    like_count: int | None
    uploader: str | None
    transcription: str | None  # None se SCOUT_ENABLE_TRANSCRIPTION=false


def _detect_platform(url: str) -> str:
    """Detecta a plataforma a partir da URL."""
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "twitch.tv" in url_lower:
        return "twitch"
    return "unknown"


def _validate_url(url: str) -> None:
    """Valida se a URL é de uma plataforma suportada."""
    url_lower = url.lower()
    if not any(domain in url_lower for domain in _SUPPORTED_DOMAINS):
        raise UnsupportedPlatformError(
            f"Plataforma não suportada. URL deve ser de: {', '.join(sorted(_SUPPORTED_DOMAINS))}"
        )


def _extract_metadata_sync(url: str) -> VideoMetadata:
    """Extrai metadados via yt-dlp de forma síncrona.
    Chamado via asyncio.to_thread para não bloquear o event loop.
    """
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:
        raise YtdlpError("yt-dlp não está instalado. Execute: pip install yt-dlp>=2024.12.0") from exc

    platform = _detect_platform(url)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,  # Apenas metadados no Sprint 1
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        err_str = str(exc).lower()
        if any(kw in err_str for kw in ("private", "unavailable", "not available", "removed")):
            raise VideoUnavailableError(f"Vídeo indisponível: {exc}") from exc
        raise YtdlpError(f"Erro ao extrair metadados: {exc}") from exc
    except Exception as exc:
        raise YtdlpError(f"Erro inesperado no yt-dlp: {exc}") from exc

    if info is None:
        raise YtdlpError("yt-dlp retornou None para a URL fornecida")

    # Transcrição via Whisper — apenas se feature flag ativa
    transcription: str | None = None
    if SCOUT_ENABLE_TRANSCRIPTION:
        transcription = _transcribe_sync(url, info)

    return VideoMetadata(
        url=url,
        platform=platform,
        title=info.get("title", "") or "",
        description=info.get("description", "") or "",
        duration_seconds=info.get("duration"),
        thumbnail_url=info.get("thumbnail"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        uploader=info.get("uploader") or info.get("channel"),
        transcription=transcription,
    )


def _transcribe_sync(url: str, info: dict) -> str | None:
    """Transcrição via faster-whisper — apenas se SCOUT_ENABLE_TRANSCRIPTION=true."""
    try:
        import faster_whisper  # noqa: PLC0415
    except ImportError:
        logger.warning("faster-whisper não instalado. Transcrição desabilitada.")
        return None

    # Usa legenda automática se disponível (mais rápido que Whisper)
    auto_captions = info.get("automatic_captions", {})
    if auto_captions:
        lang = "pt" if "pt" in auto_captions else next(iter(auto_captions), None)
        if lang and auto_captions[lang]:
            captions = auto_captions[lang]
            if isinstance(captions, list) and captions:
                # Extrai texto das legendas VTT/JSON
                texts = [c.get("text", "") for c in captions if isinstance(c, dict)]
                combined = " ".join(t for t in texts if t)
                if combined.strip():
                    return combined[:5000]  # Limita a 5000 chars

    logger.info("Transcrição Whisper não implementada neste sprint — retornando None")
    return None


async def fetch_video_metadata(url: str) -> VideoMetadata:
    """Ponto de entrada principal — async, com timeout e validação.

    Args:
        url: URL do vídeo (YouTube, Twitch, TikTok)

    Returns:
        VideoMetadata com título, descrição, duração e opcionalmente transcrição.

    Raises:
        UnsupportedPlatformError: URL de plataforma não suportada
        VideoUnavailableError: Vídeo privado ou removido
        DownloadTimeoutError: Timeout de 60s excedido
        YtdlpError: Outros erros do yt-dlp
    """
    _validate_url(url)

    platform = _detect_platform(url)
    if platform == "tiktok":
        logger.warning("TikTok tem suporte experimental — yt-dlp pode falhar com frequência")

    try:
        metadata = await asyncio.wait_for(
            asyncio.to_thread(_extract_metadata_sync, url),
            timeout=_DOWNLOAD_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise DownloadTimeoutError(
            f"Timeout de {_DOWNLOAD_TIMEOUT_S}s excedido ao processar {url}"
        ) from exc

    logger.info(
        "yt-dlp extraiu metadados | platform=%s | title=%.60s | duration=%s",
        metadata.platform,
        metadata.title,
        metadata.duration_seconds,
    )
    return metadata


def build_video_context(metadata: VideoMetadata) -> str:
    """Formata metadados como texto para o agente SCOUT processar."""
    parts = [
        f"Título: {metadata.title}",
        f"Plataforma: {metadata.platform}",
    ]
    if metadata.duration_seconds:
        mins = int(metadata.duration_seconds // 60)
        secs = int(metadata.duration_seconds % 60)
        parts.append(f"Duração: {mins}min {secs}s")
    if metadata.description:
        parts.append(f"\nDescrição:\n{metadata.description[:1000]}")
    if metadata.transcription:
        parts.append(f"\nTranscrição (parcial):\n{metadata.transcription[:3000]}")
    return "\n".join(parts)
