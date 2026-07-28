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
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from viraxis.agents.publisher.caption_generator import generate_caption_sync
from viraxis.agents.publisher.platform_clients import (
    PublishPlatformError,
    publish_to_platform,
    refresh_tiktok_token,
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
from viraxis.infrastructure.token_crypto import decrypt_token as _decrypt_token
from viraxis.infrastructure.token_crypto import encrypt_token as _encrypt_token
from viraxis.infrastructure.video_processor import sign_storage_path

logger = logging.getLogger(__name__)

# Margem de seguranca antes de token_expires_at: se faltar menos que isso,
# tenta renovar o token PROATIVAMENTE em vez de deixar a chamada de publish
# falhar com "token expirado".
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


async def _maybe_refresh_tiktok_token(
    session, account: SocialAccount,
) -> None:
    """Renova o access_token do TikTok se estiver expirado/perto de expirar.

    So atua quando `account.platform` == tiktok e ha refresh_token_enc
    disponivel. Atualiza `account` in-place (access_token_enc,
    refresh_token_enc, token_expires_at) e persiste via `session.flush()`.
    Nao lanca excecao em caso de falha — apenas loga o erro, deixando a
    tentativa de publish seguinte reportar um erro claro (token expirado)
    caso o token antigo realmente nao funcione mais.
    """
    if str(account.platform.value if hasattr(account.platform, "value") else account.platform) != "tiktok":
        return
    if not account.refresh_token_enc:
        return
    if account.token_expires_at is None:
        return
    if account.token_expires_at > datetime.now(timezone.utc) + TOKEN_REFRESH_BUFFER:
        return  # ainda valido por tempo suficiente

    old_refresh = _decrypt_token(account.refresh_token_enc)
    if not old_refresh:
        logger.warning(
            "TikTok refresh_token nao pode ser descriptografado | account=%s — "
            "usuario provavelmente precisa reconectar a conta.",
            account.id,
        )
        return

    try:
        new_tokens = await asyncio.to_thread(refresh_tiktok_token, old_refresh)
        account.access_token_enc = _encrypt_token(new_tokens["access_token"])
        new_refresh = new_tokens.get("refresh_token")
        if new_refresh:
            account.refresh_token_enc = _encrypt_token(new_refresh)
        account.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(new_tokens.get("expires_in", 86400))
        )
        session.add(account)
        await session.flush()
        logger.info(
            "TikTok token renovado com sucesso | account=%s | novo_expires_at=%s",
            account.id, account.token_expires_at,
        )
    except PublishPlatformError as exc:
        logger.error(
            "Falha ao renovar token TikTok | account=%s | erro=%s — "
            "seguindo com o token atual (pode falhar na publicacao).",
            account.id, exc,
        )


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

                # ---- 3b. Renovar token TikTok se expirado/perto de expirar ----
                if target.platform == "tiktok":
                    await _maybe_refresh_tiktok_token(session, account)

                access_token = _decrypt_token(account.access_token_enc)
                if not access_token:
                    results.append(PublishResult(
                        platform=target.platform,
                        social_account_id=target.social_account_id,
                        success=False,
                        error_message="Token de acesso nao disponivel (falha ao descriptografar).",
                    ))
                    continue

                # ---- 3c. Resolver URL de download do video ----
                # TikTok precisa de uma URL http(s) direta (assinada) para
                # baixar o binario do video — item.storage_path e apenas o
                # path relativo no bucket do Supabase, nao uma URL.
                video_source = item.storage_path
                if target.platform == "tiktok" and item.storage_path:
                    try:
                        video_source = await sign_storage_path(item.storage_path)
                    except Exception as exc:
                        logger.error(
                            "Falha ao gerar signed URL do video | item=%s | erro=%s",
                            content_item_id, exc,
                        )
                        results.append(PublishResult(
                            platform=target.platform,
                            social_account_id=target.social_account_id,
                            success=False,
                            error_message=f"Nao foi possivel acessar o video no storage: {exc}",
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
                        video_source,
                        publisher_input.title,
                        full_caption,
                        target.hashtags,
                    )
                    is_dry_run = bool(external_id) and external_id.startswith("tiktok_dryrun_")
                    results.append(PublishResult(
                        platform=target.platform,
                        social_account_id=target.social_account_id,
                        success=True,
                        external_id=external_id,
                        url=url,
                        dry_run=is_dry_run,
                    ))
                    logger.info(
                        "Publicado | platform=%s | external_id=%s | url=%s | dry_run=%s",
                        target.platform, external_id, url, is_dry_run,
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
                pub_entries = [
                    {
                        "platform": r.platform,
                        "external_id": r.external_id,
                        "published_at": datetime.now(timezone.utc).isoformat(),
                        "url": r.url,
                        "dry_run": r.dry_run,
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
