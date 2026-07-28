"""Clientes de publicacao por plataforma — PR-7 Fase 2 / Sprint 3.

Sprint 1: stubs que simulam publicacao. Retornam sucesso com external_id fake.
Sprint 3: TikTok implementado de verdade via Content Posting API (Direct Post).
          Instagram/YouTube/Kwai permanecem stub — proximos alvos de sprint.

Design:
  - Cada funcao recebe o token descriptografado (plaintext) — a descriptografia
    e o eventual refresh de token acontecem no runner ANTES de chamar os
    clientes (ver agents/publisher/runner.py).
  - Retornam (external_id, url) ou lancam PublishPlatformError.
  - Chamadas HTTP sao sincronas (httpx.Client) — o runner despacha estas
    funcoes via asyncio.to_thread para nao bloquear o event loop.

TikTok — status do app (client_key aw54mjn8uvws4dkh):
  O app esta em modo "unaudited" (sandbox) na TikTok for Developers Console.
  Nesse modo:
    - so e possivel publicar com post_info.privacy_level=SELF_ONLY (o video
      fica visivel apenas para o proprio dono da conta logada, nunca no
      feed publico/For You Page);
    - o volume de chamadas e limitado e o dominio precisa estar verificado
      (URL prefix / dominio na TikTok Developer Console).
  Passos para tirar o app do sandbox (audit):
    1. TikTok for Developers > App > "Submit for review" / "App Review".
    2. Preencher o formulario de uso do Content Posting API descrevendo o
       caso de uso do Viraxis (postagem automatizada de shorts gerados por
       IA, com consentimento explicito do usuario antes de cada publish).
    3. Anexar video de demonstracao do fluxo completo (OAuth -> geracao ->
       publish) e a URL de política de privacidade publica.
    4. Aguardar aprovacao (TikTok cita prazo de alguns dias uteis).
    5. Apos aprovado, o app pode publicar com privacy_level=PUBLIC_TO_EVERYONE
       (ou o que o usuario escolher dentre creator_info.privacy_level_options)
       sem precisar de TIKTOK_DRY_RUN nem do fallback SELF_ONLY.
  Enquanto isso, TIKTOK_DRY_RUN=true (env var / settings.tiktok_dry_run) faz
  publish_to_tiktok() simular toda a logica (decrypt ja feito pelo runner,
  montagem do payload de init) SEM chamar a rede do TikTok, retornando um
  external_id simulado prefixado "tiktok_dryrun_".
"""

from __future__ import annotations

import logging
import math
import os
import time
import uuid

import httpx

logger = logging.getLogger(__name__)

# Graph API v19 — usado pelo publish_to_instagram
IG_GRAPH_BASE = "https://graph.facebook.com/v19.0"
IG_POLL_INTERVAL_SECONDS = 5
IG_POLL_MAX_ATTEMPTS = 36  # 36 * 5s = até 3min aguardando o processamento do vídeo


class PublishPlatformError(Exception):
    """Erro ao publicar em uma plataforma especifica."""


# ── TikTok ─────────────────────────────────────────────────────────────────────

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_INIT_URL = f"{TIKTOK_API_BASE}/post/publish/video/init/"
TIKTOK_STATUS_URL = f"{TIKTOK_API_BASE}/post/publish/status/fetch/"
TIKTOK_CREATOR_INFO_URL = f"{TIKTOK_API_BASE}/post/publish/creator_info/query/"
TIKTOK_REFRESH_URL = f"{TIKTOK_API_BASE}/oauth/token/"

TIKTOK_MIN_CHUNK_BYTES = 5 * 1024 * 1024          # 5 MB — minimo por chunk (exceto video inteiro)
TIKTOK_MAX_CHUNK_BYTES = 64 * 1024 * 1024         # 64 MB — maximo por chunk "normal"
TIKTOK_SINGLE_UPLOAD_LIMIT = TIKTOK_MAX_CHUNK_BYTES  # <= 64MB -> upload em um unico chunk
TIKTOK_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024   # 4 GB — limite documentado da API

