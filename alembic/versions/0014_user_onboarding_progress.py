"""users: adiciona progresso persistido do onboarding travado (gate primeiro uso).

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-04

Contexto: hoje um usuário novo cai direto no dashboard vazio, sem nenhum gate,
enquanto a landing já vende 3 planos pagos — risco de chargeback (ver
vault/06-marca/viraxis-marca.md). Esta migration adiciona os campos usados
pelo endpoint GET /users/me/onboarding para travar a navegação até o usuário
completar: primeiro upload -> primeira decisão do BRAIN -> primeiro vídeo
pronto. Os três booleanos são espelhos persistidos de estado real do pipeline
(recalculados a cada consulta a partir de RawVideo/ContentDecision/
ContentItem — não são checkboxes manuais). `onboarding_completed_at` fixa a
conclusão permanentemente na primeira vez que os 3 marcos são atingidos.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "has_uploaded_video",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True quando existe ao menos um RawVideo status=ready do usuário (qualquer escritório).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "has_brain_decision",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True quando existe ao menos uma ContentDecision criada pelo BRAIN para o usuário.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "has_ready_content",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True quando existe ao menos um ContentItem status=ready/published do usuário.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "onboarding_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Preenchido uma única vez quando os 3 marcos acima são atingidos. Trava o gate como concluído para sempre.",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "has_ready_content")
    op.drop_column("users", "has_brain_decision")
    op.drop_column("users", "has_uploaded_video")
