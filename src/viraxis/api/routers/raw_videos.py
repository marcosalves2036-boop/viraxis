"""Router de Raw Videos — biblioteca de vídeos brutos por escritório (Supabase Storage)."""

import logging
import mimetypes
import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.rate_limit import limiter
from viraxis.api.utils import parse_uuid as _parse_uuid
from viraxis.config import settings
from viraxis.domain.models.office import Office
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.domain.models.user import User
from viraxis.infrastructure.repositories.raw_video import RawVideoRepository
from viraxis.infrastructure.upload_analyzer import analyze_uploaded_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/raw-videos", tags=["raw-videos"])

SUPABASE_BUCKET = "biblioteca-videos"


# ── Helpers Supabase Storage ───────────────────────────────────────────────────

def _supabase_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _storage_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _storage_base() -> str:
    return f"{settings.supabase_url}/storage/v1"


async def _upload_to_supabase(path: str, data: bytes, mime_type: str) -> str:
    """Faz upload de bytes para o Supabase Storage e retorna o storage path."""
    import httpx

    url = f"{_storage_base()}/object/{SUPABASE_BUCKET}/{path}"
    headers = {
        **_storage_headers(),
        "Content-Type": mime_type,
        "x-upsert": "false",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, content=data, headers=headers)
        if resp.status_code not in (200, 201):
            logger.error("Supabase Storage upload error: %s %s", resp.status_code, resp.text)
            raise HTTPException(status_code=500, detail=f"Erro no upload: {resp.text}")
    return path


async def _signed_url(path: str, expires_in: int = 86400) -> Optional[str]:
    """Gera URL assinada para download (válida por 24h). Async via httpx."""
    if not _supabase_configured():
        return None
    try:
        import httpx
        url = f"{_storage_base()}/object/sign/{SUPABASE_BUCKET}/{path}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={"expiresIn": expires_in},
                headers=_storage_headers(),
            )
        if resp.status_code == 200:
            data = resp.json()
            signed = data.get("signedURL") or data.get("signedUrl") or ""
            if signed and not signed.startswith("http"):
                signed = f"{settings.supabase_url}/storage/v1{signed}"
            return signed
    except Exception as e:
        logger.warning("Erro ao gerar signed URL: %s", e)
    return None


async def _delete_from_supabase(path: str) -> None:
    """Remove objeto do Supabase Storage."""
    import httpx

    url = f"{_storage_base()}/object/{SUPABASE_BUCKET}/{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.delete(url, headers=_storage_headers())


# ── Schemas ────────────────────────────────────────────────────────────────────

class RawVideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = None


