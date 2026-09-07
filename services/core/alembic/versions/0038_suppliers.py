"""Supplier master + supplier performance facts (INV-AI-004, SKY-86).

Suppliers are new ERP domain data (there was no vendor concept in the inventory
module). Two tenant-scoped, RLS-protected tables:

- ``erp_suppliers`` - the supplier master (soft-deletable via ``is_active``),
  composite PK ``(tenant_id, id)`` per the 0001 convention, name unique per
  tenant.
- ``erp_supplier_performance`` - one row per supplier per grading period with
  the raw dimension facts the risk-scoring engine consumes (on-time delivery
  %, defect %, price-stability index 0-100, responsiveness in days). Facts are
  stored, not recomputed, so a score change is auditable against its inputs;
  one period row per supplier per period (unique on
  ``(tenant_id, supplier_id, period_start, period_end)``).

``erp_products.supplier_id`` links each product to its default supplier
(nullable; existing products are unaffected). This lets the ai-agent restock
scan weight reorder timing by supplier risk without touching the composite-FK
convention - the FK includes ``tenant_id`` so referential integrity agrees with
RLS.

Permissions seeded (following the ``erp.inventory.cost`` pattern of 0037):
``erp.inventory.suppliers.read`` gates listing suppliers/performance (the
ai-agent supplier scan forwards this capability); writes reuse the module-level
``erp.inventory.write``.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

_TENANT_SCOPED_TABLES = ("erp_suppliers", "erp_supplier_performance")

_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (
        "erp.inventory.suppliers.read",
        "View suppliers and their performance facts in inventory reports",
    ),
    (
        "erp.inventory.suppliers.write",
        "Create, update, and deactivate suppliers in the ERP catalog",
    ),
)


def upgrade() -> None:
    op.create_table(
        "erp_suppliers",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_erp_suppliers_tenant_name"),
        sa.CheckConstraint("lead_time_days >= 0", name="ck_erp_suppliers_lead_time_non_negative"),
    )

    op.create_table(
        "erp_supplier_performance",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "on_time_delivery_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("defect_rate_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "price_stability_index",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "responsiveness_days",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["erp_suppliers.tenant_id", "erp_suppliers.id"],
            ondelete="CASCADE",
            name="fk_erp_supplier_performance_supplier_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "supplier_id",
            "period_start",
            "period_end",
            name="uq_erp_supplier_performance_period",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_erp_supplier_performance_period_range",
        ),
        sa.CheckConstraint(
            "on_time_delivery_pct >= 0 AND on_time_delivery_pct <= 100",
            name="ck_erp_supplier_performance_otd_range",
        ),
        sa.CheckConstraint(
            "defect_rate_pct >= 0 AND defect_rate_pct <= 100",
            name="ck_erp_supplier_performance_defect_range",
        ),
        sa.CheckConstraint(
            "price_stability_index >= 0 AND price_stability_index <= 100",
            name="ck_erp_supplier_performance_price_range",
        ),
        sa.CheckConstraint(
            "responsiveness_days >= 0",
            name="ck_erp_supplier_performance_responsiveness_non_negative",
        ),
    )
    op.create_index(
        "ix_erp_supplier_performance_tenant_supplier_period",
        "erp_supplier_performance",
        ["tenant_id", "supplier_id", "period_start"],
    )

    # Link products to a default supplier (nullable convenience, not a new ERP
    # module): the ai-agent reorder scan reads it to weight timing by risk.
    op.add_column(
        "erp_products",
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_erp_products_supplier_tenant",
        "erp_products",
        "erp_suppliers",
        ["tenant_id", "supplier_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    # --- Row-Level Security policies ---
    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON public.{table} "
            "USING (tenant_id = public.current_tenant_id()) "
            "WITH CHECK (tenant_id = public.current_tenant_id())"
        )

    for key, description in _PERMISSIONS:
        op.execute(
            "INSERT INTO core_permissions (key, description) VALUES "
            f"('{key}', '{description}') ON CONFLICT (key) DO NOTHING"  # nosec B608
        )


def downgrade() -> None:
    for key, _ in _PERMISSIONS:
        op.execute(f"DELETE FROM core_permissions WHERE key = '{key}'")  # nosec B608

    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON public.{table}")

    op.drop_constraint("fk_erp_products_supplier_tenant", "erp_products", type_="foreignkey")
    op.drop_column("erp_products", "supplier_id")

    op.drop_index(
        "ix_erp_supplier_performance_tenant_supplier_period",
        table_name="erp_supplier_performance",
    )
    op.drop_table("erp_supplier_performance")
    op.drop_table("erp_suppliers")
