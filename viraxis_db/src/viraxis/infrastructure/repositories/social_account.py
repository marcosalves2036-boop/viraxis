"""Repositório async para SocialAccount — PR-5."""

from uuid import UUID

from sqlalchemy import desc, select

from viraxis.domain.models.social_account import SocialAccount, SocialPlatform
from viraxis.infrastructure.repositories.base import BaseRepository


class SocialAccountRepository(BaseRepository[SocialAccount]):
    model = SocialAccount

    async def list_by_user(
        self,
        user_id: UUID,
        *,
        platform: SocialPlatform | None = None,
        active_only: bool = True,
    ) -> list[SocialAccount]:
        """Lista contas do usuário, opcionalmente filtrando por plataforma e status."""
        filters = [SocialAccount.user_id == user_id]
        if active_only:
            filters.append(SocialAccount.is_active.is_(True))
        if platform is not None:
            filters.append(SocialAccount.platform == platform)
        return await self.list(
            *filters,
            order_by=desc(SocialAccount.created_at),
        )

    async def list_by_office(
        self,
        office_id: UUID,
        *,
        platform: SocialPlatform | None = None,
        active_only: bool = True,
    ) -> list[SocialAccount]:
        """Lista contas vinculadas a um escritório."""
        filters = [SocialAccount.office_id == office_id]
        if active_only:
            filters.append(SocialAccount.is_active.is_(True))
        if platform is not None:
            filters.append(SocialAccount.platform == platform)
        return await self.list(
            *filters,
            order_by=desc(SocialAccount.created_at),
        )

    async def get_by_user_platform_username(
        self,
        user_id: UUID,
        platform: SocialPlatform,
        platform_username: str,
    ) -> SocialAccount | None:
        """Busca por constraint única user+platform+username."""
        result = await self.session.execute(
            select(SocialAccount).where(
                SocialAccount.user_id == user_id,
                SocialAccount.platform == platform,
                SocialAccount.platform_username == platform_username,
            )
        )
        return result.scalar_one_or_none()

    async def deactivate(self, account: SocialAccount) -> SocialAccount:
        """Desativa sem deletar — preserva histórico de publicações."""
        account.is_active = False
        return await self.save(account)
