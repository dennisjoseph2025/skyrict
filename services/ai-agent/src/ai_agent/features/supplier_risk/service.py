"""Supplier-risk reindex orchestration (SKY-86 / INV-AI-004).

Composes the pure contribution of :mod:`.scorer` (deterministic risk grade
per supplier) with the fetched snapshots from :mod:`.loader`. This slice is a
pure pipeline: snapshots (catalog + facts) in, a list of computed grades out -
no database or HTTP access here (the ``db`` repository and the REST loader both
live outside the feature boundary and are composed at the exercise root).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_agent.features.supplier_risk.scorer import assess_supplier_risk

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from ai_agent.domain.supplier_risk import SupplierRiskAssessment
    from ai_agent.features.supplier_risk.loader import SupplierSnapshot


class SupplierRiskService:
    """Compute one supplier's risk grade from its snapshot + facts."""

    def grade(self, snapshot: SupplierSnapshot, *, as_of: date) -> SupplierRiskAssessment | None:
        """Generate the risk assessment for one supplier snapshot."""
        return assess_supplier_risk(
            snapshot.performance,
            lead_time_days=snapshot.lead_time_days,
            as_of=as_of,
        )

    def grade_all(
        self,
        snapshots: list[SupplierSnapshot],
        *,
        as_of: date,
        tenant_id: uuid.UUID,
    ) -> list[tuple[uuid.UUID, SupplierRiskAssessment]]:
        """Grade every snapshot; returns ``(tenant_id, grade)`` pairs for upsert."""
        graded: list[tuple[uuid.UUID, SupplierRiskAssessment]] = []
        for snapshot in snapshots:
            grade = self.grade(snapshot, as_of=as_of)
            if grade is not None:
                graded.append((tenant_id, grade))
        return graded
