"""Tenant-scoped supplier ORM model - RLS-protected, composite primary key.

Follows the 0001 composite-FK convention: ``tenant_id`` is both the RLS column
and a member of the primary key. Suppliers are the SKY-86 (INV-AI-004) vendor
master; their grading facts live in ``erp_supplier_performance``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ErpSupplierModel(Base):
    __tablename__ = "erp_suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_erp_suppliers_tenant_name"),
        CheckConstraint("lead_time_days >= 0", name="ck_erp_suppliers_lead_time_non_negative"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("7"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