TIKTOK_POLL_INTERVAL_SECONDS = 3
TIKTOK_POLL_MAX_ATTEMPTS = 30  # ~90s de polling antes de retornar com status pendente
TIKTOK_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=300.0, pool=10.0)


def _tiktok_dry_run_enabled() -> bool:
    """Retorna True se o publish deve ser simulado (sem chamadas reais ao TikTok).

    Controlado por settings.tiktok_dry_run (env var TIKTOK_DRY_RUN=true/1) —
    ver docstring do modulo para o motivo (app em sandbox/unaudited).
    """
    try:
        from viraxis.config import settings  # noqa: PLC0415

        if bool(getattr(settings, "tiktok_dry_run", False)):
            return True
    except Exception:  # pragma: no cover - defensivo, settings sempre deve existir
        logger.warning("Nao foi possivel ler settings.tiktok_dry_run — usando apenas env var.")

    return os.environ.get("TIKTOK_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


def _tiktok_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def refresh_tiktok_token(refresh_token: str) -> dict:
    """Troca um refresh_token TikTok valido por um novo access_token.

    POST https://open.tiktokapis.com/v2/oauth/token/ com
    grant_type=refresh_token. Chamado pelo runner quando
    SocialAccount.token_expires_at esta proximo/passado, ANTES de tentar
    publicar.

    Args:
        refresh_token: refresh_token ja descriptografado (plaintext).

    Returns:
        dict com (pelo menos) access_token, refresh_token, expires_in,
        refresh_expires_in, open_id, scope — conforme resposta oficial do
        TikTok.

    Raises:
        PublishPlatformError: refresh_token ausente/invalido/expirado, ou
            falha de rede/parsing na chamada.
    """
    from viraxis.config import settings  # noqa: PLC0415

    if not refresh_token:
        raise PublishPlatformError(
            "refresh_token do TikTok ausente — usuario precisa reconectar a conta."
        )

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                TIKTOK_REFRESH_URL,
                data={
                    "client_key": settings.tiktok_client_key,
                    "client_secret": settings.tiktok_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise PublishPlatformError(f"Erro de rede ao renovar token TikTok: {exc}") from exc

    if resp.status_code != 200:
        logger.error("TikTok refresh token falhou (%s): %s", resp.status_code, resp.text[:500])
        raise PublishPlatformError(
            f"Falha ao renovar token TikTok ({resp.status_code}): {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise PublishPlatformError(f"Resposta de refresh do TikTok nao e JSON valido: {exc}") from exc

    # TikTok pode devolver erro em formato "flat" mesmo com HTTP 200.
    error_val = data.get("error")
    if error_val and isinstance(error_val, str) and error_val not in ("", "ok"):
        raise PublishPlatformError(
            f"TikTok recusou o refresh_token: {data.get('error_description', error_val)}"
        )

    token_data = data.get("data", data)
    if "access_token" not in token_data:
        raise PublishPlatformError(f"Resposta de refresh sem access_token: {data}")

    logger.info(
        "TikTok access_token renovado com sucesso | open_id=%s | expires_in=%s",
        token_data.get("open_id"), token_data.get("expires_in"),
    )
    return token_data


def _tiktok_creator_info(access_token: str) -> dict:
    """Consulta as configuracoes do criador — obrigatorio antes de cada Direct Post.

    POST https://open.tiktokapis.com/v2/post/publish/creator_info/query/

    Retorna dict com (entre outros) privacy_level_options, comment_disabled,
    duet_disabled, stitch_disabled, max_video_post_duration_sec.
    """
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(TIKTOK_CREATOR_INFO_URL, headers=_tiktok_headers(access_token))
    except httpx.HTTPError as exc:
        raise PublishPlatformError(
            f"Erro de rede ao consultar creator_info do TikTok: {exc}"
        ) from exc

    if resp.status_code != 200:
        logger.error("TikTok creator_info falhou (%s): %s", resp.status_code, resp.text[:500])
        raise PublishPlatformError(
            f"Falha ao consultar creator_info do TikTok ({resp.status_code}): {resp.text[:300]}"
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise PublishPlatformError(f"Resposta de creator_info nao e JSON valido: {exc}") from exc

    error = body.get("error", {})
    if isinstance(error, dict) and error.get("code", "ok") not in ("ok", ""):
        raise PublishPlatformError(
            f"TikTok creator_info retornou erro: {error.get('message', error)}"
        )
    return body.get("data", {})


def _pick_privacy_level(privacy_options: list[str]) -> str:
    """Escolhe o privacy_level mais seguro disponivel para o post.

    Apps TikTok ainda nao auditados ("unaudited") so tem permissao de postar
    com privacy_level=SELF_ONLY (video visivel apenas ao dono da conta) —
    publicar com qualquer outro valor enquanto o app esta em sandbox e
    rejeitado pela API. Por isso SELF_ONLY e sempre preferido quando
    disponivel na lista devolvida por creator_info; so usamos outro valor se
    SELF_ONLY nao estiver presente (o que nao deveria acontecer na pratica).
    """
    if not privacy_options:
        return "SELF_ONLY"
    if "SELF_ONLY" in privacy_options:
        return "SELF_ONLY"
    return privacy_options[0]


def _download_video(video_url: str) -> bytes:
    """Baixa o video inteiro em memoria (URL assinada do Supabase Storage).

    Necessario para calcular video_size exato e montar os chunks do upload
    conforme a doc do TikTok. Levanta PublishPlatformError se o download
    falhar, vier vazio ou exceder o limite de tamanho do TikTok.
    """
    try:
        with httpx.Client(timeout=TIKTOK_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(video_url)
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPError as exc:
        raise PublishPlatformError(f"Falha ao baixar video para upload no TikTok: {exc}") from exc

    if not content:
        raise PublishPlatformError("Video baixado do storage esta vazio — nao ha o que publicar.")
    if len(content) > TIKTOK_MAX_VIDEO_BYTES:
        raise PublishPlatformError(
            f"Video excede o limite de {TIKTOK_MAX_VIDEO_BYTES // (1024 * 1024)}MB do TikTok "
            f"({len(content) // (1024 * 1024)}MB)."
        )
    return content


def _compute_chunks(video_size: int) -> tuple[int, int]:
    """Calcula (chunk_size, total_chunk_count) seguindo as regras do TikTok.

    Regras (doc "content-posting-api-reference-upload-video"):
      - video_size <= 64MB: upload em um unico chunk (chunk_size=video_size).
      - video_size > 64MB: chunks de ate 64MB; total_chunk_count = ceil(size/chunk).
        O ultimo chunk carrega o restante (pode ser menor que 5MB em casos
        extremos — TikTok tolera isso apenas no ultimo chunk).
    """
    if video_size <= TIKTOK_SINGLE_UPLOAD_LIMIT:
        return video_size, 1

    chunk_size = TIKTOK_MAX_CHUNK_BYTES
    total_chunk_count = math.ceil(video_size / chunk_size)
    return chunk_size, total_chunk_count


def _tiktok_init_upload(access_token: str, title: str, privacy_level: str, video_size: int) -> dict:
    """POST video/init/ — inicia o upload e retorna {publish_id, upload_url}."""
    chunk_size, total_chunk_count = _compute_chunks(video_size)
    logger.info(
        "TikTok upload init | video_size=%d bytes | chunk_size=%d | total_chunk_count=%d",
        video_size, chunk_size, total_chunk_count,
    )

    init_payload = {
        "post_info": {
            "title": title,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_stitch": False,
            "disable_comment": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        },
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TIKTOK_INIT_URL, json=init_payload, headers=_tiktok_headers(access_token))
    except httpx.HTTPError as exc:
        raise PublishPlatformError(f"Erro de rede no init do upload TikTok: {exc}") from exc

    if resp.status_code != 200:
        logger.error("TikTok init falhou (%s): %s", resp.status_code, resp.text[:500])
        raise PublishPlatformError(
            f"Falha ao iniciar upload no TikTok ({resp.status_code}): {resp.text[:300]}"
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise PublishPlatformError(f"Resposta de init do TikTok nao e JSON valido: {exc}") from exc

    error = body.get("error", {})
    if isinstance(error, dict) and error.get("code", "ok") not in ("ok", ""):
        raise PublishPlatformError(f"TikTok init retornou erro: {error.get('message', error)}")

    data = body.get("data", {})
    if not data.get("upload_url") or not data.get("publish_id"):
        raise PublishPlatformError(f"Resposta de init sem upload_url/publish_id: {body}")

    data["_chunk_size"] = chunk_size
    return data


def _tiktok_upload_binary(upload_url: str, video_bytes: bytes, chunk_size: int) -> int:
    """PUT do binario do video para `upload_url`, em 1+ chunks. Retorna nro de chunks enviados."""
    video_size = len(video_bytes)
    offset = 0
    chunk_index = 0
    try:
        with httpx.Client(timeout=TIKTOK_HTTP_TIMEOUT) as client:
            while offset < video_size:
                end = min(offset + chunk_size, video_size) - 1
                chunk_data = video_bytes[offset:end + 1]
                put_headers = {
                    "Content-Range": f"bytes {offset}-{end}/{video_size}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk_data)),
                }
                put_resp = client.put(upload_url, content=chunk_data, headers=put_headers)
                if put_resp.status_code not in (200, 201, 206):
                    raise PublishPlatformError(
                        f"Falha no upload do chunk {chunk_index} ao TikTok "
                        f"({put_resp.status_code}): {put_resp.text[:300]}"
                    )
                offset = end + 1
                chunk_index += 1
    except httpx.HTTPError as exc:
        raise PublishPlatformError(f"Erro de rede durante upload do video ao TikTok: {exc}") from exc

    return chunk_index


def _tiktok_poll_status(access_token: str, publish_id: str) -> tuple[str | None, str | None]:
    """Poll em status/fetch/ ate PUBLISH_COMPLETE, FAILED ou esgotar tentativas.

    Returns:
        (video_id_ou_None, ultimo_status_conhecido)

    Raises:
        PublishPlatformError: se o TikTok reportar FAILED/ERROR explicitamente.
    """
    last_status = None
    for attempt in range(1, TIKTOK_POLL_MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    TIKTOK_STATUS_URL,
                    json={"publish_id": publish_id},
                    headers=_tiktok_headers(access_token),
                )
        except httpx.HTTPError as exc:
            logger.warning("Erro de rede ao consultar status TikTok (tentativa %d/%d): %s",
                            attempt, TIKTOK_POLL_MAX_ATTEMPTS, exc)
            time.sleep(TIKTOK_POLL_INTERVAL_SECONDS)
            continue

        if resp.status_code != 200:
            logger.warning(
                "TikTok status/fetch falhou (%s) tentativa %d/%d: %s",
                resp.status_code, attempt, TIKTOK_POLL_MAX_ATTEMPTS, resp.text[:300],
            )
            time.sleep(TIKTOK_POLL_INTERVAL_SECONDS)
            continue

        try:
            status_body = resp.json().get("data", {})
        except ValueError:
            logger.warning("Resposta de status TikTok nao e JSON valido (tentativa %d)", attempt)
            time.sleep(TIKTOK_POLL_INTERVAL_SECONDS)
            continue

        last_status = status_body.get("status")
        logger.info("TikTok publish status (tentativa %d/%d): %s",
                     attempt, TIKTOK_POLL_MAX_ATTEMPTS, last_status)

        if last_status == "PUBLISH_COMPLETE":
            published_ids = status_body.get("publicly_available_post_id") or []
            video_id = published_ids[0] if published_ids else publish_id
            return video_id, last_status

        if last_status in ("FAILED", "ERROR"):
            fail_reason = status_body.get("fail_reason", "motivo nao informado pelo TikTok")
            raise PublishPlatformError(f"TikTok falhou ao processar a publicacao: {fail_reason}")

        time.sleep(TIKTOK_POLL_INTERVAL_SECONDS)

    return None, last_status


def publish_to_tiktok(
    access_token: str,
    video_path: str | None,
    caption: str,
    hashtags: list[str],
) -> tuple[str, str]:
    """Publica video no TikTok via Content Posting API (Direct Post).

    Fluxo real (quando dry-run esta desativado):
      1. POST creator_info/query/ — descobre privacy_level_options validos
         para a conta autenticada (obrigatorio antes de todo Direct Post).
      2. Baixa o video de `video_path` (deve ser uma URL http(s) ja assinada
         e pronta para GET direto — o runner e quem gera essa URL a partir
         do storage_path do ContentItem, via sign_storage_path()).
      3. POST video/init/ com source_info.source=FILE_UPLOAD, video_size,
         chunk_size e total_chunk_count calculados a partir do tamanho real
         do arquivo baixado, e post_info (title/privacy_level).
      4. PUT do binario para a upload_url retornada (1 ou mais chunks,
         conforme Content-Range).
      5. Poll em status/fetch/ ate publish_id atingir PUBLISH_COMPLETE (ou
         FAILED), retornando o video_id publicado.

    Modo dry-run (TIKTOK_DRY_RUN=true): decripta/monta tudo normalmente ate
    o payload de init, mas NAO faz nenhuma chamada de rede ao TikTok — usado
    enquanto o app estiver em sandbox/unaudited (ver docstring do modulo).

    Args:
        access_token: token de acesso ja descriptografado (plaintext) — a
            descriptografia e o refresh (se necessario) acontecem no runner.
        video_path: URL http(s) assinada do video a publicar.
        caption: legenda/titulo do post (TikTok usa o campo `title`).
        hashtags: hashtags (o runner ja costuma embuti-las na caption; mantido
            aqui apenas para logging/rastreabilidade).

    Returns:
        (external_id, url):
          - modo real: (video_id publicado ou publish_id se ainda
            processando, melhor URL disponivel).
          - modo dry-run: (id simulado prefixado "tiktok_dryrun_", URL fake).

    Raises:
        PublishPlatformError: qualquer falha na cadeia acima (rede, escopo,
            token invalido, video ausente/invalido, TikTok reportando erro).
    """
    if not access_token:
        raise PublishPlatformError("access_token do TikTok ausente ou nao descriptografado.")
    if not video_path:
        raise PublishPlatformError("video_path ausente — nao ha video disponivel para publicar no TikTok.")

    title = (caption or "")[:2200]  # limite documentado do campo post_info.title
    dry_run = _tiktok_dry_run_enabled()

    if dry_run:
        logger.warning(
            "TIKTOK_DRY_RUN ativo — simulando publish_to_tiktok() sem chamar a API real "
            "do TikTok (app em modo sandbox/unaudited). caption=%.60s | hashtags=%s",
            title, hashtags,
        )
        simulated_payload = {
            "post_info": {"title": title, "privacy_level": "SELF_ONLY"},
            "source_info": {"source": "FILE_UPLOAD", "video_path_preview": video_path[:120]},
        }
        logger.info("TikTok dry-run — payload que seria enviado: %s", simulated_payload)
        ext_id = f"tiktok_dryrun_{uuid.uuid4().hex[:12]}"
        return ext_id, f"https://www.tiktok.com/dry-run/{ext_id}"

    # ---- 1. creator_info — obrigatorio antes de cada Direct Post ----
    creator_info = _tiktok_creator_info(access_token)
    privacy_options = creator_info.get("privacy_level_options", [])
    privacy_level = _pick_privacy_level(privacy_options)
    logger.info(
        "TikTok creator_info | privacy_options=%s | escolhido=%s | max_duration_s=%s",
        privacy_options, privacy_level, creator_info.get("max_video_post_duration_sec"),
    )

    # ---- 2. download do video (necessario para saber tamanho e montar chunks) ----
    video_bytes = _download_video(video_path)

    # ---- 3. init do upload ----
    init_data = _tiktok_init_upload(access_token, title, privacy_level, len(video_bytes))
    upload_url = init_data["upload_url"]
    publish_id = init_data["publish_id"]
    chunk_size = init_data["_chunk_size"]

    # ---- 4. upload do binario ----
    chunks_sent = _tiktok_upload_binary(upload_url, video_bytes, chunk_size)
    logger.info("TikTok upload concluido | publish_id=%s | chunks_enviados=%d", publish_id, chunks_sent)

    # ---- 5. polling de status ----
    video_id, last_status = _tiktok_poll_status(access_token, publish_id)
    if video_id is None:
        # Nao completou dentro do timeout de polling — nao e necessariamente
        # um erro definitivo (o TikTok pode levar mais tempo para processar
        # em segundo plano). Retornamos o publish_id como referencia; o
        # status real pode ser consultado depois via status/fetch/.
        logger.warning(
            "TikTok publish nao concluiu dentro do timeout de polling (%ds) | "
            "publish_id=%s | ultimo_status=%s",
            TIKTOK_POLL_MAX_ATTEMPTS * TIKTOK_POLL_INTERVAL_SECONDS, publish_id, last_status,
        )
        video_id = publish_id

    # TikTok nao devolve uma URL publica pronta no status/fetch — apenas
    # publicly_available_post_id (numerico) e o proprio publish_id. Sem o
    # @username nao e possivel montar a URL canonica /@user/video/{id}, entao
    # devolvemos uma URL de referencia interna; o frontend pode resolver a
    # URL real combinando com SocialAccount.platform_username se precisar.
    url = f"https://www.tiktok.com/publish/{video_id}"
    logger.info("TikTok publish finalizado | video_id=%s | privacy_level=%s | status=%s",
                video_id, privacy_level, last_status)
    return video_id, url


# ── Instagram ──────────────────────────────────────────────────────────────────

def publish_to_instagram(
    access_token: str,
    video_path: str | None,
    caption: str,
    hashtags: list[str],
    *,
    platform_user_id: str | None = None,
) -> tuple[str, str]:
    """Publica Reel no Instagram via Graph API v19 (Content Publishing).

    Fluxo real (nao-stub):
      1. POST /{ig-user-id}/media  (video_url, media_type=REELS, caption)
         -> retorna um container_id (processamento assincrono do video)
      2. Poll GET /{container_id}?fields=status_code ate status FINISHED
         (ou ERROR / timeout)
      3. POST /{ig-user-id}/media_publish (creation_id=container_id)
         -> retorna o media_id publicado
      4. GET /{media_id}?fields=permalink -> URL publica do post

    Requisitos:
      - `platform_user_id` deve ser o ID da Instagram Business Account
        (obtido no callback OAuth /auth/instagram/callback e salvo em
        SocialAccount.platform_user_id).
      - `access_token` deve ser o Page Access Token vinculado a essa conta
        (é o que o callback OAuth armazena criptografado).
      - `video_path` deve ser uma URL http(s) publicamente acessível (o
        Graph API busca o arquivo diretamente — não aceita upload direto de
        bytes neste endpoint). O runner é responsável por resolver o path
        interno de storage para uma signed URL antes de chamar esta função.

    Returns:
        (external_id, url) — media_id do post e o permalink público.

    Raises:
        PublishPlatformError: dados insuficientes ou falha em qualquer etapa
        da API do Instagram.
    """
    if not platform_user_id:
        raise PublishPlatformError(
            "Conta Instagram sem platform_user_id (ID da IG Business Account). "
            "Reconecte a conta via /auth/instagram/authorize."
        )
    if not video_path or not video_path.lower().startswith("http"):
        raise PublishPlatformError(
            "URL pública de vídeo indisponível para publicação no Instagram "
            "(era esperada uma URL http(s) assinada; recebido: "
            f"{video_path!r})."
        )

    logger.info(
        "Instagram publish iniciando | ig_user=%s | caption=%.60s | hashtags=%s",
        platform_user_id, caption, hashtags,
    )

    with httpx.Client(timeout=30.0) as client:
        # ---- 1. Criar container de mídia ----
        create_resp = client.post(
            f"{IG_GRAPH_BASE}/{platform_user_id}/media",
            data={
                "video_url": video_path,
                "media_type": "REELS",
                "caption": caption,
                "access_token": access_token,
            },
        )
        if create_resp.status_code != 200:
            logger.error(
                "Instagram: falha ao criar container de mídia (%d): %s",
                create_resp.status_code, create_resp.text[:500],
            )
            raise PublishPlatformError(
                f"Instagram: falha ao criar container de mídia "
                f"({create_resp.status_code}): {create_resp.text[:300]}"
            )

        container_data = create_resp.json()
        container_id = container_data.get("id")
        if not container_id:
            raise PublishPlatformError(
                f"Instagram: resposta sem container id: {container_data}"
            )

        # ---- 2. Poll até o container terminar de processar o vídeo ----
        status_code = "IN_PROGRESS"
        status_detail = ""
        for attempt in range(1, IG_POLL_MAX_ATTEMPTS + 1):
            time.sleep(IG_POLL_INTERVAL_SECONDS)
            status_resp = client.get(
                f"{IG_GRAPH_BASE}/{container_id}",
                params={"fields": "status_code,status", "access_token": access_token},
            )
            if status_resp.status_code != 200:
                logger.warning(
                    "Instagram: poll de status falhou (%d/%d, http=%d): %s",
                    attempt, IG_POLL_MAX_ATTEMPTS, status_resp.status_code,
                    status_resp.text[:300],
                )
                continue

            status_data = status_resp.json()
            status_code = status_data.get("status_code", "IN_PROGRESS")
            status_detail = status_data.get("status", "")
            logger.info(
                "Instagram container=%s status=%s (%d/%d)",
                container_id, status_code, attempt, IG_POLL_MAX_ATTEMPTS,
            )

            if status_code == "FINISHED":
                break
            if status_code == "ERROR":
                raise PublishPlatformError(
                    f"Instagram: processamento do vídeo falhou (container={container_id}): "
                    f"{status_detail or status_data}"
                )
        else:
            raise PublishPlatformError(
                f"Instagram: timeout aguardando processamento do vídeo "
                f"(container={container_id}, último status={status_code})"
            )

        # ---- 3. Publicar o container ----
        publish_resp = client.post(
            f"{IG_GRAPH_BASE}/{platform_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": access_token},
        )
        if publish_resp.status_code != 200:
            logger.error(
                "Instagram: falha ao publicar mídia (%d): %s",
                publish_resp.status_code, publish_resp.text[:500],
            )
            raise PublishPlatformError(
                f"Instagram: falha ao publicar mídia "
                f"({publish_resp.status_code}): {publish_resp.text[:300]}"
            )

        publish_data = publish_resp.json()
        media_id = publish_data.get("id")
        if not media_id:
            raise PublishPlatformError(
                f"Instagram: publish sem media id: {publish_data}"
            )

        # ---- 4. Buscar permalink público (best-effort) ----
        permalink = f"https://www.instagram.com/reel/{media_id}/"
        try:
            perma_resp = client.get(
                f"{IG_GRAPH_BASE}/{media_id}",
                params={"fields": "permalink", "access_token": access_token},
            )
            if perma_resp.status_code == 200:
                permalink = perma_resp.json().get("permalink", permalink)
            else:
                logger.warning(
                    "Instagram: falha ao buscar permalink (%d): %s — usando fallback",
                    perma_resp.status_code, perma_resp.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.warning("Instagram: erro ao buscar permalink: %s — usando fallback", exc)

    logger.info(
        "Instagram publish concluído | media_id=%s | url=%s", media_id, permalink,
    )
    return media_id, permalink


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
    Sprint 3 (proxima): POST https://www.googleapis.com/upload/youtube/v3/videos

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
    Sprint 3 (proxima): implementar via Kwai for Developers.

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
    platform_user_id: str | None = None,
) -> tuple[str, str]:
    """Despacha a publicacao para o cliente correto da plataforma.

    `platform_user_id` é usado apenas pelo Instagram (ID da IG Business
    Account); as demais plataformas ignoram o parâmetro.

    Returns:
        (external_id, url)

    Raises:
        PublishPlatformError: Plataforma nao suportada ou falha na API.
    """
    dispatch = {
        "tiktok": lambda: publish_to_tiktok(access_token, video_path, caption, hashtags),
        "instagram": lambda: publish_to_instagram(
            access_token, video_path, caption, hashtags, platform_user_id=platform_user_id
        ),
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
