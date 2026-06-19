"""Router de Social Accounts — PR-5 Fase 2.

Gerencia as contas de redes sociais vinculadas a escritórios.
Tokens OAuth são armazenados criptografados (Fernet) — nunca expostos na API.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from viraxis.api.deps import get_current_user, get_session
from viraxis.domain.models.social_account import SocialAccount, SocialPlatform
from viraxis.domain.models.user import User
from viraxis.domain.models.office import Office
from viraxis.infrastructure.repositories.social_account import SocialAccountRepository

router = APIRouter(prefix="/social-accounts", tags=["social-accounts"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class SocialAccountCreate(BaseModel):
    platform: str
    platform_username: str
    platform_user_id: str | None = None
    office_id: str | None = None
    # Tokens chegam criptografados do frontend ou via OAuth callback
    access_token_enc: str | None = None
    refresh_token_enc: str | None = None

    @field_validator("platform")
    @classmethod
    def valid_platform(cls, v: str) -> str:
        allowed = {p.value for p in SocialPlatform}
        if v not in allowed:
            raise ValueError(f"Plataforma inválida. Permitidas: {allowed}")
        return v

    @field_validator("platform_username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Username não pode ser vazio")
        return v


class SocialAccountResponse(BaseModel):
    id: str
    platform: str
    platform_username: str
    platform_user_id: str | None
    office_id: str | None
    is_active: bool
    token_expires_at: str | None
    # Tokens NUNCA são retornados — nem hash, nem parcial
    created_at: str
    updated_at: str


class SocialAccountAssign(BaseModel):
    office_id: str | None = None  # None = desassociar do office


# ── Helpers ────────────────────────────────────────────────────────────────────

def _account_to_response(acc: SocialAccount) -> SocialAccountResponse:
    return SocialAccountResponse(
        id=str(acc.id),
        platform=acc.platform.value,
        platform_username=acc.platform_username,
        platform_user_id=acc.platform_user_id,
        office_id=str(acc.office_id) if acc.office_id else None,
        is_active=acc.is_active,
        token_expires_at=(
            acc.token_expires_at.isoformat() if acc.token_expires_at else None
        ),
        created_at=acc.created_at.isoformat() if acc.created_at else "",
        updated_at=acc.updated_at.isoformat() if acc.updated_at else "",
    )


async def _get_account_or_404(
    account_id: UUID, user_id: UUID, session: AsyncSession
) -> SocialAccount:
    result = await session.execute(
        select(SocialAccount).where(
            SocialAccount.id == account_id,
            SocialAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta social não encontrada")
    return account


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SocialAccountResponse])
async def list_social_accounts(
    platform: str | None = Query(None),
    office_id: str | None = Query(None),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista as contas sociais do usuário autenticado."""
    repo = SocialAccountRepository(session)

    if office_id:
        accounts = await repo.list_by_office(
            UUID(office_id),
            platform=SocialPlatform(platform) if platform else None,
            active_only=not include_inactive,
        )
        # Garante que o office pertence ao usuário
        for acc in accounts:
            if acc.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Acesso negado")
    else:
        accounts = await repo.list_by_user(
            current_user.id,
            platform=SocialPlatform(platform) if platform else None,
            active_only=not include_inactive,
        )

    return [_account_to_response(a) for a in accounts]


@router.post("", response_model=SocialAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_social_account(
    body: SocialAccountCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Vincula uma nova conta social ao usuário.

    O token de acesso deve chegar já criptografado com Fernet (pelo frontend
    após OAuth callback). O backend NUNCA recebe tokens em plaintext.
    """
    repo = SocialAccountRepository(session)

    # Verificar duplicata
    existing = await repo.get_by_user_platform_username(
        current_user.id,
        SocialPlatform(body.platform),
        body.platform_username,
    )
    if existing:
        if not existing.is_active:
            # Reativar conta inativa
            existing.is_active = True
            existing.access_token_enc = body.access_token_enc
            existing.refresh_token_enc = body.refresh_token_enc
            await repo.save(existing)
            await session.commit()
            return _account_to_response(existing)
        raise HTTPException(
            status_code=409,
            detail=f"Conta @{body.platform_username} no {body.platform} já está vinculada.",
        )

    # Validar office_id se fornecido
    if body.office_id:
        office_result = await session.execute(
            select(Office).where(
                Office.id == UUID(body.office_id),
                Office.user_id == current_user.id,
            )
        )
        if not office_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Escritório não encontrado")

    account = SocialAccount(
        user_id=current_user.id,
        office_id=UUID(body.office_id) if body.office_id else None,
        platform=SocialPlatform(body.platform),
        platform_username=body.platform_username,
        platform_user_id=body.platform_user_id,
        access_token_enc=body.access_token_enc,
        refresh_token_enc=body.refresh_token_enc,
        is_active=True,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return _account_to_response(account)


@router.get("/{account_id}", response_model=SocialAccountResponse)
async def get_social_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna uma conta social pelo ID."""
    account = await _get_account_or_404(account_id, current_user.id, session)
    return _account_to_response(account)


@router.patch("/{account_id}/assign", response_model=SocialAccountResponse)
async def assign_account_to_office(
    account_id: UUID,
    body: SocialAccountAssign,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Associa ou desassocia uma conta social de um escritório."""
    account = await _get_account_or_404(account_id, current_user.id, session)

    if body.office_id:
        office_result = await session.execute(
            select(Office).where(
                Office.id == UUID(body.office_id),
                Office.user_id == current_user.id,
            )
        )
        if not office_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Escritório não encontrado")
        account.office_id = UUID(body.office_id)
    else:
        account.office_id = None

    session.add(account)
    await session.commit()
    await session.refresh(account)
    return _account_to_response(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_social_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Desativa (soft delete) uma conta social.

    Não deleta do banco — preserva histórico de publicações vinculadas.
    """
    account = await _get_account_or_404(account_id, current_user.id, session)
    repo = SocialAccountRepository(session)
    await repo.deactivate(account)
    await session.commit()
