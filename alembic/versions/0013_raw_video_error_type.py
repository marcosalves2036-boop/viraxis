"""raw_videos: adiciona campo error_type para retry automatico futuro.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-02

Contexto: o endpoint POST /raw-videos/{id}/reanalyze precisa saber por que a
analise anterior falhou (para o frontend exibir mensagem adequada e, no
futuro, decidir se vale a pena tentar de novo automaticamente). O
upload_analyzer ja distingue 3 categorias de falha critica no codigo
(download_failed, timeout, analysis_failed) mas ate aqui so persistia a
mensagem livre em ai_analysis["error"] — sem um campo estruturado e
consultavel via SQL/filtro.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_videos",
        sa.Column(
            "error_type",
            sa.String(length=32),
            nullable=True,
            comment=(
                "Categoria da falha critica de analise: download_failed | timeout | "
                "analysis_failed. Nulo quando status != failed."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("raw_videos", "error_type")
