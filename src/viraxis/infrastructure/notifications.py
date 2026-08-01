"""Notificações de eventos de produto.

Hoje cobre apenas um evento: ContentItem termina de ser produzido e vira
`status=ready`. É o primeiro loop de retenção do produto — sem isso o
usuário só descobre que o vídeo ficou pronto voltando manualmente ao
dashboard.

Ponto único de disparo — chamado a partir dos lugares do código onde
`ContentItem.status` é efetivamente setado para `ContentStatus.ready`:
  - src/viraxis/api/routers/content_items.py
    (_process_editing_plan_background, _compose_ai_video_v2_background)
  - src/viraxis/api/routers/offices.py (approve_content_item)

Protegido contra:
  - ambiente não-produção — mesma lógica de proteção usada para
    TIKTOK_DRY_RUN (settings-based flag), aqui usando ENVIRONMENT: só
    dispara o envio real quando `ENVIRONMENT=production`. Em dev/staging
    o envio é sempre pulado (sem erro), para não gerar ruído com emails
    de teste durante desenvolvimento;
  - opt-out do usuário (`User.notify_content_ready is False`);
  - qualquer falha (Resend, rede, DB) — nunca propaga exceção, apenas loga.
    Notificação é um efeito colateral e nunca pode derrubar o pipeline de
    vídeo (FFmpeg/composer/approve).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.config import settings
from viraxis.domain.models.content_item import ContentItem
from viraxis.domain.models.office import Office
from viraxis.domain.models.user import User
from viraxis.infrastructure.email import send_content_ready_email

logger = logging.getLogger(__name__)


def _content_ready_email_enabled() -> bool:
    """True apenas quando ENVIRONMENT=production.

    Replica a mesma lógica de proteção usada em TIKTOK_DRY_RUN
    (settings.tiktok_dry_run / env var) — aqui o "dry-run" é implícito:
    qualquer ambiente que não seja produção (development, staging, test)
    nunca dispara o envio real de email, evitando ruído/spam durante
    desenvolvimento e execução de testes.
    """
    try:
        env = (getattr(settings, "environment", "") or "").strip().lower()
    except Exception:  # pragma: no cover - defensivo, settings sempre deve existir
        logger.warning("notify_content_ready: não foi possível ler settings.environment.")
        return False
    return env == "production"


async def notify_content_ready(session: AsyncSession, item: ContentItem) -> None:
    """Envia o email de "seu vídeo está pronto" ao dono do escritório do item.

    Deve ser chamado logo após `item.status` ser efetivamente setado para
    `ContentStatus.ready` (a persistência/commit é responsabilidade do
    chamador — esta função só lê dados, nunca decide transação).

    Nunca lança exceção: qualquer erro é logado e engolido, para que uma
    falha de notificação (Resend fora do ar, DB lento, etc.) jamais derrube
    o fluxo principal de processamento de vídeo que a chamou.
    """
    item_id = getattr(item, "id", "?")
    try:
        if not _content_ready_email_enabled():
            logger.info(
                "notify_content_ready: pulado (ENVIRONMENT != production) | item=%s",
                item_id,
            )
            return

        office = await session.get(Office, item.office_id)
        if office is None:
            logger.warning(
                "notify_content_ready: office %s não encontrado | item=%s",
                item.office_id, item_id,
            )
            return

        user = await session.get(User, office.user_id)
        if user is None:
            logger.warning(
                "notify_content_ready: user %s não encontrado | item=%s",
                office.user_id, item_id,
            )
            return

        if not getattr(user, "notify_content_ready", True):
            logger.info(
                "notify_content_ready: opt-out do usuário %s — email não enviado | item=%s",
                user.id, item_id,
            )
            return

        if not user.email:
            logger.warning(
                "notify_content_ready: usuário %s sem email cadastrado | item=%s",
                user.id, item_id,
            )
            return

        frontend_url = (getattr(settings, "frontend_url", "") or "https://viraxis.com.br").rstrip("/")
        content_url = f"{frontend_url}/dashboard/conteudo/{item_id}"

        ok = await send_content_ready_email(
            to=user.email,
            full_name=user.full_name,
            content_title=item.title,
            content_url=content_url,
        )
        if ok:
            logger.info(
                "notify_content_ready: email enviado | item=%s | user=%s",
                item_id, user.id,
            )
        else:
            logger.error(
                "notify_content_ready: falha ao enviar email via Resend | item=%s | user=%s",
                item_id, user.id,
            )

    except Exception as exc:  # noqa: BLE001 — notificação nunca pode derrubar o pipeline
        logger.error(
            "notify_content_ready: exceção inesperada, ignorada | item=%s | %s: %s",
            item_id, type(exc).__name__, exc,
        )
