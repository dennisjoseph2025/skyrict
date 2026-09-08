"""/ai/supplier-risk endpoints - supplier risk grades (SKY-86 / INV-AI-004).

Authn here; authz at the core proxy edge (erp.ai.invoke + erp.inventory.read
for the read - checked before forwarding). The repository returns the latest
deterministic grade computed by the risk reindex.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.db.supplier_risk_repository import SupplierRiskRepository

router = APIRouter(prefix="/ai/supplier-risk", tags=["ai-supplier-risk"])


class SupplierRiskItem(BaseModel):
    supplier_id: str
    score: str
    risk_band: str
    confidence: str
    reason: str


class SupplierRiskListResponse(BaseModel):
    data: list[SupplierRiskItem]
    meta: dict[str, Any]


@router.get("", response_model=SupplierRiskListResponse)
async def list_supplier_risk(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SupplierRiskListResponse:
    """Latest risk grades for this tenant's suppliers (newest-first not defined;
    table is one row per supplier)."""
    grades = await SupplierRiskRepository(session).list_all(tenant_id=user["tenant_id"])
    return SupplierRiskListResponse(
        data=[
            SupplierRiskItem(
                supplier_id=str(grade.supplier_id),
                score=str(grade.score),
                risk_band=grade.risk_band,
                confidence=str(grade.confidence),
                reason=grade.reason,
            )
            for grade in grades
        ],
        meta={"count": len(grades)},
    )
