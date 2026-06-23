"""Repositório async para ContentDecision."""

from uuid import UUID

from sqlalchemy import desc, func, select

from viraxis.domain.models.content_decision import (
    ContentDecision,
    DecisionStatus,
    DecisionType,
)
from viraxis.infrastructure.repositories.base import BaseRepository


class ContentDecisionRepository(BaseRepository[ContentDecision]):
    model = ContentDecision

    # ------------------------------------------------------------------ #
    # Queries especializadas                                              #
    # ------------------------------------------------------------------ #

    async def list_by_office(
        self,
        office_id: UUID,
        *,
        status: DecisionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentDecision]:
        """Lista decisões de um escritório, mais recentes primeiro."""
        filters = [ContentDecision.office_id == office_id]
        if status is not None:
            filters.append(ContentDecision.status == status)
        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=desc(ContentDecision.created_at),
        )

    async def get_latest_by_office(self, office_id: UUID) -> ContentDecision | None:
        """Retorna a decisão mais recente de um escritório."""
        result = await self.session.execute(
            select(ContentDecision)
            .where(ContentDecision.office_id == office_id)
            .order_by(desc(ContentDecision.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_by_status(
        self, office_id: UUID, status: DecisionStatus
    ) -> int:
        """Conta decisões em um determinado status para um escritório."""
        result = await self.session.execute(
            select(func.count(ContentDecision.id)).where(
                ContentDecision.office_id == office_id,
                ContentDecision.status == status,
            )
        )
        return result.scalar_one()

    async def update_status(
        self, decision: ContentDecision, new_status: DecisionStatus
    ) -> ContentDecision:
        """Atualiza o status de uma decisão existente."""
        decision.status = new_status
        return await self.save(decision)

    async def create_decision(
        self,
        *,
        office_id: UUID,
        user_id: UUID,
        decision_type: DecisionType,
        hypothesis: str,
        reasoning: dict,
        input_signals: dict,
        selected_topic: str | None = None,
        selected_archetype: str | None = None,
        selected_platform: str | None = None,
        confidence_score: float | None = None,
        status: DecisionStatus = DecisionStatus.pending,
        extra_instructions: str | None = None,
    ) -> ContentDecision:
        """
        Atalho semântico — cria uma ContentDecision com campos nomeados.
        Evita kwargs genéricos no site de chamada.
        """
        return await self.create(
            office_id=office_id,
            user_id=user_id,
            decision_type=decision_type,
            hypothesis=hypothesis,
            reasoning=reasoning,
            input_signals=input_signals,
            selected_topic=selected_topic,
            selected_archetype=selected_archetype,
            selected_platform=selected_platform,
            confidence_score=confidence_score,
            status=status,
            extra_instructions=extra_instructions,
        )
