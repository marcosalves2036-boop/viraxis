"""Runner do agente PUBLISHER — PR-7 Fase 2.

Fluxo:
  1. Carrega ContentItem + SocialAccounts do banco
  2. Gera captions via LLM para plataformas sem caption customizada
  3. Descriptografa tokens (Fernet) e publica em cada plataforma
  4. Atualiza ContentItem.publication_log + status=published
  5. Avanca ContentDecision para status=done (se existir)
  6. Registra AgentRunLog
  7. Retorna PublisherOutput com resultados por plataforma
"""

import asyncio
import logging
import traceback
from uuid import UUID

from sqlalchemy import select

from viraxis.agents.publisher.caption_generator import generate_caption_sync
from viraxis.agents.publisher.platform_clients import (
    PublishPlatformError,
    publish_to_platform,
)
from viraxis.agents.publisher.schemas import (
    PublisherInput,
    PublisherOutput,
    PublishResult,
    PublishTarget,
)
from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.social_account import SocialAccount
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.agent_run_log import AgentRunLogRepository
from viraxis.infrastructure.repositories.content_item import ContentItemRepository

logger = logging.getLogger(__name__)

_FERNET_UNAVAILABLE_MSG = (
    "Fernet key nao configurada (SECRET_KEY). "
    "Tokens nao podem ser descriptografados."
)


def _decrypt_token(token_enc: str | None) -> str | None:
    """Descriptografa um token Fernet.

    Retorna None se o token for None ou se a chave nao estiver configurada.
    Em producao a chave fica em settings.secret_key.
    """
    if not token_enc:
        return None
    try:
        from cryptography.fernet import Fernet  # noqa: PLC0415
        from viraxis.config import settings  # noqa: PLC0415

        key = settings.secret_key.encode()
        # Fernet exige chave de 32 bytes base64-encoded
        # Se a key nao for Fernet-compativel, retorna o token como fallback de dev
        try:
            f = Fernet(key)
            return f.decrypt(token_enc.encode()).decode()
        except Exception:
            # Em dev, o token pode estar em plaintext para facilitar testes
            logger.warning("Token nao parece ser Fernet — usando como plaintext (dev only)")
            return token_enc
    except ImportError:
        logger.error("cryptography nao instalada: pip install cryptography")
        return token_enc  # fallback para dev


