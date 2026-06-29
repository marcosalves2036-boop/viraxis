"""NicheProfile.niche_name: String(128) → Text.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-29

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "niche_profiles",
        "niche_name",
        existing_type=sa.String(128),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "niche_profiles",
        "niche_name",
        existing_type=sa.Text(),
        type_=sa.String(128),
        existing_nullable=False,
    )
