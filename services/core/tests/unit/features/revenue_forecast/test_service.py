"""Unit tests for RevenueForecastService (SKY-82 A4) against a fake repo.

No DB: the fake records the monthly-revenue / pipeline reads and the upsert
call so the service's serialize/compute/persist choreography (including the
CRM pipeline uplift) is pinned without a database.
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
    def __init__(
        self, monthly: list[MonthlyRevenue], pipeline: dict[date, Decimal] | None = None
    ) -> None:
        self.monthly = monthly
        self.pipeline = pipeline or {}
        self.replace_calls: list[dict] = []
        self.stored: list[ErpRevenueForecastModel] = []

    async def monthly_revenue(self, tenant_id: uuid.UUID, from_month: date) -> list[MonthlyRevenue]:
        return self.monthly

    async def pipeline_by_month(
        self, tenant_id: uuid.UUID, from_month: date, to_month: date
    ) -> dict[date, Decimal]:
        return self.pipeline

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
        baselines: list[Decimal | None] | None = None,
        pipeline_uplifts: list[Decimal | None] | None = None,
    ) -> None:
        self.replace_calls.append(
            {
                "model_version": model_version,
                "months": months,
                "predicted": predicted,
                "sigma": sigma,
                "backtest_mape": backtest_mape,
                "pipeline_value": pipeline_value,
                "baselines": baselines,
                "pipeline_uplifts": pipeline_uplifts,
            }
        )

    async def get_forecast(self, tenant_id: uuid.UUID) -> list[ErpRevenueForecastModel]:
        return self.stored


def _flat_monthly(months: int) -> list[MonthlyRevenue]:
    def month_at(index: int) -> date:
        return date(2026 + index // 12, index % 12 + 1, 1)

    return [MonthlyRevenue(month=month_at(i), revenue=Decimal("10000")) for i in range(months)]


def _stored_row(
    month: date,
    predicted: str,
    pipeline_value: Decimal | None = None,
    baseline: str | None = None,
    pipeline_uplift: Decimal | None = None,
) -> ErpRevenueForecastModel:
    row = ErpRevenueForecastModel(
        tenant_id=TENANT,
        id=uuid.uuid4(),
        month=month,
        predicted=Decimal(predicted),
        model_version="trend-seasonal",
        pipeline_value=pipeline_value,
        baseline=Decimal(baseline) if baseline is not None else None,
        pipeline_uplift=pipeline_uplift,
    )
    row.created_at = datetime(2026, 9, 8, tzinfo=UTC)
    row.updated_at = datetime(2026, 9, 8, tzinfo=UTC)
    return row


async def test_refresh_persists_twelve_month_horizon() -> None:
    repo = FakeRepository(_flat_monthly(9))
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.model_version == "trend-seasonal"
    assert len(response.points) == 12
    assert len(response.history) == len(repo.monthly)
    assert response.history[0].actual == Decimal("10000")
    assert {point.month for point in response.points} == {
        date(2026, m, 1) for m in range(10, 13)
    } | {date(2027, m, 1) for m in range(1, 10)}
    assert response.backtest_mape == Decimal("0.0000")

    assert len(repo.replace_calls) == 1
    call = repo.replace_calls[0]
    assert call["months"] == [date(2026, m, 1) for m in range(10, 13)] + [
        date(2027, m, 1) for m in range(1, 10)
    ]
    assert call["predicted"] == [Decimal("10000")] * 12


async def test_refresh_blends_pipeline_into_forecast() -> None:
    repo = FakeRepository(_flat_monthly(9), pipeline={date(2026, 10, 1): Decimal("5000")})
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.pipeline_value == Decimal("5000.0000")
    assert response.points[0].predicted == Decimal("15000")  # 10000 baseline + 5000
    assert response.points[1].predicted == Decimal("10000")  # untouched month
    assert repo.replace_calls[0]["pipeline_value"] == Decimal("5000.0000")


async def test_refresh_persists_per_month_decomposition() -> None:
    repo = FakeRepository(_flat_monthly(9), pipeline={date(2026, 10, 1): Decimal("5000")})
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    uplifted = response.points[0]
    assert uplifted.month == date(2026, 10, 1)
    assert uplifted.baseline == Decimal("10000")
    assert uplifted.pipeline == Decimal("5000")
    assert uplifted.predicted == uplifted.baseline + uplifted.pipeline

    plain = response.points[1]
    assert plain.baseline == Decimal("10000")
    assert plain.pipeline == Decimal("0")
    assert plain.predicted == plain.baseline

    for point in response.points:
        assert point.predicted == point.baseline + point.pipeline

    call = repo.replace_calls[0]
    assert call["baselines"] == [Decimal("10000")] * 12
    assert call["pipeline_uplifts"] == [Decimal("5000"), *[Decimal("0")] * 11]


async def test_read_returns_stored_decomposition() -> None:
    repo = FakeRepository([])
    repo.stored = [
        _stored_row(
            date(2026, 10, 1),
            "15000",
            pipeline_value=Decimal("5000.0000"),
            baseline="10000",
            pipeline_uplift=Decimal("5000.0000"),
        ),
    ]
    svc = RevenueForecastService(repo)
    response = await svc.read(TENANT)

    assert response.pipeline_value == Decimal("5000.0000")
    assert response.points[0].baseline == Decimal("10000")
    assert response.points[0].pipeline == Decimal("5000.0000")
    assert response.points[0].predicted == Decimal("15000")


async def test_refresh_without_pipeline_stores_zero() -> None:
    repo = FakeRepository(_flat_monthly(9))
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.pipeline_value == Decimal("0")
    assert repo.replace_calls[0]["pipeline_value"] == Decimal("0")


async def test_refresh_with_no_history_persists_nothing() -> None:
    repo = FakeRepository([])
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.points == []
    assert response.backtest_mape is None
    assert response.pipeline_value is None
    assert len(repo.replace_calls) == 1
    assert repo.replace_calls[0]["months"] == []
    assert repo.replace_calls[0]["pipeline_value"] is None


async def test_read_returns_stored_pipeline_value() -> None:
    repo = FakeRepository([])
    repo.stored = [
        _stored_row(date(2026, 10, 1), "15000", pipeline_value=Decimal("5000.0000")),
    ]
    svc = RevenueForecastService(repo)
    response = await svc.read(TENANT)

    assert response.pipeline_value == Decimal("5000.0000")
    assert response.points[0].predicted == Decimal("15000")


async def test_refresh_abstains_below_three_months_history() -> None:
    repo = FakeRepository(_flat_monthly(2))
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert response.points == []
    assert response.backtest_mape is None
    assert repo.replace_calls[0]["months"] == []


async def test_refresh_horizon_spans_twelve_months() -> None:
    repo = FakeRepository(_flat_monthly(13))
    svc = RevenueForecastService(repo)
    response = await svc.refresh(TENANT)

    assert len(response.points) == 12
    assert {point.month for point in response.points} == {
        date(2027, m, 1) for m in range(2, 13)
    } | {date(2028, 1, 1)}


async def test_read_returns_stored_rows_in_order() -> None:
    repo = FakeRepository([])
    repo.stored = [
        _stored_row(date(2026, 10, 1), "10000"),
        _stored_row(date(2026, 11, 1), "11000"),
    ]
    svc = RevenueForecastService(repo)
    response = await svc.read(TENANT)

    assert response.model_version == "trend-seasonal"
    assert [point.month for point in response.points] == [
        date(2026, 10, 1),
        date(2026, 11, 1),
    ]
    assert response.points[1].predicted == Decimal("11000")
    assert response.history == []


async def test_read_with_nothing_stored_returns_empty() -> None:
    repo = FakeRepository([])
    svc = RevenueForecastService(repo)
    response = await svc.read(TENANT)

    assert response.model_version == ""
    assert response.points == []
    assert response.history == []
