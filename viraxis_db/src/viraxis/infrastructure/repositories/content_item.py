"""Repositório async para ContentItem — PR-1."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, func, select

from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.infrastructure.repositories.base import BaseRepository


class ContentItemRepository(BaseRepository[ContentItem]):
    model = ContentItem

    # ------------------------------------------------------------------ #
    # Queries especializadas                                              #
    # ------------------------------------------------------------------ #

    async def list_by_office(
        self,
        office_id: UUID,
        *,
        status: ContentStatus | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentItem]:
        """Lista ContentItems de um escritório, mais recentes primeiro.

        Por padrão exclui itens com deleted_at preenchido (soft deleted).
        """
        filters = [ContentItem.office_id == office_id]
        if not include_deleted:
            filters.append(ContentItem.deleted_at.is_(None))
        if status is not None:
            filters.append(ContentItem.status == status)
        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=desc(ContentItem.created_at),
        )

    async def get_by_id_for_office(
        self,
        item_id: UUID,
        office_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> ContentItem | None:
        """Busca um ContentItem garantindo que pertence ao escritório (multi-tenant)."""
        stmt = select(ContentItem).where(
            ContentItem.id == item_id,
            ContentItem.office_id == office_id,
        )
        if not include_deleted:
            stmt = stmt.where(ContentItem.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete(self, item: ContentItem) -> ContentItem:
        """Marca deleted_at sem remover do banco."""
        item.deleted_at = datetime.now(tz=timezone.utc)
        return await self.save(item)

    async def count_by_office(
        self,
        office_id: UUID,
        *,
        status: ContentStatus | None = None,
        include_deleted: bool = False,
    ) -> int:
        """Conta ContentItems de um escritório."""
        filters = [ContentItem.office_id == office_id]
        if not include_deleted:
            filters.append(ContentItem.deleted_at.is_(None))
        if status is not None:
            filters.append(ContentItem.status == status)
        stmt = select(func.count(ContentItem.id)).where(*filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update_status(
        self,
        item: ContentItem,
        new_status: ContentStatus,
    ) -> ContentItem:
        """Atualiza status verificando transições válidas."""
        _VALID_TRANSITIONS: dict[ContentStatus, set[ContentStatus]] = {
            ContentStatus.draft: {ContentStatus.rendering, ContentStatus.failed},
            ContentStatus.rendering: {ContentStatus.ready, ContentStatus.failed},
            ContentStatus.ready: {ContentStatus.published, ContentStatus.draft},
            ContentStatus.published: set(),
            ContentStatus.failed: {ContentStatus.draft},
        }
        allowed = _VALID_TRANSITIONS.get(item.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Transição inválida: {item.status.value} → {new_status.value}. "
                f"Permitidas: {[s.value for s in allowed]}"
            )
        item.status = new_status
        return await self.save(item)
