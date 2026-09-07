"""Pure deterministic supplier-risk scoring (SKY-86 / INV-AI-004).

Takes a supplier's grading-period facts + quoted lead time and returns a
transparent 0-1 risk score, a discretised ``low|medium|high`` band, a
confidence between 0 and 1, and a human-readable reason.

Risk dimensions (all normalised so higher = riskier, each on 0-1):

- ``on_time_delivery_pct`` (45%)  - the higher the delivered-on-time %, the lower
  the risk: ``(100 - on_time) / 100``.
- ``defect_rate_pct`` (15%)        - the higher the defect %, the higher the risk:
  ``defect / 100``.
- ``price_stability_index`` (20%) - the higher the index, the more stable prices,
  so risk is inverted: ``(100 - price) / 100``.
- ``responsiveness_days`` (20%)   - quote-turnaround in days measured against the
  supplier's own lead-time baseline: ``min(responsiveness_days / LEAD_TIME_DEFAULT, 1)``
  so a turnaround spanning most of the supplier's quoted lead time reads as
  risky, while a 2-day turnaround on a 7-day lead barely registers.

Each dimension is run through a power lift ``x ** 0.45`` (documented constant
``_LIFT``): 0-1 "failure" values are pulled upward so a supplier that is merely
"moderately bad" across several dimensions (say ~50% on-time on a 14-day lead)
grades unambiguously HIGH rather than squatting in the middle. The lift is a
fixed, auditable constant - not fitted - and keeps the whole formula
deterministic and reproducible.

Weighted sum => fixed 0-1 score for fixed inputs (no ML, fully auditable).
Bands: ``[0,0.33]`` low, ``(0.33,0.66]`` medium, ``(0.66,1]`` high.
Confidence grows with the number of grading periods observed and decays for
stale (older than one quarter) data.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from ai_agent.domain.supplier_risk import SupplierRiskAssessment

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import date

    from ai_agent.domain.supplier_risk import (
        RiskBand,
        SupplierPerformanceFacts,
    )

_EMPTY = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")

_RECENCY_WINDOW_DAYS = 92  # one quarter; older facts lower confidence.
_PERIODS_FOR_FULL_CONFIDENCE = 5

_LIFT = 0.45  # deterministic power lift (see module docstring).

_W_ON_TIME = Decimal("0.45")
_W_DEFECT = Decimal("0.15")
_W_PRICE = Decimal("0.20")
_W_RESPONSIVENESS = Decimal("0.20")

_LOW_MAX = Decimal("0.33")
_MEDIUM_MAX = Decimal("0.66")


def assess_supplier_risk(
    performance: Sequence[SupplierPerformanceFacts],
    *,
    lead_time_days: int,
    as_of: date,
) -> SupplierRiskAssessment | None:
    """Grade a supplier; returns None when there is no recorded performance."""
    if not performance:
        return None

    on_time, defect, price, responsiveness = _dimension_scores(
        performance, lead_time_days=lead_time_days
    )
    score = (
        on_time * _W_ON_TIME
        + defect * _W_DEFECT
        + price * _W_PRICE
        + responsiveness * _W_RESPONSIVENESS
    )
    score = _round3(score)
    band = _to_band(score)
    confidence = _confidence(performance, as_of)
    reason = _explain(
        band=band,
        on_time=_as_pct(_one_minus(on_time)),
        defect=_as_pct(defect),
        price=_as_pct(_one_minus(price)),
        responsiveness=_as_pct(responsiveness),
        lead_time_days=lead_time_days,
    )
    return SupplierRiskAssessment(
        supplier_id=performance[0].supplier_id,
        score=score,
        risk_band=band,
        confidence=confidence,
        reason=reason,
    )


def _dimension_scores(
    performance: Sequence[SupplierPerformanceFacts],
    *,
    lead_time_days: int,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Average the lifted failure value of each dimension across periods."""
    on_time = [_lift(_one_minus(p.on_time_delivery_pct / _HUNDRED)) for p in performance]
    defect = [_lift(p.defect_rate_pct / _HUNDRED) for p in performance]
    price = [_lift(_one_minus(p.price_stability_index / _HUNDRED)) for p in performance]
    responsiveness = [
        _lift(_responsiveness_ratio(p.responsiveness_days, lead_time_days)) for p in performance
    ]
    return (
        _mean(on_time),
        _mean(defect),
        _mean(price),
        _mean(responsiveness),
    )


def _responsiveness_ratio(responsiveness_days: Decimal, lead_time_days: int) -> Decimal:
    """Turnaround as a fraction of the supplier's quoted lead time (clamped 0-1)."""
    if lead_time_days <= 0:
        return _EMPTY
    return _clamp01(responsiveness_days / Decimal(lead_time_days))


def _lift(value: Decimal) -> Decimal:
    """Apply the deterministic power lift to a 0-1 failure value."""
    lifted = float(value) ** _LIFT
    return _round3(Decimal(str(lifted)))


def _mean(values: Iterable[Decimal]) -> Decimal:
    items = list(values)
    if not items:
        return _EMPTY
    return _round3(sum(items, _EMPTY) / Decimal(len(items)))


def _clamp01(value: Decimal) -> Decimal:
    if value < _EMPTY:
        return _EMPTY
    if value > _ONE:
        return _ONE
    return value


def _one_minus(value: Decimal) -> Decimal:
    return _ONE - value


def _round3(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _to_band(score: Decimal) -> RiskBand:
    if score <= _LOW_MAX:
        return "low"
    if score <= _MEDIUM_MAX:
        return "medium"
    return "high"


def _confidence(performance: Sequence[SupplierPerformanceFacts], as_of: date) -> Decimal:
    """0-1 confidence from number of periods and data recency (one-quarter window)."""
    n = len(performance)
    period_confidence = min(_ONE, Decimal(n) / Decimal(_PERIODS_FOR_FULL_CONFIDENCE))
    recency = _ONE
    latest = max(p.period_end for p in performance)
    age_days = (as_of - latest).days
    if age_days > 0:
        decay = _ONE - Decimal(age_days) / Decimal(_RECENCY_WINDOW_DAYS)
        recency = _clamp01(decay)
    return _round3(period_confidence * recency)


def _explain(
    *,
    band: RiskBand,
    on_time: str,
    defect: str,
    price: str,
    responsiveness: str,
    lead_time_days: int,
) -> str:
    """Single-line, human-readable detail (consumed by web risk badges/tooltips)."""
    return (
        f"{band} risk, on-time delivery {on_time}, defect rate {defect}, "
        f"price stability {price}, turnaround {responsiveness} of "
        f"{lead_time_days}d lead time"
    )


def _as_pct(value: Decimal) -> str:
    return f"{float(value * _HUNDRED):.1f}%"
