"""Pure value objects for the supplier-risk layer (SKY-86 / INV-AI-004).

``SupplierPerformanceFacts`` is the raw per-grading-period input pulled from
core's ``erp_supplier_performance``; ``SupplierRiskAssessment`` is the computed
grade (score + band + confidence + reason). They live in the domain layer so
both the feature-side scorer (features.supplier_risk.scorer) and the
persistence side (db.supplier_risk_repository) can consume them without
importing each other. Stdlib types only - no framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import uuid
    from datetime import date
    from decimal import Decimal

RiskBand = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class SupplierPerformanceFacts:
    """One supplier's grading-period fact set (raw risk-dimension inputs)."""

    supplier_id: uuid.UUID
    period_start: date
    period_end: date
    on_time_delivery_pct: Decimal
    defect_rate_pct: Decimal
    price_stability_index: Decimal
    responsiveness_days: Decimal


@dataclass(frozen=True, slots=True)
class SupplierRiskAssessment:
    """The computed deterministic risk grade for one supplier."""

    supplier_id: uuid.UUID
    score: Decimal
    risk_band: RiskBand
    confidence: Decimal
    reason: str
