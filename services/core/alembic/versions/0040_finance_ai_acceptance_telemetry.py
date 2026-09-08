"""Finance AI acceptance telemetry (SKY-67): ai_finance_quality_scores + suggestion feature/status.

Widens ``ai_finance_suggestions`` so each row carries the AI feature that
produced it (``account_suggest`` today, per A2 the draft path will use
``draft_entry``) and the unique key becomes (tenant_id, description, feature).
Adds a CHECK so ``status`` can only be pending/accepted/dismissed - the domain
already documented those three values, but nothing enforced them. New
``ai_finance_quality_scores`` persists the per-feature acceptance-rate snapshot
the ``GET /suggestions/quality`` endpoint computes (spec: <30% acceptance flags
low quality so a future review loop can pause/enrich the prompt).

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_finance_suggestions",
        sa.Column(
            "feature",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'account_suggest'"),
        ),
    )
    op.drop_constraint(
        "uq_ai_finance_suggestions_tenant_description",
        "ai_finance_suggestions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_finance_suggestions_tenant_description_feature",
        "ai_finance_suggestions",
        ["tenant_id", "description", "feature"],
    )
    op.create_check_constraint(
        "ck_ai_finance_suggestions_status",
        "ai_finance_suggestions",
        "status IN ('pending', 'accepted', 'dismissed')",
    )

    op.create_table(
        "ai_finance_quality_scores",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("feature", sa.String(16), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("acceptance_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("below_threshold", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "feature",
            "window_days",
            name="uq_ai_finance_quality_scores_feature_window",
        ),
    )
    op.execute("ALTER TABLE public.ai_finance_quality_scores ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_ai_finance_quality_scores ON public.ai_finance_quality_scores "
        "USING (tenant_id = public.current_tenant_id()) "
        "WITH CHECK (tenant_id = public.current_tenant_id())"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_ai_finance_quality_scores "
        "ON public.ai_finance_quality_scores"
    )
    op.execute("ALTER TABLE public.ai_finance_quality_scores DISABLE ROW LEVEL SECURITY")
    op.drop_table("ai_finance_quality_scores")
    op.drop_constraint(
        "ck_ai_finance_suggestions_status",
        "ai_finance_suggestions",
        type_="check",
    )
    op.drop_constraint(
        "uq_ai_finance_suggestions_tenant_description_feature",
        "ai_finance_suggestions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_finance_suggestions_tenant_description",
        "ai_finance_suggestions",
        ["tenant_id", "description"],
    )
    op.drop_column("ai_finance_suggestions", "feature")
