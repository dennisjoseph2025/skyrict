"""Unit tests for RevenueForecastService (SKY-82 A4) against a fake repo.

No DB: the fake records the monthly-revenue read and the upsert call so the
service's serialize/compute/persist choreography is pinned without a database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from core.features.revenue_forecast.calculator import MonthlyRevenue
from core.features.revenue_forecast.models.forecast import ErpRevenueForecastModel
from core.features.revenue_forecast.service import RevenueForecastService

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")


class FakeRepository:
    def __init__(self, monthly: list[MonthlyRevenue]) -> None:
        self.monthly = monthly
        self.replace_calls: list[dict] = []
        self.stored: list[ErpRevenueForecastModel] = []

    async def monthly_revenue(self, tenant_id: uuid.UUID, from_month: date) -> list[MonthlyRevenue]:
        return self.monthly

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
    ) -> None:
        self.replace_calls.append(
            {
                "model_version": model_version,
                "months": months,
                "predicted": predicted,
                "sigma": sigma,
                "backtest_mape": backtest_mape,
            }
        )

    async def get_forecast(self, tenant_id: uuid.UUID) -> list[ErpRevenueForecastModel]:
        return self.stored


def _flat_monthly(months: int) -> list[MonthlyRevenue]:
    def month_at(index: int) -> date:
        return date(2026 + index // 12, index % 12 + 1, 1)

    return [
        MonthlyRevenue(month=month_at(i), revenue=Decimal("10000"))
        for i in range(months)
    ]


def _stored_row(month: date, predicted: str) -> ErpRevenueForecastModel:
    row = ErpRevenueForecastModel(
        tenant_id=TENANT,
        id=uuid.uuid4(),
        month=month,
        predicted=Decimal(predicted),
        model_version="sma-6",
    )
    row.created_at = datetime(2026, 9, 8, tzinfo=UTC)
    row.updated_at = datetime(2026, 9, 8, tzinfo=UTC)
    return row


async def test_refresh_persists_three_month_horizon() -> None:
    repo = FakeRepository(_flat_monthly(9))
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.model_version == "sma-6"
    assert len(response.points) == 3
    assert {point.month for point in response.points} == {
        date(2026, 10, 1),
        date(2026, 11, 1),
        date(2026, 12, 1),
    }
    assert response.backtest_mape == Decimal("0.0000")

    assert len(repo.replace_calls) == 1
    call = repo.replace_calls[0]
    assert call["months"] == [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]
    assert call["predicted"] == [Decimal("10000")] * 3


async def test_refresh_with_no_history_persists_nothing() -> None:
    repo = FakeRepository([])
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.points == []
    assert response.backtest_mape is None
    assert len(repo.replace_calls) == 1
    assert repo.replace_calls[0]["months"] == []


async def test_refresh_horizon_filters_to_three() -> None:
    repo = FakeRepository(_flat_monthly(13))
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert len(response.points) == 3
    assert {point.month for point in response.points} == {
        date(2027, 2, 1),
        date(2027, 3, 1),
        date(2027, 4, 1),
    }


async def test_read_returns_stored_rows_in_order() -> None:
    repo = FakeRepository([])
    repo.stored = [
        _stored_row(date(2026, 10, 1), "10000"),
        _stored_row(date(2026, 11, 1), "11000"),
    ]
    svc = RevenueForecastService(repo)
    response = await svc.read(TENANT)

    assert response.model_version == "sma-6"
    assert [point.month for point in response.points] == [
        date(2026, 10, 1),
        date(2026, 11, 1),
    ]
    assert response.points[1].predicted == Decimal("11000")


async def test_read_with_nothing_stored_returns_empty() -> None:
    repo = FakeRepository([])
    svc = RevenueForecastService(repo)
    response = await svc.read(TENANT)

    assert response.model_version == ""
    assert response.points == []
