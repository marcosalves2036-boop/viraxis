"""Office.niche: String(128) → Text (sem limite de tamanho).

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-29

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "offices",
        "niche",
        existing_type=sa.String(128),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "offices",
        "niche",
        existing_type=sa.Text(),
        type_=sa.String(128),
        existing_nullable=False,
    )
