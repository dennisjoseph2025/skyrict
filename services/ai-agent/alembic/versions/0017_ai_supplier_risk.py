"""Add ai_supplier_risk table (SKY-86 / INV-AI-004).

One row per tenant+supplier holding the latest deterministic risk grade that
the supplier-risk engine computed from the supplier's grading-period facts
(``erp_supplier_performance``) plus its quoted lead time (``erp_suppliers``).
``score`` is a 0-1 risk score; ``risk_band`` is the discretised
``low|medium|high`` band the v2 restock formula consumes to stretch the
effective replenishment lead time.

Composite PK ``(tenant_id, supplier_id)`` with a composite FK into core-owned
``erp_suppliers`` (cross-service idiom identical to ``ai_restock_demand_stats``
-> ``erp_products``): tenant_id stays the RLS column and integrity is enforced
by the composite FK.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    """RLS + tenant isolation policy, matching the 0001 convention."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation_{table} ON {table} "
        "USING (tenant_id = public.current_tenant_id())"
    )


def upgrade() -> None:
    op.create_table(
        "ai_supplier_risk",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "score",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "risk_band",
            sa.String(16),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Numeric(4, 3),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["erp_suppliers.tenant_id", "erp_suppliers.id"],
            ondelete="CASCADE",
            name="fk_ai_supplier_risk_supplier_tenant",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_ai_supplier_risk_score_range"),
        sa.CheckConstraint(
            "risk_band IN ('low', 'medium', 'high')", name="ck_ai_supplier_risk_band"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_ai_supplier_risk_confidence_range"
        ),
    )
    op.create_index(
        "idx_ai_supplier_risk_tenant_band",
        "ai_supplier_risk",
        ["tenant_id", "risk_band"],
    )
    _enable_rls("ai_supplier_risk")


def downgrade() -> None:
    op.drop_table("ai_supplier_risk")
