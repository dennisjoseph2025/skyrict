"""Reconcile report definitions against the canonical seed catalog (RPT-DATA-001).

Migration 0036 seeded ``erp_report_definitions`` with
``ON CONFLICT (tenant_id, slug) DO NOTHING`` - insert-only. When a seed's SQL
evolves in the canonical catalog (``reporting.seeds``), already-provisioned
tenants keep the old definition forever, silently returning stale report
columns (e.g. ``ar_aging`` without ``outstanding``, making the dashboard's
"Open receivables" KPI sum a missing column to ₹0).

This migration makes seeding **reconcile** instead of just insert:

  * a missing definition is inserted (same as 0036);
  * an existing definition whose version is older than the canonical seed, or
    whose stored SQL differs from the canonical seed (after whitespace
    normalization), is updated in place and its ``version`` bumped;
  * identical rows are left untouched (idempotent - stable re-runs).

Every seed is validated read-only and tenant-filtered before it can be
written, exactly as in 0036. The drift predicate mirrors
``reporting.seeds.is_seed_stale`` (which the tenant-provisioning hook uses):
stale means the stored version is older than the seed's, or the stored SQL
differs after whitespace normalization. Both paths classify "in sync"
identically, so re-runs are stable.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-07
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from core.features.reporting.seeds import PHASE_1_REPORT_SEEDS
from core.features.reporting.validation import require_tenant_filter, validate_read_only_sql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def _reconcile_definitions() -> None:
    """Insert missing definitions and refresh drifted ones for every tenant."""
    bind = op.get_bind()
    for seed in PHASE_1_REPORT_SEEDS:
        validate_read_only_sql(seed.sql, seed.params)
        require_tenant_filter(seed.sql)
        bind.execute(
            sa.text(
                """
                INSERT INTO erp_report_definitions
                    (tenant_id, slug, title, module, description, sql, params,
                     permission_key, version)
                SELECT t.id,
                       :slug,
                       :title,
                       :module,
                       :description,
                       :sql,
                       CAST(:params AS jsonb),
                       :permission_key,
                       :version
                  FROM tenants t
                ON CONFLICT (tenant_id, slug) DO UPDATE SET
                       title = EXCLUDED.title,
                       module = EXCLUDED.module,
                       description = EXCLUDED.description,
                       sql = EXCLUDED.sql,
                       params = EXCLUDED.params,
                       permission_key = EXCLUDED.permission_key,
                       version = EXCLUDED.version,
                       updated_at = now()
                 WHERE erp_report_definitions.version < EXCLUDED.version
                    OR btrim(regexp_replace(
                         erp_report_definitions.sql, E'\\s+', ' ', 'g')) <>
                       btrim(regexp_replace(
                         EXCLUDED.sql, E'\\s+', ' ', 'g'))
                """
            ),
            {
                "slug": seed.slug,
                "title": seed.title,
                "module": seed.module,
                "description": seed.description,
                "sql": seed.sql,
                "params": json.dumps(list(seed.params)),
                "permission_key": seed.permission_key,
                "version": seed.version,
            },
        )


def upgrade() -> None:
    _reconcile_definitions()


def downgrade() -> None:
    # No structural change to undo: the reconcile only aligns row content with
    # the canonical catalog. Downgrading restores nothing - a downgrade to 0037
    # leaves the reconciled (canonical) definitions in place, which is the
    # desired forward state for every tenant.
    pass
