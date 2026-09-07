"""ai_supplier_risk - per-tenant supplier risk grade (SKY-86 / INV-AI-004).

Holds the latest deterministic risk score + band + confidence + reason the
supplier-risk engine computed from a supplier's grading-period facts. The
``effective_lead_time = quoted_lead_time * multiplier(risk_band)`` adjustment
in the v2 restock formula is what consumes the ``risk_band`` column.

Composite PK ``(tenant_id, supplier_id)``; composite FK into core-owned
``erp_suppliers`` (cross-service idiom - that table is owned by core in the
same shared database). ``score`` is 0-1, ``confidence`` is 0-1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiSupplierRiskModel(Base):
    __tablename__ = "ai_supplier_risk"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["erp_suppliers.tenant_id", "erp_suppliers.id"],
            ondelete="CASCADE",
            name="fk_ai_supplier_risk_supplier_tenant",
        ),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_ai_supplier_risk_score_range"),
        CheckConstraint("risk_band IN ('low', 'medium', 'high')", name="ck_ai_supplier_risk_band"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ai_supplier_risk_confidence_range",
        ),
        Index("idx_ai_supplier_risk_tenant_band", "tenant_id", "risk_band"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default=text("0"))
    risk_band: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.5")
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
