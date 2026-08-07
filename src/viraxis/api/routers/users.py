"""Router de Users — perfil, senha e progresso do onboarding travado."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.security import hash_password, verify_password
from viraxis.domain.models.content_decision import ContentDecision
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus
from viraxis.domain.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    notify_content_ready: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    plan: str
    role: str
    notify_content_ready: bool
    onboarding_completed: bool

    model_config = {"from_attributes": True}


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        plan=user.plan.value,
        role=user.role.value,
        notify_content_ready=user.notify_content_ready,
        onboarding_completed=user.onboarding_completed_at is not None,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return _to_user_response(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Atualiza perfil do usuário.

    `notify_content_ready` controla o opt-out do email de "vídeo pronto"
    (disparado quando um ContentItem transiciona para status=ready) — ver
    viraxis.infrastructure.notifications.notify_content_ready.
    """
    if body.full_name is not None:
        name = body.full_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Nome nao pode ser vazio")
        current_user.full_name = name
    if body.notify_content_ready is not None:
        current_user.notify_content_ready = body.notify_content_ready
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return _to_user_response(current_user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Troca a senha do usuário autenticado.

    Nota de verbo HTTP (BACKLOG P2, fonte: qa, 2026-07-29): specs antigas
    descreviam este endpoint como `PUT /me/password`; o contrato real e
    estável, consumido pelo proxy Next.js (`app/api/users/me/password/
    route.ts`) e coberto por `tests/test_auth.py::TestChangePassword`, é
    `POST /users/me/password`. Confirmado em 2026-08-06 que não há
    divergência funcional — só a documentação antiga estava desatualizada.
    """
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Nova senha deve ter ao menos 8 caracteres")
    if len(body.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Nova senha deve ter no maximo 72 caracteres")
    current_user.hashed_password = hash_password(body.new_password)
    session.add(current_user)
    await session.commit()


# ── Onboarding travado (gate de primeiro uso) ─────────────────────────────────
#
# Não pulável: primeiro upload -> primeira decisão do BRAIN -> primeiro vídeo
# pronto. O progresso NUNCA é setado manualmente pelo frontend — é derivado a
# cada chamada a partir dos eventos reais do pipeline (RawVideo.status=ready,
# existência de ContentDecision, ContentItem.status em ready/published) e
# depois espelhado nos campos persistidos do User (ver domain/models/user.py).

class OnboardingStatusResponse(BaseModel):
    has_uploaded_video: bool
    has_brain_decision: bool
    has_ready_content: bool
    completed: bool
    completed_at: str | None
    current_step: int
    total_steps: int = 3


async def _compute_onboarding_progress(
    current_user: User, session: AsyncSession
) -> tuple[bool, bool, bool]:
    """Deriva o progresso real do onboarding a partir do pipeline.

    Escopo: todos os escritórios do usuário (RawVideo/ContentDecision/
    ContentItem carregam `user_id` diretamente, sem precisar juntar Office).
    Usa EXISTS para não trazer linhas — barato mesmo com histórico grande.
    """
    has_uploaded = await session.scalar(
        select(
            exists().where(
                RawVideo.user_id == current_user.id,
                RawVideo.status == RawVideoStatus.ready,
            )
        )
    )
    has_decision = await session.scalar(
        select(
            exists().where(ContentDecision.user_id == current_user.id)
        )
    )
    has_ready = await session.scalar(
        select(
            exists().where(
                ContentItem.user_id == current_user.id,
                ContentItem.status.in_(
                    (ContentStatus.ready, ContentStatus.published)
                ),
                ContentItem.deleted_at.is_(None),
            )
        )
    )
    return bool(has_uploaded), bool(has_decision), bool(has_ready)


@router.get("/me/onboarding", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Estado atual do onboarding travado do usuário.

    Consultado pelo gate do frontend em toda navegação do dashboard enquanto
    `completed=false`. Recalcula o progresso real (não confia em cache
    obsoleto) e persiste o snapshot + a data de conclusão na primeira vez que
    os 3 marcos são atingidos, para o gate nunca reaparecer depois.
    """
    has_uploaded, has_decision, has_ready = await _compute_onboarding_progress(
        current_user, session
    )

    changed = False
    if current_user.has_uploaded_video != has_uploaded:
        current_user.has_uploaded_video = has_uploaded
        changed = True
    if current_user.has_brain_decision != has_decision:
        current_user.has_brain_decision = has_decision
        changed = True
    if current_user.has_ready_content != has_ready:
        current_user.has_ready_content = has_ready
        changed = True

    all_done = has_uploaded and has_decision and has_ready
    if all_done and current_user.onboarding_completed_at is None:
        current_user.onboarding_completed_at = datetime.now(timezone.utc)
        changed = True
        logger.info("Onboarding concluído | user_id=%s", current_user.id)

    if changed:
        session.add(current_user)
        await session.commit()
        await session.refresh(current_user)

    completed = current_user.onboarding_completed_at is not None
    if completed:
        current_step = 4
    elif not has_uploaded:
        current_step = 1
    elif not has_decision:
        current_step = 2
    else:
        current_step = 3

    return OnboardingStatusResponse(
        has_uploaded_video=current_user.has_uploaded_video,
        has_brain_decision=current_user.has_brain_decision,
        has_ready_content=current_user.has_ready_content,
        completed=completed,
        completed_at=(
            current_user.onboarding_completed_at.isoformat()
            if current_user.onboarding_completed_at
            else None
        ),
        current_step=current_step,
    )
