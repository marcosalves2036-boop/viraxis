"""
DevCrew — Kevin + Davi trabalhando juntos no desenvolvimento do VIRAXIS.

Fluxo padrão (Process.sequential):
  1. Kevin lê o codebase e cria uma spec técnica detalhada
  2. Davi implementa a spec, validando cada arquivo antes de escrever
  3. Kevin revisa o que Davi implementou
  4. Resultado final retorna ao chamador

Uso rápido via CLI:
    python -m viraxis.agents.dev_crew "Adicionar endpoint PATCH /offices/{id}/status"
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from crewai import Crew, Process

from viraxis.agents.davi.agent import create_davi_agent
from viraxis.agents.davi.tasks import create_implementation_task
from viraxis.agents.kevin.agent import create_kevin_agent
from viraxis.agents.kevin.tasks import create_architecture_review_task, create_review_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sessão de desenvolvimento — armazenada em memória durante a execução
# ---------------------------------------------------------------------------

@dataclass
class DevSession:
    id: str = field(default_factory=lambda: str(uuid4()))
    task: str = ""
    status: str = "pending"          # pending | running | done | error
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    kevin_spec: str = ""
    davi_output: str = ""
    review_output: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "kevin_spec": self.kevin_spec,
            "davi_output": self.davi_output,
            "review_output": self.review_output,
            "error": self.error,
        }


# In-memory store — process-level cache (suficiente para dev tool)
_sessions: dict[str, DevSession] = {}


def get_session(session_id: str) -> Optional[DevSession]:
    return _sessions.get(session_id)


def list_sessions(limit: int = 20) -> list[dict]:
    sessions = sorted(_sessions.values(), key=lambda s: s.started_at or "", reverse=True)
    return [s.to_dict() for s in sessions[:limit]]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_dev_crew_sync(session: DevSession) -> None:
    """
    Executa Kevin+Davi de forma síncrona.
    Chamado via asyncio.to_thread para não bloquear o event loop da API.
    """
    session.status = "running"
    session.started_at = datetime.now(timezone.utc).isoformat()
    _sessions[session.id] = session

    try:
        kevin = create_kevin_agent()
        davi = create_davi_agent()

        # FASE 1: Kevin analisa e cria spec
        logger.info("[DevCrew] Kevin analisando tarefa: %s", session.task[:80])
        spec_task = create_architecture_review_task(kevin, session.task)

        spec_crew = Crew(
            agents=[kevin],
            tasks=[spec_task],
            process=Process.sequential,
            verbose=True,
        )
        spec_result = spec_crew.kickoff()
        session.kevin_spec = spec_result.raw or ""

        # FASE 2: Davi implementa baseado na spec do Kevin
        logger.info("[DevCrew] Davi implementando spec do Kevin...")
        impl_task = create_implementation_task(davi, session.kevin_spec)

        impl_crew = Crew(
            agents=[davi],
            tasks=[impl_task],
            process=Process.sequential,
            verbose=True,
        )
        impl_result = impl_crew.kickoff()
        session.davi_output = impl_result.raw or ""

        # FASE 3: Kevin revisa o que Davi implementou
        logger.info("[DevCrew] Kevin revisando implementação do Davi...")
        review_task = create_review_task(kevin, session.davi_output)

        review_crew = Crew(
            agents=[kevin],
            tasks=[review_task],
            process=Process.sequential,
            verbose=True,
        )
        review_result = review_crew.kickoff()
        session.review_output = review_result.raw or ""

        session.status = "done"
        logger.info("[DevCrew] Sessão %s concluída com sucesso.", session.id)

    except Exception as e:
        logger.exception("[DevCrew] Erro na sessão %s", session.id)
        session.status = "error"
        session.error = str(e)
    finally:
        session.finished_at = datetime.now(timezone.utc).isoformat()
        _sessions[session.id] = session


async def run_dev_task(task: str) -> DevSession:
    """
    Ponto de entrada principal — cria uma sessão e executa Kevin+Davi em background thread.

    Returns:
        DevSession com status='running'. Use get_session(id) para polling.
    """
    session = DevSession(task=task)
    _sessions[session.id] = session

    # Executa em thread separada para não bloquear o event loop do uvicorn
    asyncio.get_event_loop().run_in_executor(
        None, _run_dev_crew_sync, session
    )

    return session


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _cli_main(task: str) -> None:
    import sys
    print(f"\n{'='*60}")
    print("VIRAXIS DevCrew — Kevin + Davi")
    print(f"{'='*60}")
    print(f"Tarefa: {task}\n")

    session = DevSession(task=task)
    _run_dev_crew_sync(session)

    print(f"\n{'='*60}")
    print("📋 SPEC DO KEVIN")
    print(f"{'='*60}")
    print(session.kevin_spec)

    print(f"\n{'='*60}")
    print("💻 IMPLEMENTAÇÃO DO DAVI")
    print(f"{'='*60}")
    print(session.davi_output)

    print(f"\n{'='*60}")
    print("🔍 REVISÃO DO KEVIN")
    print(f"{'='*60}")
    print(session.review_output)

    if session.error:
        print(f"\n❌ ERRO: {session.error}")
        sys.exit(1)
    else:
        print(f"\n✅ Sessão concluída em {session.finished_at}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python -m viraxis.agents.dev_crew '<tarefa>'")
        sys.exit(1)
    asyncio.run(_cli_main(" ".join(sys.argv[1:])))
