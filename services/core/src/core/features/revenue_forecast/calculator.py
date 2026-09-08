"""Revenue forecasting (SKY-82 A4) - pure forecasting math.

The method is deliberately simple: a trailing 6-month simple moving average,
flat for the whole horizon, with a confidence band of ±1.5 sigma of the
walk-forward historical error distribution (per the approved plan - the CRM
influencer pipeline weighting was deferred, add it back only if the backtest
MAPE warrants it). All arithmetic is :class:`decimal.Decimal` so figures
round-trip exactly through the SQL ``Numeric`` columns and the web UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MODEL_VERSION = "sma-6"
SMA_WINDOW = 6
BACKTEST_MIN_POINTS = 3
HORIZON_MONTHS = 3
BAND_SIGMA_MULTIPLIER = Decimal("1.5")


@dataclass(frozen=True)
class MonthlyRevenue:
    """Recognized revenue for one calendar month (from approved invoices)."""

    month: date
    revenue: Decimal


@dataclass(frozen=True)
class ForecastPoint:
    month: date
    predicted: Decimal
    lower_bound: Decimal | None
    upper_bound: Decimal | None


@dataclass(frozen=True)
class Backtest:
    mape: Decimal
    sigma: Decimal | None  # None when there are no errors (perfect, or too little history)


@dataclass(frozen=True)
class Forecast:
    points: tuple[ForecastPoint, ...]
    backtest: Backtest | None
    model_version: str = MODEL_VERSION


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _sma(values: list[Decimal]) -> Decimal:
    total = sum(values, Decimal("0"))
    return _quantize(total / len(values))


def _month_step(month: date, offset_months: int) -> date:
    year = month.year + (month.month - 1 + offset_months) // 12
    m = (month.month - 1 + offset_months) % 12 + 1
    return date(year, m, 1)


def backtest_errors(monthly: list[MonthlyRevenue]) -> list[Decimal]:
    """Walk-forward prediction errors (predicted - actual).

    For each month t with at least :data:`BACKTEST_MIN_POINTS` prior months,
    predict t with the SMA over the up-to-6 prior completed months and record
    the signed error. Returns [] when there is too little history to validate.
    """
    errors: list[Decimal] = []
    for i in range(SMA_WINDOW, len(monthly)):
        predicted = _sma([point.revenue for point in monthly[i - SMA_WINDOW : i]])
        errors.append(predicted - monthly[i].revenue)
    return errors


def _mape(errors: list[Decimal], actuals: list[Decimal]) -> Decimal:
    aligned = [(abs(e), a) for e, a in zip(errors, actuals, strict=True) if a > 0]
    if not aligned:
        return Decimal("0")
    total_absolute = sum((e for e, _ in aligned), Decimal("0"))
    total_actual = sum((a for _, a in aligned), Decimal("0"))
    return _quantize(total_absolute / total_actual * Decimal("100"))


def compute_forecast(
    monthly: list[MonthlyRevenue],
    *,
    horizon: int = HORIZON_MONTHS,
) -> Forecast:
    """Forecast ``horizon`` months ahead using SMA-6 over ``monthly`` history.

    History is expected to be a contiguous, ascending monthly series. With
    fewer than :data:`BACKTEST_MIN_POINTS` months there is no validation, so
    points carry no band and ``backtest`` is None. When there is at least one
    window, the band is ``predicted ± 1.5 sigma`` of the signed historical errors
    (floored at zero).
    """
    if not monthly:
        return Forecast(points=(), backtest=None)

    errors = backtest_errors(monthly)
    if len(monthly) >= SMA_WINDOW and errors:
        sigma = max(Decimal("0.0001"), _stddev(errors))
        backtest = Backtest(
            mape=_mape(errors, [p.revenue for p in monthly[SMA_WINDOW:]]), sigma=sigma
        )
    else:
        backtest = None

    last_month = monthly[-1].month
    baseline = _sma([p.revenue for p in monthly[-SMA_WINDOW:]])

    points: list[ForecastPoint] = []
    for offset in range(1, horizon + 1):
        forecast_month = _month_step(last_month, offset)
        lower: Decimal | None
        upper: Decimal | None
        if backtest is not None:
            assert backtest.sigma is not None
            band = BAND_SIGMA_MULTIPLIER * backtest.sigma
            lower = max(Decimal("0"), baseline - band)
            upper = baseline + band
        else:
            lower = upper = None
        points.append(
            ForecastPoint(
                month=forecast_month,
                predicted=baseline,
                lower_bound=_quantize(lower) if lower is not None else None,
                upper_bound=_quantize(upper) if upper is not None else None,
            )
        )
    return Forecast(points=tuple(points), backtest=backtest)


def _stddev(values: list[Decimal]) -> Decimal:
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(len(values))
    return variance.sqrt()
