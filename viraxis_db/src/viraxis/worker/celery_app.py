"""Instância central do Celery — PR-6 Fase 2.

Importar apenas este módulo para obter a instância `celery_app`.
Tasks ficam em viraxis/worker/tasks.py.

Iniciar worker:
    celery -A viraxis.worker.celery_app worker --loglevel=info -Q viraxis

Iniciar beat (tarefas periódicas):
    celery -A viraxis.worker.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from viraxis.config import settings

celery_app = Celery(
    "viraxis",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["viraxis.worker.tasks"],
)

celery_app.conf.update(
    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Retry behavior padrão
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Expiração de resultado: 24h
    result_expires=86400,
    # Prefetch — 1 task por vez para tarefas longas de IA
    worker_prefetch_multiplier=1,
    # Roteamento de filas
    task_routes={
        "viraxis.worker.tasks.run_brain_task": {"queue": "viraxis"},
        "viraxis.worker.tasks.run_scout_task": {"queue": "viraxis"},
        "viraxis.worker.tasks.run_renderer_task": {"queue": "viraxis"},
        "viraxis.worker.tasks.run_publisher_task": {"queue": "viraxis"},
        "viraxis.worker.tasks.cleanup_agent_logs_task": {"queue": "viraxis-beat"},
    },
    # Agendamento periódico (Beat)
    beat_schedule={
        # Limpeza de AgentRunLogs com mais de 90 dias — roda todo dia às 3:00
        "cleanup-agent-logs-daily": {
            "task": "viraxis.worker.tasks.cleanup_agent_logs_task",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
