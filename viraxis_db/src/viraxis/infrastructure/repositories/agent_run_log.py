"""Repositório async para AgentRunLog — PR-2."""

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, func, select, text

from viraxis.domain.models.agent_run_log import AgentRunLog, AgentRunStatus
from viraxis.infrastructure.repositories.base import BaseRepository

_MAX_JSONB_BYTES = 1_000_000  # 1 MB


def _truncate_jsonb(data: dict) -> tuple[dict, bool]:
    """Trunca payload JSONB se > 1MB. Retorna (dados, foi_truncado)."""
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw.encode()) <= _MAX_JSONB_BYTES:
        return data, False
    return {"_truncated": True, "original_size_bytes": len(raw.encode())}, True


class AgentRunLogRepository(BaseRepository[AgentRunLog]):
    model = AgentRunLog

    # ------------------------------------------------------------------ #
    # Criação com instrumentação                                         #
    # ------------------------------------------------------------------ #

    async def create_running(
        self,
        *,
        agent_name: str,
        task_name: str,
        office_id: UUID | None = None,
        user_id: UUID | None = None,
        input_data: dict | None = None,
        celery_task_id: str | None = None,
    ) -> AgentRunLog:
        """Cria log com status=running e started_at=agora.
        Chamado ANTES do crew.kickoff() no runner do agente.
        """
        raw_input = input_data or {}
        truncated_input, data_truncated = _truncate_jsonb(raw_input)
        if data_truncated:
            truncated_input["data_truncated"] = True

        return await self.create(
            agent_name=agent_name,
            task_name=task_name,
            office_id=office_id,
            user_id=user_id,
            input_data=truncated_input,
            output_data={},
            status=AgentRunStatus.running,
            started_at=datetime.now(tz=timezone.utc),
            celery_task_id=celery_task_id,
        )

    async def mark_success(
        self,
        log: AgentRunLog,
        output_data: dict | None = None,
    ) -> AgentRunLog:
        """Atualiza para success com output e finished_at."""
        raw_output = output_data or {}
        truncated_output, data_truncated = _truncate_jsonb(raw_output)
        if data_truncated:
            truncated_output["data_truncated"] = True

        log.status = AgentRunStatus.success
        log.output_data = truncated_output
        log.finished_at = datetime.now(tz=timezone.utc)
        return await self.save(log)

    async def mark_failed(
        self,
        log: AgentRunLog,
        error_message: str,
        traceback: str | None = None,
    ) -> AgentRunLog:
        """Atualiza para failed com mensagem de erro. Chamado no finally/except."""
        log.status = AgentRunStatus.failed
        log.error_message = error_message[:2000] if error_message else None
        log.traceback = traceback
        log.finished_at = datetime.now(tz=timezone.utc)
        return await self.save(log)

    # ------------------------------------------------------------------ #
    # Queries                                                             #
    # ------------------------------------------------------------------ #

    async def list_by_office(
        self,
        office_id: UUID,
        *,
        agent_name: str | None = None,
        status: AgentRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentRunLog]:
        """Lista logs de um escritório, mais recentes primeiro."""
        filters = [AgentRunLog.office_id == office_id]
        if agent_name:
            filters.append(AgentRunLog.agent_name == agent_name)
        if status:
            filters.append(AgentRunLog.status == status)
        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=desc(AgentRunLog.started_at),
        )

    async def list_all_admin(
        self,
        *,
        agent_name: str | None = None,
        status: AgentRunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentRunLog]:
        """Lista todos os logs — apenas para admin."""
        filters: list = []
        if agent_name:
            filters.append(AgentRunLog.agent_name == agent_name)
        if status:
            filters.append(AgentRunLog.status == status)
        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=desc(AgentRunLog.started_at),
        )

    async def count_by_status(self, status: AgentRunStatus) -> int:
        result = await self.session.execute(
            select(func.count(AgentRunLog.id)).where(AgentRunLog.status == status)
        )
        return result.scalar_one()

    async def cleanup_old_logs(self) -> int:
        """Remove logs com mais de 90 dias. Retorna quantidade removida.
        Chamado pelo Beat de manutenção diário.
        """
        result = await self.session.execute(
            text(
                "DELETE FROM agent_run_logs "
                "WHERE created_at < NOW() - INTERVAL '90 days' "
                "RETURNING id"
            )
        )
        return result.rowcount  # type: ignore[attr-defined]
