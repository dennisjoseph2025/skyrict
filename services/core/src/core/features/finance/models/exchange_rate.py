"""erp_exchange_rates - tenant FX rates (SKY-67 C2).

One row per (tenant, base_currency, quote_currency, effective_date). Invoice
prices live in the invoice's own ``currency``; ``rate`` converts one unit of
``quote_currency`` into ``base_currency`` (a USD-base tenant storing an INR
invoice keeps the USD-per-INR price here).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ErpExchangeRateModel(Base):
    __tablename__ = "erp_exchange_rates"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    base_currency: Mapped[str] = mapped_column(String(3), primary_key=True, nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), primary_key=True, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
