"""Router de autenticacao: register + login + verificação de email."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from viraxis.api.deps import get_session
from viraxis.api.security import create_access_token, hash_password, verify_password
from viraxis.config import settings
from viraxis.infrastructure.email import send_verification_email, send_password_reset_email
from viraxis.infrastructure.repositories.user import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Token de verificação: JWT de curta duração com purpose claim
_VERIFY_PURPOSE = "email-verification"
_RESET_PURPOSE = "password-reset"
_VERIFY_EXPIRE_HOURS = 24
_RESET_EXPIRE_HOURS = 1


# ── Helpers de token ───────────────────────────────────────────────────────────

def _create_purpose_token(user_id: str, email: str, purpose: str, expire_hours: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
    return jwt.encode(
        {"sub": user_id, "email": email, "purpose": purpose, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _decode_purpose_token(token: str, expected_purpose: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    if payload.get("purpose") != expected_purpose:
        raise HTTPException(status_code=400, detail="Token inválido")
    return payload


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Senha deve ter pelo menos 8 caracteres")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Senha deve ter no máximo 72 caracteres")
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome nao pode ser vazio")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Senha deve ter pelo menos 8 caracteres")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Senha deve ter no máximo 72 caracteres")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    """Cria conta e envia email de verificação. Login só permitido após verificar."""
    import traceback as _tb
    try:
        return await _register_impl(body, session)
    except HTTPException:
        raise
    except Exception as _e:
        logger.error("REGISTER UNHANDLED EXCEPTION: %s\n%s", _e, _tb.format_exc())
        raise HTTPException(status_code=500, detail=f"DEBUG: {type(_e).__name__}: {_e}\n{_tb.format_exc()}")

async def _register_impl(body: RegisterRequest, session: AsyncSession):
    repo = UserRepository(session)

    existing = await repo.get_by_email(body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado")

    try:
        user = await repo.create_user(
            email=body.email,
            hashed_password=hash_password(body.password),
            full_name=body.full_name,
        )
        # is_verified = False por padrão (server_default no model)
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado")

    # Enviar email de verificação
    token = _create_purpose_token(str(user.id), user.email, _VERIFY_PURPOSE, _VERIFY_EXPIRE_HOURS)
    sent = await send_verification_email(user.email, user.full_name, token)
    if not sent:
        logger.warning("Falha ao enviar email de verificação para %s", user.email)

    return MessageResponse(
        message="Conta criada! Verifique seu email para ativar a conta."
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    repo = UserRepository(session)
    user = await repo.get_by_email(body.email)

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha incorretos")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta desativada")

    if not getattr(user, "is_verified", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email não verificado. Verifique sua caixa de entrada ou reenvie o link.",
        )

    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest, session: AsyncSession = Depends(get_session)
):
    """Ativa a conta após o usuário clicar no link do email."""
    payload = _decode_purpose_token(body.token, _VERIFY_PURPOSE)
    repo = UserRepository(session)
    user = await repo.get_by_email(payload["email"])

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if getattr(user, "is_verified", False):
        return MessageResponse(message="Email já verificado. Faça login.")

    user.is_verified = True  # type: ignore[attr-defined]
    session.add(user)
    await session.commit()
    logger.info("Email verificado: %s", user.email)

    return MessageResponse(message="Email verificado com sucesso! Agora você pode fazer login.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    body: ResendVerificationRequest, session: AsyncSession = Depends(get_session)
):
    """Reenvia o email de verificação."""
    repo = UserRepository(session)
    user = await repo.get_by_email(body.email)

    # Resposta genérica para não revelar se o email existe
    if not user or getattr(user, "is_verified", True):
        return MessageResponse(message="Se o email existir e não estiver verificado, um novo link foi enviado.")

    token = _create_purpose_token(str(user.id), user.email, _VERIFY_PURPOSE, _VERIFY_EXPIRE_HOURS)
    await send_verification_email(user.email, user.full_name, token)

    return MessageResponse(message="Se o email existir e não estiver verificado, um novo link foi enviado.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_session)
):
    """Envia email de redefinição de senha."""
    repo = UserRepository(session)
    user = await repo.get_by_email(body.email)

    if user and user.is_active:
        token = _create_purpose_token(str(user.id), user.email, _RESET_PURPOSE, _RESET_EXPIRE_HOURS)
        await send_password_reset_email(user.email, user.full_name, token)

    return MessageResponse(message="Se o email estiver cadastrado, você receberá o link em breve.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest, session: AsyncSession = Depends(get_session)
):
    """Redefine a senha usando o token recebido por email."""
    payload = _decode_purpose_token(body.token, _RESET_PURPOSE)
    repo = UserRepository(session)
    user = await repo.get_by_email(payload["email"])

    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.hashed_password = hash_password(body.new_password)
    session.add(user)
    await session.commit()
    logger.info("Senha redefinida: %s", user.email)

    return MessageResponse(message="Senha redefinida com sucesso! Faça login com a nova senha.")
