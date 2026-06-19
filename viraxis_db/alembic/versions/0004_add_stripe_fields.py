"""Adiciona campos Stripe ao users — PR-8 Fase 2.

Revision ID: 0004_add_stripe_fields
Revises: 0003_content_items_fase2
Create Date: 2025-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_stripe_fields"
down_revision = "0003_content_items_fase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Campos de billing Stripe no users
    op.add_column(
        "users",
        sa.Column(
            "stripe_customer_id",
            sa.String(64),
            nullable=True,
            comment="ID do Customer no Stripe (cus_xxx). Unico por usuario.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "stripe_subscription_id",
            sa.String(64),
            nullable=True,
            comment="ID da Subscription ativa no Stripe (sub_xxx).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "stripe_subscription_status",
            sa.String(32),
            nullable=True,
            comment="Status da subscription: active, past_due, canceled, trialing, etc.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "plan_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Data de expiracao do plano atual. Null = plano free (sem expiracao).",
        ),
    )

    # Indice para lookup rapido por stripe_customer_id (webhook)
    op.create_index(
        "ix_users_stripe_customer_id",
        "users",
        ["stripe_customer_id"],
        unique=True,
        postgresql_where=sa.text("stripe_customer_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "plan_expires_at")
    op.drop_column("users", "stripe_subscription_status")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
