"""users: adiciona notify_content_ready (opt-out de email quando video fica pronto).

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_content_ready",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment=(
                "Opt-out de notificacoes por email quando um ContentItem fica "
                "pronto (status=ready). True (padrao) = recebe o email. "
                "False = usuario desabilitou este tipo de notificacao."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_content_ready")
