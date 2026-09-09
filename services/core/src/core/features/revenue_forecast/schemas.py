"""Response schemas for the revenue-forecast feature (SKY-82 A4).

The forecast is a computed product - one point per forecast month, each with
an optional ±1.5 sigma confidence band. ``backtest_mape`` / ``sigma`` are
run-level aggregates; both are None when history is too short to validate.
``pipeline_value`` is the run-level total of weighted expected pipeline
(open CRM opportunities, ``probability/100 x amount`` bucketed by expected
close month) blended into the horizon; None when the forecast abstained.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from skyrict_common.schemas import ResponseEnvelope


class ForecastPointResponse(BaseModel):
    month: date
    predicted: Decimal
    # Per-month decomposition: the trend + seasonal baseline and the CRM
    # pipeline uplift blended in (predicted == baseline + pipeline).
    baseline: Decimal | None = None
    pipeline: Decimal | None = None
    lower_bound: Decimal | None
    upper_bound: Decimal | None


class ActualPointResponse(BaseModel):
    month: date
    actual: Decimal


class RevenueForecastResponse(BaseModel):
    model_version: str
    backtest_mape: Decimal | None
    sigma: Decimal | None
    points: list[ForecastPointResponse]
    history: list[ActualPointResponse] = Field(default_factory=list)
    pipeline_value: Decimal | None = None


RevenueForecastEnvelope = ResponseEnvelope[RevenueForecastResponse]
