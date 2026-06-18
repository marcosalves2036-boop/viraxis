"""add user role

Revision ID: 0002_add_user_role
Revises: 0001_initial_schema
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_user_role"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Criar o enum type
    userrole = sa.Enum("admin", "user", name="userrole", create_constraint=True)
    userrole.create(op.get_bind(), checkfirst=True)

    # Adicionar coluna com default 'user'
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("admin", "user", name="userrole"),
            nullable=False,
            server_default="user",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS userrole")
