"""Repositório async para RawVideo."""

from uuid import UUID

from sqlalchemy import desc, select

from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.infrastructure.repositories.base import BaseRepository


class RawVideoRepository(BaseRepository[RawVideo]):
    model = RawVideo

    async def list_by_office(
        self,
        office_id: UUID,
        *,
        status: RawVideoStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RawVideo]:
        """Lista vídeos de um escritório, mais recentes primeiro."""
        filters = [RawVideo.office_id == office_id]
        if status is not None:
            filters.append(RawVideo.status == status)
        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=desc(RawVideo.created_at),
        )

    async def get_ready_by_office(self, office_id: UUID) -> list[RawVideo]:
        """Retorna apenas vídeos prontos — para o BRAIN consultar."""
        return await self.list_by_office(office_id, status=RawVideoStatus.ready)

    async def get_by_r2_key(self, r2_key: str) -> RawVideo | None:
        result = await self.session.execute(
            select(RawVideo).where(RawVideo.r2_key == r2_key)
        )
        return result.scalar_one_or_none()
