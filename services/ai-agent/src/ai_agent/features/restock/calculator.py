"""Restock suggestion calculator - spec 3.2 with 4-factor confidence scoring.

Pure functions, no I/O: given a product's stock facts plus demand history,
produce the suggestion draft (quantity, cost, reason, confidence).

Confidence scoring (spec 3.2 table):
  - Data quality 30%: how many days of movement history are available
  - Demand stability 30%: coefficient of variation of daily demand (lower = more stable)
  - Proximity 20%: how far below the reorder point (deeper = more urgent)
  - Time since replenishment 20%: days since last receipt (longer = more urgent)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from ai_agent.domain.supplier_risk import RiskBand
    from ai_agent.features.nl_query.gateway import MovementRow, ProductRef

# Confidence factor weights (spec 3.2).
_W_DATA_QUALITY = Decimal("0.30")
_W_DEMAND_STABILITY = Decimal("0.30")
_W_PROXIMITY = Decimal("0.20")
_W_REPLENISHMENT_RECENCY = Decimal("0.20")

# Bounds for individual factor scores.
_FACTOR_FLOOR = Decimal("0.0")
_FACTOR_CEILING = Decimal("1.0")

# Data quality: full marks at 90+ days of history, zero at 0 days.
_DATA_QUALITY_FULL_DAYS = 90

# Demand stability: CV (coefficient of variation) thresholds.
# CV = stddev / mean. CV <= 0.3 is very stable (score 1.0); CV >= 1.5 is erratic (score 0.0).
_CV_STABLE = Decimal("0.3")
_CV_ERRATIC = Decimal("1.5")

# Replenishment recency: full urgency at 30+ days since last receipt.
_RECENCY_FULL_DAYS = 30

# Final confidence bounds (never claim certainty we cannot justify).
_CONFIDENCE_FLOOR = Decimal("0.50")
_CONFIDENCE_CEILING = Decimal("0.95")

# SKY-86 (INV-AI-004) supplier-risk adjustments: a supplier graded by the
# risk engine stretches the replenishment lead time and safety buffer so the
# v2 formula orders defensively for unreliable sources. Bands come from
# ``ai_supplier_risk``; absent a grade (risk_band None) no adjustment applies
# (low-risk semantics). Fixed, auditable constants - not tuned to data.
_RISK_LEAD_TIME_MULTIPLIERS: dict[str, Decimal] = {
    "low": Decimal("1.0"),
    "medium": Decimal("1.2"),
    "high": Decimal("1.5"),
}
_RISK_SAFETY_BUMPS: dict[str, Decimal] = {
    "low": Decimal("0.0"),
    "medium": Decimal("0.10"),
    "high": Decimal("0.20"),
}
_RISK_DEFAULT_MULTIPLIER = Decimal("1.0")
_RISK_DEFAULT_BUMP = Decimal("0.0")


@dataclass(frozen=True, slots=True)
class SuggestionDraft:
    """One computed restock proposal, ready for persistence."""

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    current_stock: Decimal
    reorder_point: Decimal
    suggested_qty: Decimal
    estimated_cost: Decimal | None
    reason: str
    confidence: Decimal


@dataclass(frozen=True, slots=True)
class DemandProfile:
    """V2 (spec 3.2 enhanced) inputs for one product+warehouse.

    *eligible* gates the enhanced formula: only pairs with enough observed
    history (backfilled into ``ai_restock_demand_stats``) graduate from the
    v1 ``reorder_point * 2`` heuristic. Lead time and safety factor come from
    the tenant's ``ai_restock_settings``; *risk_band* comes from the SKY-86
    supplier-risk engine through the product's supplier (None = ungraded,
    treated as low risk, no adjustment). The calculator stays pure.
    """

    avg_daily_demand: Decimal
    eligible: bool
    lead_time_days: Decimal
    safety_factor: Decimal
    risk_band: RiskBand | None = None


def compute_suggestion(
    *,
    product: ProductRef,
    warehouse_id: uuid.UUID,
    qty_on_hand: Decimal,
    movements: list[MovementRow] | None = None,
    demand: DemandProfile | None = None,
) -> SuggestionDraft:
    """Apply the spec 3.2 formula to one product/warehouse pair.

    When *movements* are provided the full 4-factor confidence is computed;
    otherwise the v1 proximity-only heuristic is used as a fallback.

    When *demand* is provided AND eligible, the suggestion quantity uses the
    enhanced formula (avg daily demand * lead time * safety factor); otherwise
    the v1 ``reorder_point * 2`` heuristic stands. The ``v2_enabled`` tenant
    flag is an orchestration concern, applied by the service when it decides
    whether to pass a :class:`DemandProfile`.
    """
    if demand is not None and demand.eligible:
        suggested_qty = _v2_suggested_qty(
            reorder_point=product.reorder_point,
            qty_on_hand=qty_on_hand,
            demand=demand,
        )
        effective_lead = _effective_lead_time_days(demand).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        reason = (
            f"Stock ({qty_on_hand}) below reorder point ({product.reorder_point}). "
            f"Avg daily demand: {demand.avg_daily_demand}. "
            f"Lead time: {effective_lead} day(s)."
        )
        if demand.risk_band is not None and demand.risk_band != "low":
            reason += (
                f" Supplier risk {demand.risk_band} applied "
                f"({_RISK_LEAD_TIME_MULTIPLIERS.get(demand.risk_band, _RISK_DEFAULT_MULTIPLIER)}x "
                f"lead time, +{_RISK_SAFETY_BUMPS.get(demand.risk_band, _RISK_DEFAULT_BUMP)} safety)."
            )
    else:
        suggested_qty = product.reorder_point * Decimal(2)
        reason = f"Stock ({qty_on_hand}) below reorder point ({product.reorder_point})."

    # Cost prices are LOCAL-ONLY data (spec 5.5): used for the estimate
    # here and returned to the tenant - never sent to any LLM provider.
    estimated_cost = suggested_qty * product.cost_price if product.cost_price is not None else None

    if movements:
        confidence = _four_factor_confidence(
            product=product,
            qty_on_hand=qty_on_hand,
            warehouse_id=warehouse_id,
            movements=movements,
        )
    else:
        confidence = _proximity_confidence(qty_on_hand, product.reorder_point)

    return SuggestionDraft(
        product_id=product.id,
        warehouse_id=warehouse_id,
        current_stock=qty_on_hand,
        reorder_point=product.reorder_point,
        suggested_qty=suggested_qty,
        estimated_cost=estimated_cost,
        reason=reason,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# V2 enhanced formula (spec 3.2) - demand-history based
# ---------------------------------------------------------------------------


def _v2_suggested_qty(
    *,
    reorder_point: Decimal,
    qty_on_hand: Decimal,
    demand: DemandProfile,
) -> Decimal:
    """``reorder_point + avg_daily_demand * effective_lead * safety - qty_on_hand``.

    Without a risk band this is the plain spec 3.2 formula:
    ``reorder + avg * lead_time * safety_factor - qty_on_hand``. A graded
    supplier's band stretches the lead time (x1.0/1.2/1.5) and adds a safety
    bump (+0.0/0.10/0.20) so unreliable sources order defensively.

    Never negative: a pair already at/above the target restock level orders
    nothing. Rounded to 2dp for durable, readable quantities.
    """
    effective_lead = _effective_lead_time_days(demand)
    effective_safety = _effective_safety_factor(demand)
    target = reorder_point + demand.avg_daily_demand * effective_lead * effective_safety
    gross = target - qty_on_hand
    return max(Decimal(0), gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _effect_multiplier(band: RiskBand | None) -> Decimal:
    return _RISK_LEAD_TIME_MULTIPLIERS.get(band or "low", _RISK_DEFAULT_MULTIPLIER)


def _effect_bump(band: RiskBand | None) -> Decimal:
    return _RISK_SAFETY_BUMPS.get(band or "low", _RISK_DEFAULT_BUMP)


def _effective_lead_time_days(demand: DemandProfile) -> Decimal:
    """Risk-adjusted lead time: quoted lead * band multiplier (SKY-86)."""
    return demand.lead_time_days * _effect_multiplier(demand.risk_band)


def _effective_safety_factor(demand: DemandProfile) -> Decimal:
    """Risk-adjusted safety: configured factor + band bump (SKY-86)."""
    return demand.safety_factor + _effect_bump(demand.risk_band)


# ---------------------------------------------------------------------------
# 4-factor confidence scoring (spec 3.2)
# ---------------------------------------------------------------------------


def _four_factor_confidence(
    *,
    product: ProductRef,
    qty_on_hand: Decimal,
    warehouse_id: uuid.UUID,
    movements: list[MovementRow],
) -> Decimal:
    """Weighted confidence from data quality, demand stability, proximity,
    and time since last replenishment."""
    # Filter to this product+warehouse movements.
    relevant = [
        m for m in movements if m.product_id == product.id and m.warehouse_id == warehouse_id
    ]
    issues = [m for m in relevant if m.movement_type == "issue" and m.qty < 0]
    receipts = [m for m in relevant if m.movement_type == "receipt" and m.qty > 0]

    f_quality = _data_quality_factor(relevant)
    f_stability = _demand_stability_factor(issues)
    f_proximity = _proximity_factor(qty_on_hand, product.reorder_point)
    f_recency = _replenishment_recency_factor(receipts)

    raw = (
        f_quality * _W_DATA_QUALITY
        + f_stability * _W_DEMAND_STABILITY
        + f_proximity * _W_PROXIMITY
        + f_recency * _W_REPLENISHMENT_RECENCY
    )
    return max(
        _CONFIDENCE_FLOOR,
        min(_CONFIDENCE_CEILING, raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    )


def _data_quality_factor(movements: list[MovementRow]) -> Decimal:
    """More days of history = higher confidence. Full marks at 90+ days."""
    if not movements:
        return _FACTOR_FLOOR
    now = datetime.now(tz=UTC)
    oldest = min(_as_utc(m.created_at) for m in movements)
    span_days = (now - oldest).days
    return min(_FACTOR_CEILING, Decimal(span_days) / Decimal(_DATA_QUALITY_FULL_DAYS))


def _demand_stability_factor(issues: list[MovementRow]) -> Decimal:
    """Lower coefficient of variation = more stable demand = higher confidence."""
    if len(issues) < 3:
        return Decimal("0.5")  # insufficient data, neutral score
    quantities = [abs(m.qty) for m in issues]
    mean = sum(quantities) / len(quantities)
    if mean == 0:
        return _FACTOR_CEILING
    import statistics

    sigma = Decimal(str(statistics.stdev(float(q) for q in quantities)))
    cv = sigma / Decimal(str(mean)) if mean else Decimal(0)
    if cv <= _CV_STABLE:
        return _FACTOR_CEILING
    if cv >= _CV_ERRATIC:
        return _FACTOR_FLOOR
    # Linear interpolation between stable and erratic.
    span = _CV_ERRATIC - _CV_STABLE
    return (_CV_ERRATIC - cv) / span


def _proximity_factor(qty_on_hand: Decimal, reorder_point: Decimal) -> Decimal:
    """Deeper below reorder = more urgent = higher confidence."""
    if reorder_point <= 0:
        return _FACTOR_FLOOR
    deficit_ratio = (reorder_point - qty_on_hand) / reorder_point
    return min(_FACTOR_CEILING, abs(deficit_ratio))


def _replenishment_recency_factor(receipts: list[MovementRow]) -> Decimal:
    """Longer since last receipt = more urgency = higher confidence."""
    if not receipts:
        return _FACTOR_CEILING  # never replenished = maximum urgency
    latest = max(_as_utc(m.created_at) for m in receipts)
    days_since = (datetime.now(tz=UTC) - latest).days
    return min(_FACTOR_CEILING, Decimal(days_since) / Decimal(_RECENCY_FULL_DAYS))


# ---------------------------------------------------------------------------
# V1 fallback: proximity-only (kept for when no movement history is available)
# ---------------------------------------------------------------------------


def _proximity_confidence(qty_on_hand: Decimal, reorder_point: Decimal) -> Decimal:
    """V1 placeholder: deeper below reorder point => more confident suggestion."""
    if reorder_point <= 0:
        return _CONFIDENCE_FLOOR
    deficit_ratio = (reorder_point - qty_on_hand) / reorder_point
    span = _CONFIDENCE_CEILING - _CONFIDENCE_FLOOR
    return min(_CONFIDENCE_CEILING, _CONFIDENCE_FLOOR + abs(deficit_ratio) * span)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
