"""Revenue-forecast service (SKY-82 A4).

``refresh`` computes and persists a 12-month SMA-6 forecast from the last 24
months of recognized revenue (abstaining - persisting nothing - when there
is under 6 months of history); ``read`` returns whatever is currently stored
(weekly recompute and manual refresh keep it fresh). CRM pipeline conversion
weighting from deal health is a cross-module (CRM) dependency, documented in
the eval note rather than implemented here.
"""

from __future__ import annotations

import uuid
from datetime import date

from core.features.revenue_forecast.calculator import (
    compute_forecast,
)
from core.features.revenue_forecast.repository import RevenueForecastRepository
from core.features.revenue_forecast.schemas import (
    ForecastPointResponse,
    RevenueForecastResponse,
)

_HISTORY_MONTHS = 24


class RevenueForecastService:
    def __init__(self, repo: RevenueForecastRepository) -> None:
        self._repo = repo

    @staticmethod
    def _history_from_month(as_of: date) -> date:
        year = as_of.year + (as_of.month - 1 - (_HISTORY_MONTHS - 1)) // 12
        month = (as_of.month - 1 - (_HISTORY_MONTHS - 1)) % 12 + 1
        return date(year, month, 1)

    async def refresh(
        self, tenant_id: uuid.UUID, as_of: date | None = None
    ) -> RevenueForecastResponse:
        as_of = as_of or date.today()
        monthly = await self._repo.monthly_revenue(tenant_id, self._history_from_month(as_of))
        forecast = compute_forecast(monthly)
        months = [p.month for p in forecast.points]
        await self._repo.replace_forecast(
            tenant_id,
            forecast.model_version,
            months=months,
            predicted=[p.predicted for p in forecast.points],
            lower_bounds=[p.lower_bound for p in forecast.points],
            upper_bounds=[p.upper_bound for p in forecast.points],
            sigma=forecast.backtest.sigma if forecast.backtest is not None else None,
            backtest_mape=forecast.backtest.mape if forecast.backtest is not None else None,
        )
        return RevenueForecastResponse(
            model_version=forecast.model_version,
            backtest_mape=forecast.backtest.mape if forecast.backtest is not None else None,
            sigma=forecast.backtest.sigma if forecast.backtest is not None else None,
            points=[
                ForecastPointResponse(
                    month=p.month,
                    predicted=p.predicted,
                    lower_bound=p.lower_bound,
                    upper_bound=p.upper_bound,
                )
                for p in forecast.points
            ],
        )

    async def read(self, tenant_id: uuid.UUID) -> RevenueForecastResponse:
        rows = await self._repo.get_forecast(tenant_id)
        if not rows:
            return RevenueForecastResponse(
                model_version="", backtest_mape=None, sigma=None, points=[]
            )
        return RevenueForecastResponse(
            model_version=rows[0].model_version,
            backtest_mape=rows[0].backtest_mape,
            sigma=rows[0].sigma,
            points=[
                ForecastPointResponse(
                    month=row.month,
                    predicted=row.predicted,
                    lower_bound=row.lower_bound,
                    upper_bound=row.upper_bound,
                )
                for row in rows
            ],
        )
