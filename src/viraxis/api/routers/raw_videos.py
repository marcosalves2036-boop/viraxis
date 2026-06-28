"""Router de Raw Videos — biblioteca de vídeos brutos por escritório (Supabase Storage)."""

import logging
import mimetypes
import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select

from viraxis.api.deps import get_current_user, get_session
from viraxis.config import settings
from viraxis.domain.models.office import Office
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.domain.models.user import User
from viraxis.infrastructure.repositories.raw_video import RawVideoRepository

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


def _signed_url(path: str, expires_in: int = 3600) -> Optional[str]:
    """Gera URL assinada para download (válida por 1h). Síncrono via requests."""
    if not _supabase_configured():
        return None
    try:
        import requests
        url = f"{_storage_base()}/object/sign/{SUPABASE_BUCKET}/{path}"
        resp = requests.post(
            url,
            json={"expiresIn": expires_in},
            headers=_storage_headers(),
            timeout=10,
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
            created_at=v.created_at.isoformat(),
            updated_at=v.updated_at.isoformat(),
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=RawVideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    office_id: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Recebe vídeo via multipart, faz upload para o Supabase Storage
    e registra metadados no banco. Retorna o vídeo criado.
    """
    if not _supabase_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento não configurado. Contate o suporte.",
        )

    # Verificar que o office pertence ao usuário
    result = await session.execute(
        sa_select(Office).where(
            Office.id == UUID(office_id),
            Office.user_id == current_user.id,
        )
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escritório não encontrado.")

    # Ler arquivo em memória
    data = await file.read()
    file_size = len(data)

    # Inferir mime_type
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "video/mp4"
    ext = mimetypes.guess_extension(mime_type) or ".mp4"
    if ext == ".mp4v":
        ext = ".mp4"

    # Gerar storage path único
    storage_path = f"{current_user.id}/{office_id}/{uuid.uuid4()}{ext}"

    # Upload para Supabase Storage
    await _upload_to_supabase(storage_path, data, mime_type)

    # Gerar signed URL inicial (1h)
    signed = _signed_url(storage_path)

    # Registrar no banco
    repo = RawVideoRepository(session)
    video = await repo.create(
        office_id=UUID(office_id),
        user_id=current_user.id,
        original_filename=file.filename or "video",
        r2_key=storage_path,       # reutilizamos o campo r2_key para o storage_path
        r2_url=signed,
        file_size_bytes=file_size,
        duration_seconds=None,
        mime_type=mime_type,
        status=RawVideoStatus.ready,
        title=title,
        description=description,
        tags=[],
    )
    await session.commit()
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
    result = await session.execute(
        sa_select(Office).where(
            Office.id == UUID(office_id),
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

    videos = await repo.list_by_office(UUID(office_id), status=status_enum, limit=limit, offset=offset)

    # Gerar signed URLs em lote (síncrono, mas rápido)
    result_list = []
    for v in videos:
        signed = _signed_url(v.r2_key) if _supabase_configured() and v.r2_key else None
        result_list.append(RawVideoResponse.from_model(v, signed_url=signed))
    return result_list


@router.get("/{video_id}", response_model=RawVideoResponse)
async def get_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = RawVideoRepository(session)
    video = await repo.get(UUID(video_id))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
    signed = _signed_url(video.r2_key) if _supabase_configured() and video.r2_key else None
    return RawVideoResponse.from_model(video, signed_url=signed)


@router.patch("/{video_id}", response_model=RawVideoResponse)
async def update_video(
    video_id: str,
    body: RawVideoUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = RawVideoRepository(session)
    video = await repo.get(UUID(video_id))
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
    signed = _signed_url(video.r2_key) if _supabase_configured() and video.r2_key else None
    return RawVideoResponse.from_model(video, signed_url=signed)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = RawVideoRepository(session)
    video = await repo.get(UUID(video_id))
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
