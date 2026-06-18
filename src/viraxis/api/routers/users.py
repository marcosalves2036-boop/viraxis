"""Router de Users — perfil e senha."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from viraxis.api.deps import get_current_user, get_session
from viraxis.api.security import hash_password, verify_password
from viraxis.domain.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    full_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    plan: str
    role: str

    model_config = {"from_attributes": True}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        plan=current_user.plan.value,
        role=current_user.role.value,
    )


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    name = body.full_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Nome nao pode ser vazio")
    current_user.full_name = name
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        plan=current_user.plan.value,
        role=current_user.role.value,
    )


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