class RawVideoResponse(BaseModel):
    id: str
    office_id: str
    original_filename: str
    r2_key: str          # reutilizado: armazena o storage_path no Supabase
    r2_url: Optional[str]  # signed URL gerada sob demanda
    file_size_bytes: Optional[int]
    duration_seconds: Optional[float]
    mime_type: str
    status: str
    title: Optional[str]
    description: Optional[str]
    tags: list
    ai_analysis: Optional[dict]
    error_type: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, v: RawVideo, signed_url: Optional[str] = None) -> "RawVideoResponse":
        return cls(
            id=str(v.id),
            office_id=str(v.office_id),
            original_filename=v.original_filename,
            r2_key=v.r2_key,
            r2_url=signed_url or v.r2_url,
            file_size_bytes=v.file_size_bytes,
            duration_seconds=v.duration_seconds,
            mime_type=v.mime_type,
            status=v.status.value,
            title=v.title,
            description=v.description,
            tags=v.tags or [],
            ai_analysis=v.ai_analysis,
            error_type=v.error_type,
            created_at=v.created_at.isoformat(),
            updated_at=v.updated_at.isoformat(),
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=RawVideoResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")
async def upload_video(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    office_id: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Recebe vídeo via multipart, faz upload para o Supabase Storage,
    registra metadados no banco e dispara análise automática de IA em background.
    Retorna o vídeo criado (status=processing enquanto a IA analisa, depois ready).

    Rate limit (15/min por usuário): cada upload dispara análise de IA
    (Gemini + Whisper) em background — custo real por chamada.
    """
    if not _supabase_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento não configurado. Contate o suporte.",
        )

    # Verificar que o office pertence ao usuário
    office_uuid = _parse_uuid(office_id, "office_id")
    result = await session.execute(
        sa_select(Office).where(
            Office.id == office_uuid,
            Office.user_id == current_user.id,
        )
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escritório não encontrado.")

    # Ler arquivo em memória — APENAS para arquivos pequenos.
    # Vídeos grandes devem usar o fluxo /upload-url (upload direto browser→Supabase).
    MAX_DIRECT_UPLOAD_BYTES = 50 * 1024 * 1024
    data = await file.read()
    file_size = len(data)
    if file_size > MAX_DIRECT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Arquivo acima de 50MB. Use o fluxo de upload direto (/raw-videos/upload-url).",
        )

    # Inferir mime_type
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "video/mp4"
    ext = mimetypes.guess_extension(mime_type) or ".mp4"
    if ext == ".mp4v":
        ext = ".mp4"

    # Gerar storage path único
    storage_path = f"{current_user.id}/{office_id}/{uuid.uuid4()}{ext}"

    # Upload para Supabase Storage
    await _upload_to_supabase(storage_path, data, mime_type)

    # Gerar signed URL inicial (24h)
    signed = await _signed_url(storage_path)

    # Registrar no banco
    repo = RawVideoRepository(session)
    video = await repo.create(
        office_id=office_uuid,
        user_id=current_user.id,
        original_filename=file.filename or "video",
        r2_key=storage_path,       # reutilizamos o campo r2_key para o storage_path
        r2_url=signed,
        file_size_bytes=file_size,
        duration_seconds=None,
        mime_type=mime_type,
        status=RawVideoStatus.processing,
        title=title,
        description=description,
        tags=[],
    )
    await session.commit()

    # Disparar análise de IA em background (não bloqueia a resposta ao usuário)
    if signed:
        background_tasks.add_task(analyze_uploaded_video, str(video.id), signed)

    return RawVideoResponse.from_model(video, signed_url=signed)


async def _probe_duration(url: str) -> Optional[float]:
    """Extrai a duração do vídeo via ffprobe (binário estático do build)."""
    import asyncio
    import json as _json
    import os
    import shutil
    import subprocess

    probe_bin = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [probe_bin, "-v", "quiet", "-print_format", "json", "-show_format", url],
            capture_output=True,
            timeout=90,
        )
        data = _json.loads(proc.stdout or b"{}")
        duration = float((data.get("format") or {}).get("duration") or 0)
        return duration if duration > 0 else None
    except Exception as e:
        logger.warning("ffprobe falhou (duração ficará vazia): %s", e)
        return None


class UploadUrlRequest(BaseModel):
    office_id: str
    filename: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None


class UploadUrlResponse(BaseModel):
    video_id: str
    upload_url: str
    storage_path: str


@router.post("/upload-url", response_model=UploadUrlResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")
async def create_upload_url(
    request: Request,
    body: UploadUrlRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Gera signed upload URL para o browser enviar o vídeo DIRETO ao Supabase.

    Evita passar o arquivo pelo Render (vídeos grandes derrubavam o serviço).
    Fluxo: upload-url → PUT do arquivo na URL → confirm-upload.

    Rate limit (15/min por usuário): cada chamada cria uma linha `RawVideo`
    nova e cada upload confirmado dispara análise de IA — mesmo write
    amplificado do endpoint /upload acima.
    """
    if not _supabase_configured():
        logger.error("upload-url chamado sem Supabase configurado (SUPABASE_URL/SERVICE_ROLE_KEY ausentes).")
        raise HTTPException(status_code=503, detail="Armazenamento não configurado.")

    office_uuid = _parse_uuid(body.office_id, "office_id")

    result = await session.execute(
        sa_select(Office).where(
            Office.id == office_uuid,
            Office.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    mime_type = body.mime_type or mimetypes.guess_type(body.filename)[0] or "video/mp4"
    ext = mimetypes.guess_extension(mime_type) or ".mp4"
    if ext == ".mp4v":
        ext = ".mp4"
    storage_path = f"{current_user.id}/{body.office_id}/{uuid.uuid4()}{ext}"

    import httpx
    sign_url = f"{_storage_base()}/object/upload/sign/{SUPABASE_BUCKET}/{storage_path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(sign_url, headers=_storage_headers(), json={})
    except httpx.TimeoutException as e:
        logger.error(
            "Timeout ao contatar Supabase Storage (upload-url) para office_id=%s: %s",
            body.office_id, e,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Armazenamento demorou para responder. Tente novamente em instantes.",
        )
    except httpx.RequestError as e:
        # Cobre falhas de DNS/conexão — ex: projeto Supabase pausado por inatividade (INACTIVE),
        # que resolve DNS como NXDOMAIN e derruba esta chamada antes de qualquer resposta HTTP.
        logger.error(
            "Falha de rede ao contatar Supabase Storage (upload-url) para office_id=%s: %s - %s",
            body.office_id, type(e).__name__, e,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível conectar ao armazenamento no momento. Tente novamente em instantes.",
        )

    if resp.status_code != 200:
        logger.error(
            "Supabase signed upload URL error para office_id=%s storage_path=%s: %s %s",
            body.office_id, storage_path, resp.status_code, resp.text,
        )
        raise HTTPException(status_code=502, detail="Erro ao gerar URL de upload no armazenamento.")

    try:
        rel_url = resp.json().get("url", "")
    except ValueError as e:
        logger.error("Resposta inválida (não-JSON) do Supabase Storage ao assinar upload: %s - body=%r", e, resp.text)
        raise HTTPException(status_code=502, detail="Resposta inválida do armazenamento ao gerar URL de upload.")

    if not rel_url:
        logger.error("Supabase não retornou 'url' na resposta de sign upload: %r", resp.text)
        raise HTTPException(status_code=502, detail="Armazenamento não retornou URL de upload.")
    upload_url = rel_url if rel_url.startswith("http") else f"{_storage_base()}{rel_url}"

    try:
        repo = RawVideoRepository(session)
        video = await repo.create(
            office_id=office_uuid,
            user_id=current_user.id,
            original_filename=body.filename,
            r2_key=storage_path,
            r2_url=None,
            file_size_bytes=body.file_size_bytes,
            duration_seconds=None,
            mime_type=mime_type,
            status=RawVideoStatus.processing,
            title=None,
            description=None,
            tags=[],
        )
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.exception(
            "Erro ao registrar raw_video no banco (upload-url) para office_id=%s storage_path=%s: %s",
            body.office_id, storage_path, e,
        )
        raise HTTPException(status_code=500, detail="Erro ao registrar vídeo. Tente novamente.")

    return UploadUrlResponse(
        video_id=str(video.id),
        upload_url=upload_url,
        storage_path=storage_path,
    )


class ConfirmUploadRequest(BaseModel):
    file_size_bytes: Optional[int] = None


@router.post("/{video_id}/confirm-upload", response_model=RawVideoResponse)
async def confirm_upload(
    video_id: UUID,
    body: ConfirmUploadRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Confirma que o browser terminou o upload direto ao Supabase.

    Extrai a duração via ffprobe, gera signed URL 24h e dispara a análise
    de IA em background.
    """
    video = await session.get(RawVideo, video_id)
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    if body.file_size_bytes:
        video.file_size_bytes = body.file_size_bytes

    signed = await _signed_url(video.r2_key)
    if not signed:
        raise HTTPException(status_code=500, detail="Erro ao gerar signed URL do vídeo.")

    duration = await _probe_duration(signed)
    if duration:
        video.duration_seconds = duration

    video.r2_url = signed
    session.add(video)
    await session.commit()
    await session.refresh(video)

    background_tasks.add_task(analyze_uploaded_video, str(video.id), signed)

    return RawVideoResponse.from_model(video, signed_url=signed)


@router.post("/{video_id}/reanalyze", response_model=RawVideoResponse)
@limiter.limit("10/minute")
async def reanalyze_video(
    request: Request,
    video_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Re-dispara a análise de IA de um RawVideo com status=failed, sem exigir
    novo upload — reusa o arquivo já presente no Supabase Storage (r2_key).

    Rate limit (10/min por usuário): mesmo custo real de análise de IA do
    endpoint de upload original — só sem o envio de arquivo.

    Usado pelo botão "Tentar novamente" da Biblioteca (frontend do Arthur):
    o usuário não precisa reenviar o vídeo, só confirmar a nova tentativa.

    Fluxo:
      1. Valida que o vídeo existe e pertence ao usuário autenticado
         (mesma checagem de autorização multi-tenant de get_video/update_video/
         delete_video: `video.user_id != current_user.id` → 404. Não vazamos
         "vídeo existe mas não é seu" via 403 — 404 evita enumeração).
      2. Recusa com 422 se o vídeo não estiver em status=failed (idempotência:
         não faz sentido reanalisar algo pending/processing/ready).
      3. Gera uma signed URL nova (a antiga pode ter expirado — validade 24h)
         a partir do r2_key já armazenado, sem tocar no arquivo no bucket.
      4. Volta status=processing, limpa error_type e enfileira
         analyze_uploaded_video em BackgroundTask — o MESMO fluxo assíncrono
         usado no upload original (confirm_upload), então o resto do pipeline
         (ffprobe, Gemini, Whisper, gravação de ai_analysis) é idêntico.
    """
    repo = RawVideoRepository(session)
    video = await repo.get(_parse_uuid(video_id, "video_id"))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    if video.status != RawVideoStatus.failed:
        raise HTTPException(
            status_code=422,
            detail=(
                "Só é possível reanalisar vídeos com status=failed "
                f"(status atual: {video.status.value})."
            ),
        )

    if not _supabase_configured():
        logger.error("reanalyze chamado sem Supabase configurado | video_id=%s", video_id)
        raise HTTPException(status_code=503, detail="Armazenamento não configurado. Contate o suporte.")

    if not video.r2_key:
        raise HTTPException(
            status_code=422,
            detail="Vídeo sem arquivo associado no armazenamento — não é possível reanalisar. Faça um novo upload.",
        )

    signed = await _signed_url(video.r2_key)
    if not signed:
        logger.error(
            "reanalyze: falha ao gerar signed URL | video_id=%s | r2_key=%s",
            video_id, video.r2_key,
        )
        raise HTTPException(
            status_code=502,
            detail="Erro ao gerar URL de acesso ao arquivo no armazenamento. Tente novamente em instantes.",
        )

    prior_analysis = video.ai_analysis or {}
    video.status = RawVideoStatus.processing
    video.error_type = None
    video.r2_url = signed
    # Preserva o histórico da falha anterior sob uma chave própria, mas sinaliza
    # que uma nova tentativa está em andamento — evita a UI mostrar "failed"
    # obsoleto entre o disparo do reanalyze e a conclusão da nova análise.
    video.ai_analysis = {
        **prior_analysis,
        "status": "reanalyzing",
        "previous_failure": {
            "error": prior_analysis.get("error"),
            "error_type": prior_analysis.get("error_type"),
        },
    }
    session.add(video)
    await session.commit()
    await session.refresh(video)

    logger.info(
        "reanalyze disparado | video_id=%s | user_id=%s | office_id=%s",
        video_id, current_user.id, video.office_id,
    )
    background_tasks.add_task(analyze_uploaded_video, str(video.id), signed)

    return RawVideoResponse.from_model(video, signed_url=signed)


@router.get("", response_model=list[RawVideoResponse])
async def list_videos(
    office_id: str = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista vídeos brutos de um escritório com signed URLs frescas."""
    office_uuid = _parse_uuid(office_id, "office_id")
    result = await session.execute(
        sa_select(Office).where(
            Office.id == office_uuid,
            Office.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    repo = RawVideoRepository(session)
    status_enum = None
    if status_filter:
        try:
            status_enum = RawVideoStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {status_filter}")

    videos = await repo.list_by_office(office_uuid, status=status_enum, limit=limit, offset=offset)

    # Gerar signed URLs em paralelo (async, 24h de validade)
    import asyncio
    async def _get_signed(v: RawVideo):
        signed = await _signed_url(v.r2_key) if (_supabase_configured() and v.r2_key) else None
        return RawVideoResponse.from_model(v, signed_url=signed)

    result_list = await asyncio.gather(*[_get_signed(v) for v in videos])
    return list(result_list)


@router.get("/{video_id}", response_model=RawVideoResponse)
async def get_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = RawVideoRepository(session)
    video = await repo.get(_parse_uuid(video_id, "video_id"))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
    signed = await _signed_url(video.r2_key) if (_supabase_configured() and video.r2_key) else None
    return RawVideoResponse.from_model(video, signed_url=signed)


@router.patch("/{video_id}", response_model=RawVideoResponse)
async def update_video(
    video_id: str,
    body: RawVideoUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = RawVideoRepository(session)
    video = await repo.get(_parse_uuid(video_id, "video_id"))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    if body.title is not None:
        video.title = body.title
    if body.description is not None:
        video.description = body.description
    if body.tags is not None:
        video.tags = body.tags
    if body.duration_seconds is not None:
        video.duration_seconds = body.duration_seconds
    if body.status is not None:
        try:
            video.status = RawVideoStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {body.status}")

    await repo.save(video)
    await session.commit()
    signed = await _signed_url(video.r2_key) if (_supabase_configured() and video.r2_key) else None
    return RawVideoResponse.from_model(video, signed_url=signed)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = RawVideoRepository(session)
    video = await repo.get(_parse_uuid(video_id, "video_id"))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    # Deletar do Supabase Storage também
    if video.r2_key and _supabase_configured():
        try:
            await _delete_from_supabase(video.r2_key)
        except Exception as e:
            logger.warning("Erro ao deletar do Supabase Storage: %s", e)

    await repo.delete(video)
    await session.commit()
