"""Response schemas for the revenue-forecast feature (SKY-82 A4).

The forecast is a computed product - one point per forecast month, each with
an optional ±1.5 sigma confidence band. ``backtest_mape`` / ``sigma`` are
run-level aggregates; both are None when history is too short to validate.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from skyrict_common.schemas import ResponseEnvelope


class ForecastPointResponse(BaseModel):
    month: date
    predicted: Decimal
    lower_bound: Decimal | None
    upper_bound: Decimal | None


class RevenueForecastResponse(BaseModel):
    model_version: str
    backtest_mape: Decimal | None
    sigma: Decimal | None
    points: list[ForecastPointResponse]


RevenueForecastEnvelope = ResponseEnvelope[RevenueForecastResponse]
