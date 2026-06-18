"""Router de Billing Stripe — PR-8 Fase 2.

Endpoints:
  POST /billing/checkout          — cria Stripe Checkout Session (redirect para pagar)
  POST /billing/portal            — abre Customer Portal (gerenciar/cancelar plano)
  POST /billing/webhook           — recebe eventos Stripe (assinado com HMAC)
  GET  /billing/status            — retorna plano atual + status da subscription

Design de seguranca:
  - Webhook valida assinatura Stripe antes de processar qualquer evento
  - Tokens Stripe nunca expostos na resposta
  - Plano atualizado atomicamente via transacao
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from viraxis.api.deps import get_current_user, get_session
from viraxis.config import settings
from viraxis.domain.models.user import User, UserPlan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

# Mapeamento Price ID -> plano interno
_PRICE_TO_PLAN: dict[str, UserPlan] = {
    settings.stripe_price_pro: UserPlan.pro,
    settings.stripe_price_business: UserPlan.business,
}

# Mapeamento plano -> Price ID para o Checkout
_PLAN_TO_PRICE: dict[str, str] = {
    "pro": settings.stripe_price_pro,
    "business": settings.stripe_price_business,
}


# ── Schemas ────────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "business"
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PortalResponse(BaseModel):
    portal_url: str


class BillingStatusResponse(BaseModel):
    plan: str
    stripe_customer_id: str | None
    subscription_status: str | None
    plan_expires_at: str | None
    is_active_subscription: bool


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_stripe():
    """Importa e configura o SDK Stripe. Lanca se nao instalado."""
    try:
        import stripe  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Billing indisponivel: stripe nao instalado. Execute: pip install stripe",
        ) from exc
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Billing indisponivel: STRIPE_SECRET_KEY nao configurada.",
        )
    stripe.api_key = settings.stripe_secret_key
    return stripe


async def _get_or_create_customer(stripe, user: User, session: AsyncSession) -> str:
    """Retorna o stripe_customer_id do usuario, criando se necessario."""
    # Leitura direta pois o model User nao tem o campo ainda no ORM
    # (campo adicionado via migration — usar raw SQL ate ORM ser atualizado)
    result = await session.execute(
        select(User).where(User.id == user.id)
    )
    db_user = result.scalar_one()

    # Verifica se o campo ja existe na instancia (apos migration)
    customer_id = getattr(db_user, "stripe_customer_id", None)

    if customer_id:
        return customer_id

    # Criar customer no Stripe
    customer = stripe.Customer.create(
        email=user.email,
        name=user.full_name,
        metadata={"user_id": str(user.id)},
    )

    # Persistir stripe_customer_id
    await session.execute(
        User.__table__.update()
        .where(User.id == user.id)
        .values(stripe_customer_id=customer.id)
    )
    await session.flush()

    logger.info("Stripe Customer criado | user=%s | customer=%s", user.id, customer.id)
    return customer.id


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Cria uma Stripe Checkout Session para upgrade de plano.

    O frontend deve redirecionar o usuario para checkout_url.
    Apos pagamento, Stripe envia evento via webhook que atualiza o plano.
    """
    stripe = _get_stripe()

    price_id = _PLAN_TO_PRICE.get(body.plan)
    if not price_id:
        raise HTTPException(
            status_code=422,
            detail=f"Plano invalido: {body.plan}. Opcoes: {list(_PLAN_TO_PRICE.keys())}",
        )
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Price ID para plano '{body.plan}' nao configurado no ambiente.",
        )

    customer_id = await _get_or_create_customer(stripe, current_user, session)
    await session.commit()

    checkout_session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=body.success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=body.cancel_url,
        metadata={"user_id": str(current_user.id), "plan": body.plan},
        subscription_data={
            "metadata": {"user_id": str(current_user.id), "plan": body.plan}
        },
    )

    logger.info(
        "Checkout criado | user=%s | plan=%s | session=%s",
        current_user.id, body.plan, checkout_session.id,
    )
    return CheckoutResponse(
        checkout_url=checkout_session.url,
        session_id=checkout_session.id,
    )


