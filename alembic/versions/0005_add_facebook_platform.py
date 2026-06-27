"""add facebook to socialplatform enum

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-23
"""
from alembic import op

revision = "0005"
down_revision = "0004_add_stripe_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE socialplatform ADD VALUE IF NOT EXISTS 'facebook'")


def downgrade() -> None:
    pass
