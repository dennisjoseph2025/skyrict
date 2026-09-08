"""Seed overdue invoices so the A8 payment-reminder flow can be tested.

Creates a handful of APPROVED/ISSUED invoices whose ``due_date`` is in the
past for a target tenant. Non-destructive: it only inserts rows with a
distinct ``invoice_number`` prefix (``INV-OVR-``) and never touches existing
data. Idempotent per invoice number.

Usage:
    core seed-overdue-invoices --tenant-id <UUID>
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from core.db.session import async_session_factory
from core.domain.value_objects import InvoiceStatus
from core.features.crm.models.customer import ErpCrmCustomerModel
from core.features.finance.models.chart_of_account import ErpChartOfAccountModel
from core.features.finance.models.invoice import ErpInvoiceModel
from core.features.finance.models.invoice_line import ErpInvoiceLineModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("core.seed.overdue_invoices")

_REVENUE_ACCOUNT_CODE = "4010"


def _due_days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def seed_overdue_invoices(tenant_id: uuid.UUID) -> dict[str, int]:
    """Insert 3 overdue invoices (1 APPROVED, 2 ISSUED) for the tenant.

    Returns a dict of counts (``invoices``, ``lines``) so callers can report
    what was seeded. Any invoice whose number already exists is skipped.
    """
    async with async_session_factory() as session:
        customers = (
            (
                await session.execute(
                    select(ErpCrmCustomerModel)
                    .where(
                        ErpCrmCustomerModel.tenant_id == tenant_id,
                        ErpCrmCustomerModel.is_active.is_(True),
                    )
                    .order_by(ErpCrmCustomerModel.customer_code)
                )
            )
            .scalars()
            .all()
        )
        if not customers:
            raise RuntimeError(
                f"No active customers found for tenant {tenant_id}; seed CRM data first."
            )

        revenue = (
            await session.execute(
                select(ErpChartOfAccountModel).where(
                    ErpChartOfAccountModel.tenant_id == tenant_id,
                    ErpChartOfAccountModel.code == _REVENUE_ACCOUNT_CODE,
                )
            )
        ).scalar_one_or_none()
        if revenue is None:
            raise RuntimeError(
                f"Revenue account {_REVENUE_ACCOUNT_CODE} not found for tenant {tenant_id}."
            )

        existing = set(
            (
                await session.execute(
                    select(ErpInvoiceModel.invoice_number).where(
                        ErpInvoiceModel.tenant_id == tenant_id
                    )
                )
            )
            .scalars()
            .all()
        )

        rows: list[tuple[str, int, int, InvoiceStatus, Decimal, str]] = [
            ("INV-OVR-001", 30, 45, InvoiceStatus.APPROVED, Decimal("12500.00"), "Azure migration retainer"),
            ("INV-OVR-002", 12, 20, InvoiceStatus.ISSUED, Decimal("8300.00"), "Quarterly security audit"),
            ("INV-OVR-003", 45, 60, InvoiceStatus.ISSUED, Decimal("17800.00"), "Data warehouse build"),
        ]

        invoices = 0
        lines = 0
        for number, due_ago, issued_ago, status, total, desc in rows:
            if number in existing:
                logger.info("seed.overdue.skip.exists", number=number)
                continue

            customer = customers[invoices % len(customers)]
            issued_at = _due_days_ago(issued_ago)
            inv = ErpInvoiceModel(
                tenant_id=tenant_id,
                invoice_number=number,
                customer_id=customer.id,
                invoice_date=issued_at.date(),
                due_date=_due_days_ago(due_ago).date(),
                status=status,
                total=total,
                currency="USD",
                exchange_rate=Decimal("1"),
                source="manual",
                source_ref=None,
            )
            if status is InvoiceStatus.APPROVED:
                inv.approved_at = issued_at + timedelta(days=1)
            elif status is InvoiceStatus.ISSUED:
                inv.issued_at = issued_at
            session.add(inv)
            await session.flush()

            session.add(
                ErpInvoiceLineModel(
                    tenant_id=tenant_id,
                    invoice_id=inv.id,
                    line_no=1,
                    description=desc,
                    account_id=revenue.id,
                    quantity=Decimal("1"),
                    unit_price=total,
                    amount=total,
                )
            )
            invoices += 1
            lines += 1
            logger.info("seed.overdue.created", number=number, status=status.value)

        await session.commit()
        return {"invoices": invoices, "lines": lines}