@router.post("/portal", response_model=PortalResponse)
async def create_customer_portal(
    return_url: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Abre o Customer Portal do Stripe (gerenciar/cancelar assinatura)."""
    stripe = _get_stripe()

    customer_id = getattr(current_user, "stripe_customer_id", None)
    if not customer_id:
        # Tentar buscar do banco (campo pode estar na migration mas nao no ORM)
        result = await session.execute(
            select(User.__table__.c.stripe_customer_id).where(User.id == current_user.id)
        )
        row = result.one_or_none()
        customer_id = row[0] if row else None

    if not customer_id:
        raise HTTPException(
            status_code=404,
            detail="Usuario nao possui assinatura Stripe ativa.",
        )

    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return PortalResponse(portal_url=portal_session.url)


@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retorna o plano atual e status da assinatura do usuario."""
    # Busca campos Stripe do banco (podem estar fora do ORM se migration nao rodou)
    result = await session.execute(
        select(
            User.__table__.c.stripe_customer_id,
            User.__table__.c.stripe_subscription_id,
            User.__table__.c.stripe_subscription_status,
            User.__table__.c.plan_expires_at,
        ).where(User.id == current_user.id)
    )
    row = result.one_or_none()

    if row:
        customer_id, sub_id, sub_status, expires_at = row
    else:
        customer_id = sub_id = sub_status = expires_at = None

    is_active = sub_status in ("active", "trialing") if sub_status else False

    return BillingStatusResponse(
        plan=current_user.plan.value,
        stripe_customer_id=customer_id,
        subscription_status=sub_status,
        plan_expires_at=expires_at.isoformat() if expires_at else None,
        is_active_subscription=is_active,
    )


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    session: AsyncSession = Depends(get_session),
):
    """Recebe e processa eventos do Stripe via webhook.

    Valida assinatura HMAC antes de qualquer processamento.
    Eventos suportados:
      - checkout.session.completed
      - customer.subscription.updated
      - customer.subscription.deleted
      - invoice.payment_failed
    """
    stripe = _get_stripe()

    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="STRIPE_WEBHOOK_SECRET nao configurado.",
        )

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Webhook com assinatura invalida rejeitado")
        raise HTTPException(status_code=400, detail="Assinatura invalida")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook | type=%s | id=%s", event_type, event.get("id"))

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, session)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, session)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, session)

    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data, session)

    else:
        logger.debug("Evento nao tratado: %s", event_type)

    await session.commit()
    return {"received": True}


# ── Handlers de eventos ────────────────────────────────────────────────────────

async def _handle_checkout_completed(data: dict, session: AsyncSession) -> None:
    """checkout.session.completed — upgrade de plano apos pagamento."""
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")
    plan_name = data.get("metadata", {}).get("plan", "pro")

    new_plan = UserPlan(plan_name) if plan_name in UserPlan._value2member_map_ else UserPlan.pro

    await session.execute(
        User.__table__.update()
        .where(User.__table__.c.stripe_customer_id == customer_id)
        .values(
            plan=new_plan.value,
            stripe_subscription_id=subscription_id,
            stripe_subscription_status="active",
        )
    )
    logger.info(
        "Plano atualizado via checkout | customer=%s | plan=%s | sub=%s",
        customer_id, new_plan.value, subscription_id,
    )


async def _handle_subscription_updated(data: dict, session: AsyncSession) -> None:
    """customer.subscription.updated — mudanca de status ou plano."""
    customer_id = data.get("customer")
    sub_status = data.get("status")
    items = data.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None

    updates: dict = {"stripe_subscription_status": sub_status}

    if price_id and price_id in _PRICE_TO_PLAN:
        updates["plan"] = _PRICE_TO_PLAN[price_id].value

    # Se cancelado ou expirado, rebaixar para free
    if sub_status in ("canceled", "unpaid", "incomplete_expired"):
        updates["plan"] = UserPlan.free.value

    await session.execute(
        User.__table__.update()
        .where(User.__table__.c.stripe_customer_id == customer_id)
        .values(**updates)
    )
    logger.info(
        "Subscription atualizada | customer=%s | status=%s | price=%s",
        customer_id, sub_status, price_id,
    )


async def _handle_subscription_deleted(data: dict, session: AsyncSession) -> None:
    """customer.subscription.deleted — rebaixa para plano free."""
    customer_id = data.get("customer")
    await session.execute(
        User.__table__.update()
        .where(User.__table__.c.stripe_customer_id == customer_id)
        .values(
            plan=UserPlan.free.value,
            stripe_subscription_status="canceled",
            stripe_subscription_id=None,
        )
    )
    logger.info("Subscription cancelada | customer=%s | plan=free", customer_id)


async def _handle_payment_failed(data: dict, session: AsyncSession) -> None:
    """invoice.payment_failed — atualiza status para past_due."""
    customer_id = data.get("customer")
    await session.execute(
        User.__table__.update()
        .where(User.__table__.c.stripe_customer_id == customer_id)
        .values(stripe_subscription_status="past_due")
    )
    logger.warning("Pagamento falhou | customer=%s | status=past_due", customer_id)