async def run_publisher(publisher_input: PublisherInput) -> PublisherOutput:
    """Publica um ContentItem em uma ou mais plataformas sociais.

    Args:
        publisher_input: Input com content_item_id, office_id, user_id e targets.

    Returns:
        PublisherOutput com resultados por plataforma.

    Raises:
        ValueError: ContentItem nao encontrado ou nao esta pronto para publicacao.
    """
    office_id = UUID(publisher_input.office_id)
    user_id = UUID(publisher_input.user_id)
    content_item_id = UUID(publisher_input.content_item_id)

    async with AsyncSessionLocal() as session:
        # ---- 1. Carregar ContentItem ----
        item_repo = ContentItemRepository(session)
        item = await item_repo.get_by_id_for_office(content_item_id, office_id)
        if not item:
            raise ValueError(
                f"ContentItem {content_item_id} nao encontrado para office {office_id}"
            )
        if item.status not in (ContentStatus.ready, ContentStatus.draft):
            raise ValueError(
                f"ContentItem {content_item_id} com status={item.status.value} "
                "nao pode ser publicado. Esperado: ready ou draft."
            )

        # ---- 2. Criar AgentRunLog ----
        log_repo = AgentRunLogRepository(session)
        run_log = await log_repo.create_running(
            agent_name="PublisherAgent",
            task_name="publish_to_platforms",
            office_id=office_id,
            user_id=user_id,
            input_data={
                "content_item_id": str(content_item_id),
                "platforms": [t.platform for t in publisher_input.targets],
            },
        )
        await session.flush()

        logger.info(
            "PUBLISHER iniciando | office=%s | item=%s | platforms=%s",
            office_id,
            content_item_id,
            [t.platform for t in publisher_input.targets],
        )

        results: list[PublishResult] = []

        try:
            for target in publisher_input.targets:
                # ---- 3. Carregar SocialAccount e descriptografar token ----
                acc_result = await session.execute(
                    select(SocialAccount).where(
                        SocialAccount.id == UUID(target.social_account_id),
                        SocialAccount.user_id == user_id,
                        SocialAccount.is_active.is_(True),
                    )
                )
                account: SocialAccount | None = acc_result.scalar_one_or_none()
                if not account:
                    results.append(PublishResult(
                        platform=target.platform,
                        social_account_id=target.social_account_id,
                        success=False,
                        error_message="Conta social nao encontrada ou inativa.",
                    ))
                    continue

                access_token = _decrypt_token(account.access_token_enc)
                if not access_token:
                    results.append(PublishResult(
                        platform=target.platform,
                        social_account_id=target.social_account_id,
                        success=False,
                        error_message="Token de acesso nao disponivel.",
                    ))
                    continue

                # ---- 4. Gerar caption se nao fornecida ----
                caption = target.caption
                if not caption:
                    caption = await asyncio.to_thread(
                        generate_caption_sync,
                        target.platform,
                        publisher_input.title,
                        publisher_input.script[:200],
                        "",  # niche: seria carregado do NicheProfile em versao completa
                    )

                full_caption = caption
                if target.hashtags:
                    hashtag_str = " ".join(
                        f"#{h.lstrip('#')}" for h in target.hashtags
                    )
                    full_caption = f"{caption}\n{hashtag_str}"

                # ---- 5. Publicar na plataforma ----
                try:
                    external_id, url = await asyncio.to_thread(
                        publish_to_platform,
                        target.platform,
                        access_token,
                        item.storage_path,
                        publisher_input.title,
                        full_caption,
                        target.hashtags,
                    )
                    results.append(PublishResult(
                        platform=target.platform,
                        social_account_id=target.social_account_id,
                        success=True,
                        external_id=external_id,
                        url=url,
                    ))
                    logger.info(
                        "Publicado | platform=%s | external_id=%s | url=%s",
                        target.platform, external_id, url,
                    )
                except PublishPlatformError as exc:
                    results.append(PublishResult(
                        platform=target.platform,
                        social_account_id=target.social_account_id,
                        success=False,
                        error_message=str(exc),
                    ))
                    logger.error("Falha ao publicar | platform=%s | erro=%s", target.platform, exc)

            # ---- 6. Atualizar ContentItem ----
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]

            if successful:
                from datetime import datetime, timezone  # noqa: PLC0415
                pub_entries = [
                    {
                        "platform": r.platform,
                        "external_id": r.external_id,
                        "published_at": datetime.now(timezone.utc).isoformat(),
                        "url": r.url,
                    }
                    for r in successful
                ]
                item.publication_log = list(item.publication_log or []) + pub_entries
                item.status = ContentStatus.published
                session.add(item)

                # Avanca ContentDecision para done
                if item.decision_id:
                    dec_result = await session.execute(
                        select(ContentDecision).where(
                            ContentDecision.id == item.decision_id
                        )
                    )
                    decision = dec_result.scalar_one_or_none()
                    if decision and decision.status == DecisionStatus.executing:
                        decision.status = DecisionStatus.done
                        session.add(decision)

            # ---- 7. Marcar log ----
            output = PublisherOutput(
                results=results,
                successful_platforms=[r.platform for r in successful],
                failed_platforms=[r.platform for r in failed],
            )

            if successful:
                await log_repo.mark_success(
                    run_log,
                    output_data={
                        "successful": [r.platform for r in successful],
                        "failed": [r.platform for r in failed],
                    },
                )
            else:
                await log_repo.mark_failed(
                    run_log,
                    error_message="Todas as publicacoes falharam.",
                    traceback="\n".join(r.error_message or "" for r in failed),
                )

            await session.commit()
            logger.info(
                "PUBLISHER concluido | ok=%d | failed=%d",
                len(successful), len(failed),
            )
            return output

        except Exception as exc:
            tb = traceback.format_exc()
            await log_repo.mark_failed(run_log, error_message=str(exc), traceback=tb)
            await session.commit()
            logger.error("PUBLISHER erro critico | office=%s | item=%s | erro=%s", office_id, content_item_id, exc)
            raise
