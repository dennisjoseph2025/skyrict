"""Tenant-scoped access to ai_supplier_risk (SKY-86 / INV-AI-004).

The supplier-risk reindex upserts one row per (tenant, supplier) on every run
so the table is always a fresh grade; the v2 restock formula then reads the
band back to stretch the effective replenishment lead time. Uses Postgres
``ON CONFLICT DO UPDATE`` - reindexes are idempotent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ai_agent.domain.supplier_risk import RiskBand, SupplierRiskAssessment
from ai_agent.models.ai_supplier_risk import AiSupplierRiskModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class SupplierRiskRepository:
    """Persistence for per-supplier risk grades."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, *, tenant_id: uuid.UUID, grade: SupplierRiskAssessment) -> None:
        """Upsert one supplier grade; concurrent reindexes converge."""
        values = {
            "tenant_id": tenant_id,
            "supplier_id": grade.supplier_id,
            "score": str(grade.score),
            "risk_band": grade.risk_band,
            "confidence": str(grade.confidence),
            "reason": grade.reason,
            "generated_at": func.now(),
        }
        insert_stmt = insert(AiSupplierRiskModel).values(**values)
        insert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["tenant_id", "supplier_id"],
            set_={
                "score": insert_stmt.excluded.score,
                "risk_band": insert_stmt.excluded.risk_band,
                "confidence": insert_stmt.excluded.confidence,
                "reason": insert_stmt.excluded.reason,
                "generated_at": func.now(),
            },
        )
        await self.session.execute(insert_stmt)

    async def list_all(self, *, tenant_id: uuid.UUID) -> list[SupplierRiskAssessment]:
        """All supplier grades for one tenant (latest snapshot)."""
        result = await self.session.execute(
            select(AiSupplierRiskModel)
            .where(AiSupplierRiskModel.tenant_id == tenant_id)
            .order_by(AiSupplierRiskModel.supplier_id)
        )
        return [_to_grade(row) for row in result.scalars().all()]


def _to_grade(row: AiSupplierRiskModel) -> SupplierRiskAssessment:
    return SupplierRiskAssessment(
        supplier_id=row.supplier_id,
        score=row.score,
        risk_band=cast("RiskBand", row.risk_band),
        confidence=row.confidence,
        reason=row.reason or "",
    )
