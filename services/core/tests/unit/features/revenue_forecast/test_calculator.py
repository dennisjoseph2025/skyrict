"""Unit tests for the revenue-forecast calculator (SKY-82 A4).

The calculator is pure Decimal math - no DB. These pin the SMA-6 baseline,
the ±1.5 sigma band from walk-forward error, MAPE aggregation, and the month-shift
bookkeeping (including the calendar-year wrap).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from core.features.revenue_forecast.calculator import (
    Backtest,
    MonthlyRevenue,
    compute_forecast,
)


def _series() -> list[MonthlyRevenue]:
    def revenue(month_index: int) -> Decimal:
        base = Decimal("10000") + Decimal(month_index) * Decimal("1000")
        return base

    points = [
        MonthlyRevenue(month=date(2026, m, 1), revenue=revenue(i))
        for i, m in enumerate(range(1, 13))
    ]
    return points


def _flat_series(months: int, value: str = "10000") -> list[MonthlyRevenue]:
    return [
        MonthlyRevenue(month=date(2026, m, 1), revenue=Decimal(value)) for m in range(1, months + 1)
    ]


def test_empty_history_has_no_points_and_no_backtest() -> None:
    forecast = compute_forecast([])
    assert forecast.points == ()
    assert forecast.backtest is None


def test_six_months_flat_has_points_without_band() -> None:
    monthly = _flat_series(6)
    forecast = compute_forecast(monthly)
    assert len(forecast.points) == 12
    assert forecast.backtest is None
    for point in forecast.points:
        assert point.predicted == Decimal("10000")
        assert point.lower_bound is None
        assert point.upper_bound is None


def test_horizon_months_step_with_year_wrap() -> None:
    monthly = [MonthlyRevenue(month=date(2026, 10, 1), revenue=Decimal("10000")) for _ in range(6)]
    forecast = compute_forecast(monthly, horizon=3)
    months = [point.month for point in forecast.points]
    assert months == [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]


def test_backtest_present_and_equal_sma6_baseline() -> None:
    forecast = compute_forecast(_series(), horizon=3)
    backtest = forecast.backtest
    assert backtest is not None
    assert isinstance(backtest, Backtest)
    assert 0 < backtest.mape < Decimal("50")
    expected_baseline = sum((p.revenue for p in _series()[-6:]), Decimal("0")) / 6
    for point in forecast.points:
        assert point.predicted == expected_baseline
        assert point.lower_bound is not None
        assert point.upper_bound is not None
        assert point.lower_bound < point.predicted < point.upper_bound


def test_band_is_minus_15_sigma_floored_at_zero() -> None:
    volatile = _series()
    forecast = compute_forecast(volatile)
    assert forecast.backtest is not None
    assert forecast.backtest.sigma is not None
    point = forecast.points[0]
    band = Decimal("1.5") * forecast.backtest.sigma
    expected_lower = max(
        Decimal("0"), (point.predicted - band).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )
    assert point.lower_bound == expected_lower
    assert point.upper_bound == (point.predicted + band).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def test_perfect_walk_forward_forecast_yields_zero_mape() -> None:
    monthly = [
        MonthlyRevenue(month=date(2026, m, 1), revenue=Decimal("10000")) for m in range(1, 10)
    ]
    forecast = compute_forecast(monthly)
    assert forecast.backtest is not None
    assert forecast.backtest.mape == Decimal("0.0000")


@pytest.mark.parametrize("months", [0, 1, 2, 3, 4, 5])
def test_under_six_months_history_abstains(months: int) -> None:
    forecast = compute_forecast(_flat_series(months))
    assert forecast.backtest is None
    assert forecast.points == ()
