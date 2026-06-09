"""BaseRepository genérico — CRUD async para qualquer model SQLAlchemy."""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Repository genérico com operações async básicas.

    Subclasses devem definir `model` como atributo de classe:

        class UserRepository(BaseRepository[User]):
            model = User
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Leitura                                                             #
    # ------------------------------------------------------------------ #

    async def get(self, id: UUID) -> ModelT | None:
        """Busca por PK. Retorna None se não encontrado."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, id: UUID) -> ModelT:
        """Busca por PK. Lança ValueError se não encontrado."""
        instance = await self.get(id)
        if instance is None:
            raise ValueError(f"{self.model.__name__} id={id} não encontrado.")
        return instance

    async def list(
        self,
        *filters: Any,
        limit: int = 100,
        offset: int = 0,
        order_by: Any = None,
    ) -> list[ModelT]:
        """Lista com filtros opcionais, paginação e ordenação."""
        stmt = select(self.model)
        if filters:
            stmt = stmt.where(*filters)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # Escrita                                                             #
    # ------------------------------------------------------------------ #

    async def create(self, **kwargs: Any) -> ModelT:
        """Cria e persiste uma nova instância."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()       # gera PK sem commit
        await self.session.refresh(instance)
        return instance

    async def save(self, instance: ModelT) -> ModelT:
        """Persiste uma instância já existente (update)."""
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Remove uma instância do banco."""
        await self.session.delete(instance)
        await self.session.flush()
