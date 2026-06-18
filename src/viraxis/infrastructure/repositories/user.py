"""Repositorio de usuarios."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.domain.models.user import User, UserPlan
from viraxis.infrastructure.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        plan: UserPlan = UserPlan.free,
    ) -> User:
        return await self.create(
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
            plan=plan,
        )
