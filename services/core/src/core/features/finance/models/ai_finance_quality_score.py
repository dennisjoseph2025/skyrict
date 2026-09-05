"""ai_finance_quality_scores - per-feature acceptance-rate snapshots (SKY-67).

The finance automation quality endpoint aggregates human accept/dismiss
decisions over a rolling window and writes one row per (feature, window_days).
``below_threshold`` flags an acceptance rate under the 30% spec threshold only
when there is signal (at least one decision in the window) - no decisions is
"no opinion", not "bad quality". Mirrors ``ai_hr_quality_scores`` style.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class AiFinanceQualityScoreModel(Base):
    __tablename__ = "ai_finance_quality_scores"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "feature",
            "window_days",
            name="uq_ai_finance_quality_scores_feature_window",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    feature: Mapped[str] = mapped_column(String(16), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    acceptance_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    below_threshold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
