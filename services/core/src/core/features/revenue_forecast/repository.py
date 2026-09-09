"""Revenue-forecast persistence (SKY-82 A4).

Reads the recognized-revenue series from approved invoices (the same source
boundary as finance: revenue is only recognized at ``approved``), and upserts
forecast rows keyed on ``UNIQUE (tenant_id, month)`` - the recompute guard.

Pipeline weighting reads the tenant's open CRM opportunities (same shared
database, tenant-scoped) - weighted conversion value per closing month is
``probability/100 x amount`` of every non-terminal deal whose
``expected_close_date`` lands in the forecast horizon.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects import InvoiceStatus, OpportunityStage
from core.features.crm.models.opportunity import ErpCrmOpportunityModel
from core.features.finance.models.invoice import ErpInvoiceModel
from core.features.revenue_forecast.calculator import MonthlyRevenue
from core.features.revenue_forecast.models.forecast import ErpRevenueForecastModel


class RevenueForecastRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def monthly_revenue(self, tenant_id: uuid.UUID, from_month: date) -> list[MonthlyRevenue]:
        """Recognized revenue per calendar month from approved invoices."""
        result = await self._db.execute(
            select(
                func.date_trunc("month", ErpInvoiceModel.invoice_date).label("month"),
                func.sum(ErpInvoiceModel.total).label("revenue"),
            )
            .where(
                ErpInvoiceModel.tenant_id == tenant_id,
                ErpInvoiceModel.status == InvoiceStatus.APPROVED,
                ErpInvoiceModel.invoice_date >= from_month,
            )
            .group_by("month")
            .order_by("month")
        )
        return [
            MonthlyRevenue(month=row.month.date(), revenue=Decimal(row.revenue))
            for row in result.all()
        ]

    async def pipeline_by_month(
        self, tenant_id: uuid.UUID, from_month: date, to_month: date
    ) -> dict[date, Decimal]:
        """Weighted expected pipeline value per closing month in the horizon.

        Every open (non-terminal) opportunity with an amount and an
        ``expected_close_date`` inside ``[from_month, to_month]`` contributes
        ``probability/100 x amount`` to its closing month. Deals without an
        amount or without an expected close date are ignored (they cannot be
        value-weighted or bucketed honestly).
        """
        result = await self._db.execute(
            select(
                func.date_trunc("month", ErpCrmOpportunityModel.expected_close_date).label("month"),
                func.coalesce(
                    func.sum(
                        ErpCrmOpportunityModel.amount * ErpCrmOpportunityModel.probability / 100
                    ),
                    0,
                ).label("weighted"),
            )
            .where(
                ErpCrmOpportunityModel.tenant_id == tenant_id,
                ErpCrmOpportunityModel.stage.not_in((OpportunityStage.WON, OpportunityStage.LOST)),
                ErpCrmOpportunityModel.amount.is_not(None),
                ErpCrmOpportunityModel.expected_close_date.is_not(None),
                ErpCrmOpportunityModel.expected_close_date >= from_month,
                ErpCrmOpportunityModel.expected_close_date <= to_month,
            )
            .group_by("month")
            .order_by("month")
        )
        return {row.month.date(): Decimal(row.weighted) for row in result.all()}

    async def replace_forecast(
        self,
        tenant_id: uuid.UUID,
        model_version: str,
        *,
        months: list[date],
        predicted: list[Decimal],
        lower_bounds: list[Decimal | None],
        upper_bounds: list[Decimal | None],
        sigma: Decimal | None,
        backtest_mape: Decimal | None,
        pipeline_value: Decimal | None = None,
    ) -> None:
        """Upsert the full forecast horizon for a tenant (recompute guard).

        ``pipeline_value`` is the run-level total of weighted expected pipeline
        added to the horizon (``None`` when the forecast abstained); it applies
        to every row written by this recompute.
        """
        if months:
            stmt = insert(ErpRevenueForecastModel).values(
                [
                    {
                        "tenant_id": tenant_id,
                        "month": m,
                        "predicted": p,
                        "lower_bound": lo,
                        "upper_bound": hi,
                        "sigma": sigma,
                        "backtest_mape": backtest_mape,
                        "model_version": model_version,
                        "pipeline_value": pipeline_value,
                    }
                    for m, p, lo, hi in zip(
                        months, predicted, lower_bounds, upper_bounds, strict=True
                    )
                ]
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_erp_revenue_forecast_tenant_month",
                set_={
                    "predicted": stmt.excluded.predicted,
                    "lower_bound": stmt.excluded.lower_bound,
                    "upper_bound": stmt.excluded.upper_bound,
                    "sigma": stmt.excluded.sigma,
                    "backtest_mape": stmt.excluded.backtest_mape,
                    "model_version": stmt.excluded.model_version,
                    "pipeline_value": stmt.excluded.pipeline_value,
                    "updated_at": func.now(),
                },
            )
            await self._db.execute(stmt)

    async def get_forecast(self, tenant_id: uuid.UUID) -> list[ErpRevenueForecastModel]:
        result = await self._db.execute(
            select(ErpRevenueForecastModel)
            .where(ErpRevenueForecastModel.tenant_id == tenant_id)
            .order_by(ErpRevenueForecastModel.month)
        )
        return list(result.scalars().all())
