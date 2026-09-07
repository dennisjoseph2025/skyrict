"""Run predictions: drift threshold on payroll settings (HR-AUT-002, Commit 1).

Adds ``prediction_drift_threshold_pct`` to ``erp_payroll_settings`` - the
per-tenant threshold (as a decimal fraction, 0.1000 = 10%) past which a
department's projected net vs the previous period is flagged as drift in the
run-prediction API.

The threshold lives on settings (one row per tenant, like pf/tax rates) so a
tenant can tighten it without a code change. Predictions are advisory-only:
drift never blocks a commit at the backend, the acknowledgment guardrail is the
UI's. If a tenant ever wants drift to hard-gate enqueue, the upgrade path is a
``drift_block_pct`` pre-flight block at enqueue time (ponytail: note in the
prediction service) - deliberately not built now.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "erp_payroll_settings",
        sa.Column(
            "prediction_drift_threshold_pct",
            sa.Numeric(6, 4),
            nullable=False,
            server_default=sa.text("0.1000"),
        ),
    )


def downgrade() -> None:
    op.drop_column("erp_payroll_settings", "prediction_drift_threshold_pct")
