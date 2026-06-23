"""Router de Raw Videos — biblioteca de vídeos brutos por escritório."""

import logging
import mimetypes
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

import boto3
from botocore.client import Config
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.config import settings
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.domain.models.user import User
from sqlalchemy import select as sa_select
from viraxis.domain.models.office import Office
from viraxis.infrastructure.repositories.raw_video import RawVideoRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/raw-videos", tags=["raw-videos"])


# ── Helpers R2 ─────────────────────────────────────────────────────────────────

def _r2_client():
    """Retorna cliente boto3 configurado para Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url or None,
        aws_access_key_id=settings.r2_access_key_id or None,
        aws_secret_access_key=settings.r2_secret_access_key or None,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _r2_configured() -> bool:
    return bool(
        settings.r2_endpoint_url
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
    )


# ── Schemas ────────────────────────────────────────────────────────────────────

class PresignRequest(BaseModel):
    office_id: str
    filename: str
    mime_type: str = "video/mp4"
    file_size_bytes: Optional[int] = None


class PresignResponse(BaseModel):
    upload_url: str
    r2_key: str
    expires_in: int = 900  # 15 min


class RawVideoRegister(BaseModel):
    """Chamado após upload direto completar."""
    office_id: str
    r2_key: str
    original_filename: str
    mime_type: str = "video/mp4"
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = []


class RawVideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None  # "ready" | "failed"
    duration_seconds: Optional[float] = None


class RawVideoResponse(BaseModel):
    id: str
    office_id: str
    original_filename: str
    r2_key: str
    r2_url: Optional[str]
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
    def from_model(cls, v: RawVideo) -> "RawVideoResponse":
        return cls(
            id=str(v.id),
            office_id=str(v.office_id),
            original_filename=v.original_filename,
            r2_key=v.r2_key,
            r2_url=v.r2_url,
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

@router.post("/presign", response_model=PresignResponse)
async def get_presigned_upload_url(
    body: PresignRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Gera URL presigned para upload direto ao R2.
    O browser faz PUT direto no R2, sem passar pelo servidor.
    """
    if not _r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento R2 não configurado. Contate o suporte.",
        )

    # Verificar que o office pertence ao usuário
    result = await session.execute(
        sa_select(Office).where(Office.id == UUID(body.office_id), Office.user_id == current_user.id)
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escritório não encontrado.")

    # Gerar r2_key única
    ext = mimetypes.guess_extension(body.mime_type) or ".mp4"
    r2_key = f"raw-videos/{current_user.id}/{body.office_id}/{uuid.uuid4()}{ext}"

    try:
        s3 = _r2_client()
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.r2_bucket_name,
                "Key": r2_key,
                "ContentType": body.mime_type,
            },
            ExpiresIn=900,
        )
    except Exception as e:
        logger.error("Erro ao gerar presigned URL: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao gerar URL de upload.")

    return PresignResponse(upload_url=upload_url, r2_key=r2_key)


@router.post("", response_model=RawVideoResponse, status_code=status.HTTP_201_CREATED)
async def register_video(
    body: RawVideoRegister,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Registra metadados de um vídeo após o upload direto ao R2 completar.
    O status inicial é 'ready' se o upload foi bem-sucedido.
    """
    result = await session.execute(
        sa_select(Office).where(Office.id == UUID(body.office_id), Office.user_id == current_user.id)
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    repo = RawVideoRepository(session)

    # Verificar duplicata por r2_key
    existing = await repo.get_by_r2_key(body.r2_key)
    if existing:
        raise HTTPException(status_code=409, detail="Vídeo já registrado.")

    # Construir URL pública (se R2 configurado com domínio público)
    r2_url = None
    if settings.r2_endpoint_url and body.r2_key:
        r2_url = f"{settings.r2_endpoint_url}/{settings.r2_bucket_name}/{body.r2_key}"

    video = await repo.create(
        office_id=UUID(body.office_id),
        user_id=current_user.id,
        original_filename=body.original_filename,
        r2_key=body.r2_key,
        r2_url=r2_url,
        file_size_bytes=body.file_size_bytes,
        duration_seconds=body.duration_seconds,
        mime_type=body.mime_type,
        status=RawVideoStatus.ready,
        title=body.title,
        description=body.description,
        tags=body.tags,
    )

    await session.commit()
    return RawVideoResponse.from_model(video)


@router.get("", response_model=list[RawVideoResponse])
async def list_videos(
    office_id: str = Query(..., description="ID do escritório"),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista vídeos brutos de um escritório."""
    result = await session.execute(
        sa_select(Office).where(Office.id == UUID(office_id), Office.user_id == current_user.id)
    )
    office = result.scalar_one_or_none()
    if not office:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    repo = RawVideoRepository(session)

    status_enum = None
    if status_filter:
        try:
            status_enum = RawVideoStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Status inválido: {status_filter}")

    videos = await repo.list_by_office(
        UUID(office_id),
        status=status_enum,
        limit=limit,
        offset=offset,
    )
    return [RawVideoResponse.from_model(v) for v in videos]


@router.get("/{video_id}", response_model=RawVideoResponse)
async def get_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna metadados de um vídeo específico."""
    repo = RawVideoRepository(session)
    video = await repo.get(UUID(video_id))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
    return RawVideoResponse.from_model(video)


@router.patch("/{video_id}", response_model=RawVideoResponse)
async def update_video(
    video_id: str,
    body: RawVideoUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Atualiza metadados (title, description, tags, status, duration)."""
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
    return RawVideoResponse.from_model(video)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Remove o registro do vídeo (não deleta do R2 — deve ser feito manualmente)."""
    repo = RawVideoRepository(session)
    video = await repo.get(UUID(video_id))
    if not video or video.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    await repo.delete(video)
    await session.commit()
