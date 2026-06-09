"""Initial schema — 9 tabelas VIRAXIS Phase 1.

Revision ID: 0001
Revises: (base)
Create Date: 2026-06-08

Tabelas criadas nesta migration:
  users, offices, niche_profiles, content_decisions,
  content_items, trend_snapshots, social_accounts,
  performance_metrics, agent_run_logs
"""

from __future__ import annotations

import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ENUMs são criados automaticamente pelo SQLAlchemy ao criar as tabelas
    # ------------------------------------------------------------------ #
    # TABLE: users                                                        #
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("plan", sa.Enum("free", "pro", "business", name="userplan"), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        comment="Contas de usuário — raiz da hierarquia multi-tenant.",
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ------------------------------------------------------------------ #
    # TABLE: offices                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "offices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("niche", sa.String(128), nullable=False),
        sa.Column("status", sa.Enum("active", "paused", "archived", name="officestatus"), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_offices_user_id", ondelete="CASCADE"),
        comment="Escritórios virtuais — cada um opera em um nicho específico.",
    )
    op.create_index("ix_offices_user_id", "offices", ["user_id"])
    op.create_index("ix_offices_user_status", "offices", ["user_id", "status"])

    # ------------------------------------------------------------------ #
    # TABLE: niche_profiles                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "niche_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("niche_name", sa.String(128), nullable=False),
        sa.Column("target_platforms", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("viral_archetypes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("content_style", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("top_keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("brain_params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_niche_profiles_office_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_niche_profiles_user_id", ondelete="CASCADE"),
        sa.UniqueConstraint("office_id", name="uq_niche_profiles_office_id"),
        comment="Perfil de nicho — inteligência acumulada por escritório.",
    )
    op.create_index("ix_niche_profiles_user_id", "niche_profiles", ["user_id"])
    op.create_index("ix_niche_profiles_office_user", "niche_profiles", ["office_id", "user_id"])

    # ------------------------------------------------------------------ #
    # TABLE: content_decisions                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "content_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_type", sa.Enum("content_topic", "archetype_selection", "platform_targeting", "repost_strategy", "pause_office", name="decisiontype"), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "executing", "done", "rejected", "failed", name="decisionstatus"), nullable=False, server_default="pending"),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("reasoning", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("selected_archetype", sa.String(128), nullable=True),
        sa.Column("selected_topic", sa.String(512), nullable=True),
        sa.Column("selected_platform", sa.String(64), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("input_signals", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_content_decisions_office_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_content_decisions_user_id", ondelete="CASCADE"),
        comment="Decisões documentadas do BRAIN — diferencial core do produto.",
    )
    op.create_index("ix_content_decisions_office_status", "content_decisions", ["office_id", "status"])
    op.create_index("ix_content_decisions_user_id", "content_decisions", ["user_id"])
    op.create_index("ix_content_decisions_created_at", "content_decisions", ["created_at"])

    # ------------------------------------------------------------------ #
    # TABLE: content_items                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("draft", "rendering", "ready", "published", "failed", name="contentstatus"), nullable=False, server_default="draft"),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("thumbnail_path", sa.String(1024), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("production_meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("publication_log", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_content_items_office_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_content_items_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["content_decisions.id"], name="fk_content_items_decision_id", ondelete="SET NULL"),
        comment="Vídeos produzidos — rastreia decisão, roteiro, artefatos e publicação.",
    )
    op.create_index("ix_content_items_office_status", "content_items", ["office_id", "status"])
    op.create_index("ix_content_items_user_id", "content_items", ["user_id"])
    op.create_index("ix_content_items_decision_id", "content_items", ["decision_id"])

    # ------------------------------------------------------------------ #
    # TABLE: trend_snapshots                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "trend_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Enum("scout_url", "vault_upload", "manual_input", name="trendsource"), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("processed_signals", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("transcription", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_trend_snapshots_office_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_trend_snapshots_user_id", ondelete="CASCADE"),
        comment="Sinais de tendência coletados — imutáveis, preservam histórico.",
    )
    op.create_index("ix_trend_snapshots_office_captured", "trend_snapshots", ["office_id", "captured_at"])
    op.create_index("ix_trend_snapshots_user_id", "trend_snapshots", ["user_id"])
    op.create_index("ix_trend_snapshots_source", "trend_snapshots", ["source"])

    # ------------------------------------------------------------------ #
    # TABLE: social_accounts                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "social_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("platform", sa.Enum("tiktok", "instagram", "youtube", "kwai", name="socialplatform"), nullable=False),
        sa.Column("platform_username", sa.String(128), nullable=False),
        sa.Column("platform_user_id", sa.String(256), nullable=True),
        sa.Column("access_token_enc", sa.String(2048), nullable=True),
        sa.Column("refresh_token_enc", sa.String(2048), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_social_accounts_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_social_accounts_office_id", ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "platform", "platform_username", name="uq_social_accounts_user_platform_username"),
        comment="Contas sociais vinculadas — tokens criptografados em aplicação.",
    )
    op.create_index("ix_social_accounts_user_id", "social_accounts", ["user_id"])
    op.create_index("ix_social_accounts_office_platform", "social_accounts", ["office_id", "platform"])

    # ------------------------------------------------------------------ #
    # TABLE: performance_metrics                                          #
    # ------------------------------------------------------------------ #
    op.create_table(
        "performance_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("content_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.Enum("tiktok", "instagram", "youtube", "kwai", name="socialplatform"), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("likes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("comments", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("shares", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("saves", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("watch_time_seconds", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], name="fk_perf_metrics_content_item_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_perf_metrics_office_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_perf_metrics_user_id", ondelete="CASCADE"),
        comment="Snapshots de métricas por conteúdo/plataforma — imutáveis.",
    )
    op.create_index("ix_perf_metrics_content_item", "performance_metrics", ["content_item_id", "recorded_at"])
    op.create_index("ix_perf_metrics_office_platform", "performance_metrics", ["office_id", "platform"])
    op.create_index("ix_perf_metrics_user_id", "performance_metrics", ["user_id"])

    # ------------------------------------------------------------------ #
    # TABLE: agent_run_logs                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("task_name", sa.String(256), nullable=False),
        sa.Column("celery_task_id", sa.String(256), nullable=True),
        sa.Column("status", sa.Enum("queued", "running", "success", "failed", "retrying", "cancelled", name="agentrunstatus"), nullable=False, server_default="queued"),
        sa.Column("input_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_agent_run_logs_office_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_agent_run_logs_user_id", ondelete="SET NULL"),
        sa.UniqueConstraint("celery_task_id", name="uq_agent_run_logs_celery_task_id"),
        comment="Log de execução de agentes — base do painel de observabilidade.",
    )
    op.create_index("ix_agent_run_logs_office_status", "agent_run_logs", ["office_id", "status"])
    op.create_index("ix_agent_run_logs_user_id", "agent_run_logs", ["user_id"])
    op.create_index("ix_agent_run_logs_agent_name", "agent_run_logs", ["agent_name"])
    op.create_index("ix_agent_run_logs_started_at", "agent_run_logs", ["started_at"])


def downgrade() -> None:
    # Ordem reversa — respeita FKs
    op.drop_table("agent_run_logs")
    op.drop_table("performance_metrics")
    op.drop_table("social_accounts")
    op.drop_table("trend_snapshots")
    op.drop_table("content_items")
    op.drop_table("content_decisions")
    op.drop_table("niche_profiles")
    op.drop_table("offices")
    op.drop_table("users")

    # Drop enums
    for enum_name in [
        "agentrunstatus", "socialplatform", "trendsource",
        "contentstatus", "decisionstatus", "decisiontype",
        "officestatus", "userplan",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
