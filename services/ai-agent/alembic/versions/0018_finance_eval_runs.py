"""ai_finance_eval_runs - finance prompt-eval results (FIN-AI-002).

One row per evaluated feature (a1_suggest / a2_draft / a7_narrate / a8_remind)
per nightly run. Global (not tenant-scoped) like ``ai_eval_runs``: prompt
quality is a cross-tenant signal, so no tenant_id column and no RLS policy.
Append-only; the nightly workflow inserts rows and nobody reads them yet
(warn-not-fail). The ``passed`` column carries the per-feature verdict
against the registry threshold; ``details`` holds per-case scores for
drill-down.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_finance_eval_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("feature", sa.String(16), nullable=False),
        sa.Column("prompt_id", sa.String(100), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=False, server_default=sa.text("''")),
        sa.Column("considered", sa.Integer(), nullable=False),
        sa.Column("abstained", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("precision", sa.Numeric(5, 4), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_index(
        "idx_finance_eval_runs_run_at",
        "ai_finance_eval_runs",
        [sa.text("run_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_finance_eval_runs_run_at", table_name="ai_finance_eval_runs")
    op.drop_table("ai_finance_eval_runs")
