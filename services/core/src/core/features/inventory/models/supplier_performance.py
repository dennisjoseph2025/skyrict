"""Supplier grading-period ORM model - raw risk-scoring input facts.

One row per supplier per period (unique on tenant/supplier/period). Holds the
raw dimension facts - on-time delivery %, defect %, price-stability index,
responsiveness in days - that the SKY-86 (INV-AI-004) supplier risk engine
consumes. Facts are stored so a score change is auditable against its inputs;
DB CHECKs keep each dimension inside its domain range.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ErpSupplierPerformanceModel(Base):
    __tablename__ = "erp_supplier_performance"
    __table_args__ = (
        Index(
            "ix_erp_supplier_performance_tenant_supplier_period",
            "tenant_id",
            "supplier_id",
            "period_start",
        ),
        # Composite-FK convention: a performance row only ever references a
        # supplier in the SAME tenant - referential integrity agrees with RLS.
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["erp_suppliers.tenant_id", "erp_suppliers.id"],
            ondelete="CASCADE",
            name="fk_erp_supplier_performance_supplier_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "supplier_id",
            "period_start",
            "period_end",
            name="uq_erp_supplier_performance_period",
        ),
        CheckConstraint(
            "period_end >= period_start", name="ck_erp_supplier_performance_period_range"
        ),
        CheckConstraint(
            "on_time_delivery_pct >= 0 AND on_time_delivery_pct <= 100",
            name="ck_erp_supplier_performance_otd_range",
        ),
        CheckConstraint(
            "defect_rate_pct >= 0 AND defect_rate_pct <= 100",
            name="ck_erp_supplier_performance_defect_range",
        ),
        CheckConstraint(
            "price_stability_index >= 0 AND price_stability_index <= 100",
            name="ck_erp_supplier_performance_price_range",
        ),
        CheckConstraint(
            "responsiveness_days >= 0",
            name="ck_erp_supplier_performance_responsiveness_non_negative",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    on_time_delivery_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    defect_rate_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    price_stability_index: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    responsiveness_days: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
