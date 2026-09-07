"""Currency FX for invoices (SKY-67 C2): erp_exchange_rates + invoice currency columns.

Spec C2 "FX line item amounts": an invoice is created in one currency, priced in
that currency, and carries the exchange rate against the tenant's default
currency. Nothing is silently converted - the dialog confirms the currency and
the rate before creating, and journal entries never auto-write FX amounts. This
migration adds the per-tenant rate store and the two invoice columns; the FX
permissions seed ``core_permissions`` so tenants can be granted
``core.fx.read``/``core.fx.write``.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_FX_PERMISSIONS = (
    ("core.fx.read", "Look up exchange rates and invoice FX context"),
    ("core.fx.write", "Enter or update tenant exchange rates"),
)


def upgrade() -> None:
    op.create_table(
        "erp_exchange_rates",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column(
            "rate",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.CheckConstraint(
            "base_currency <> quote_currency",
            name="ck_erp_exchange_rates_distinct_currencies",
        ),
        sa.CheckConstraint("rate > 0", name="ck_erp_exchange_rates_positive"),
        sa.ForeignKeyConstraint(
            ("base_currency",), ["erp_currencies.code"], name="fk_erp_exchange_rates_base"
        ),
        sa.ForeignKeyConstraint(
            ("quote_currency",),
            ["erp_currencies.code"],
            name="fk_erp_exchange_rates_quote",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "base_currency", "quote_currency", "effective_date"
        ),
    )
    op.execute("ALTER TABLE public.erp_exchange_rates ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_erp_exchange_rates ON public.erp_exchange_rates "
        "USING (tenant_id = public.current_tenant_id()) "
        "WITH CHECK (tenant_id = public.current_tenant_id())"
    )

    op.add_column(
        "erp_invoices",
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'USD'"),
        ),
    )
    op.add_column(
        "erp_invoices",
        sa.Column(
            "exchange_rate",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_foreign_key(
        "fk_erp_invoices_currency",
        "erp_invoices",
        "erp_currencies",
        ["currency"],
        ["code"],
    )
    op.create_check_constraint(
        "ck_erp_invoices_exchange_rate_positive",
        "erp_invoices",
        "exchange_rate > 0",
    )

    for key, description in _FX_PERMISSIONS:
        op.execute(
            "INSERT INTO core_permissions (key, description) VALUES "
            f"('{key}', '{description}') ON CONFLICT (key) DO NOTHING"  # nosec B608
        )


def downgrade() -> None:
    for key, _description in _FX_PERMISSIONS:
        op.execute(f"DELETE FROM core_permissions WHERE key = '{key}'")  # nosec B608

    op.drop_constraint(
        "ck_erp_invoices_exchange_rate_positive", "erp_invoices", type_="check"
    )
    op.drop_constraint("fk_erp_invoices_currency", "erp_invoices", type_="foreignkey")
    op.drop_column("erp_invoices", "exchange_rate")
    op.drop_column("erp_invoices", "currency")

    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_erp_exchange_rates "
        "ON public.erp_exchange_rates"
    )
    op.execute("ALTER TABLE public.erp_exchange_rates DISABLE ROW LEVEL SECURITY")
    op.drop_table("erp_exchange_rates")