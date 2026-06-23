"""Model: raw_videos — biblioteca de vídeos brutos por escritório."""

import enum
import uuid

from sqlalchemy import BigInteger, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from viraxis.infrastructure.database.base import Base
from viraxis.domain.models._base import BaseModelMixin


class RawVideoStatus(str, enum.Enum):
    pending = "pending"      # Aguardando upload completar
    ready = "ready"          # Upload concluído, disponível para uso
    processing = "processing"  # Em processamento (thumbnail, metadados)
    failed = "failed"        # Upload/processamento falhou


class RawVideo(BaseModelMixin, Base):
    """
    Vídeo bruto armazenado no R2 — insumo para o BRAIN e para o RENDERER.
    Cada vídeo pertence a um escritório e pode ser referenciado por ContentDecisions.
    """

    __tablename__ = "raw_videos"
    __table_args__ = (
        Index("ix_raw_videos_office_id", "office_id"),
        Index("ix_raw_videos_user_id", "user_id"),
        Index("ix_raw_videos_status", "status"),
        {"comment": "Biblioteca de vídeos brutos — insumo para BRAIN e RENDERER."},
    )

    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Metadados do arquivo
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    r2_key: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True,
        comment="Chave do objeto no Cloudflare R2.",
    )
    r2_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="URL pública ou presigned para acesso.",
    )
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    mime_type: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default="video/mp4"
    )

    status: Mapped[RawVideoStatus] = mapped_column(
        Enum(RawVideoStatus, name="rawvideostatus", create_constraint=True),
        nullable=False,
        default=RawVideoStatus.pending,
        server_default=RawVideoStatus.pending.value,
    )

    # Metadados opcionais fornecidos pelo usuário
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
        comment="Tags livres para categorizar o vídeo.",
    )

    # Relationships
    office: Mapped["Office"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Office", back_populates="raw_videos", lazy="raise"
    )
