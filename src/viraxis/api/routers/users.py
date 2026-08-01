"""Router de Users — perfil e senha."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.security import hash_password, verify_password
from viraxis.domain.models.user import User

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

    model_config = {"from_attributes": True}


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        plan=user.plan.value,
        role=user.role.value,
        notify_content_ready=user.notify_content_ready,
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
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Nova senha deve ter ao menos 8 caracteres")
    if len(body.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Nova senha deve ter no maximo 72 caracteres")
    current_user.hashed_password = hash_password(body.new_password)
    session.add(current_user)
    await session.commit()
