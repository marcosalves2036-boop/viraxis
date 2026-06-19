"""Repositório async para NicheProfile."""

from uuid import UUID

from sqlalchemy import select

from viraxis.domain.models.niche_profile import NicheProfile
from viraxis.infrastructure.repositories.base import BaseRepository


class NicheProfileRepository(BaseRepository[NicheProfile]):
    model = NicheProfile

    # ------------------------------------------------------------------ #
    # Queries especializadas                                              #
    # ------------------------------------------------------------------ #

    async def get_by_office_id(self, office_id: UUID) -> NicheProfile | None:
        """
        Retorna o NicheProfile de um escritório (relação 1:1).
        Retorna None se o escritório ainda não tem perfil.
        """
        result = await self.session.execute(
            select(NicheProfile).where(NicheProfile.office_id == office_id)
        )
        return result.scalar_one_or_none()

    async def get_by_office_or_raise(self, office_id: UUID) -> NicheProfile:
        """Igual a get_by_office_id, mas lança ValueError se não existir."""
        profile = await self.get_by_office_id(office_id)
        if profile is None:
            raise ValueError(
                f"NicheProfile para office_id={office_id} não encontrado. "
                "O escritório precisa ser configurado antes de rodar o BRAIN."
            )
        return profile

    async def list_by_user(
        self, user_id: UUID, *, limit: int = 100
    ) -> list[NicheProfile]:
        """Lista todos os perfis de nichos de um usuário (multi-office)."""
        return await self.list(
            NicheProfile.user_id == user_id,
            limit=limit,
        )

    async def upsert(
        self,
        *,
        office_id: UUID,
        user_id: UUID,
        niche_name: str,
        target_platforms: list | None = None,
        viral_archetypes: dict | None = None,
        content_style: dict | None = None,
        top_keywords: list | None = None,
        brain_params: dict | None = None,
        raw_notes: str | None = None,
    ) -> NicheProfile:
        """
        Cria o NicheProfile se não existir; atualiza os campos se já existir.
        Mantém campos não fornecidos inalterados em caso de update.
        """
        existing = await self.get_by_office_id(office_id)

        if existing is None:
            return await self.create(
                office_id=office_id,
                user_id=user_id,
                niche_name=niche_name,
                target_platforms=target_platforms or [],
                viral_archetypes=viral_archetypes or {},
                content_style=content_style or {},
                top_keywords=top_keywords or [],
                brain_params=brain_params or {},
                raw_notes=raw_notes,
            )

        # Update apenas os campos fornecidos
        existing.niche_name = niche_name
        if target_platforms is not None:
            existing.target_platforms = target_platforms
        if viral_archetypes is not None:
            existing.viral_archetypes = viral_archetypes
        if content_style is not None:
            existing.content_style = content_style
        if top_keywords is not None:
            existing.top_keywords = top_keywords
        if brain_params is not None:
            existing.brain_params = brain_params
        if raw_notes is not None:
            existing.raw_notes = raw_notes

        return await self.save(existing)
