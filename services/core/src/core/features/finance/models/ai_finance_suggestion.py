"""ai_finance_suggestions - persisted account-code suggestion rows.

Upserted on account-code suggestion (deduped on tenant + description +
feature hash) and accepted/dismissed by humans (SKY-66). ``status`` moves
pending -> accepted|dismissed; the acceptance rate per feature feeds
``ai_finance_quality_scores`` (SKY-67 acceptance telemetry)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class AiFinanceSuggestionModel(Base):
    __tablename__ = "ai_finance_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "description",
            "feature",
            name="uq_ai_finance_suggestions_tenant_description_feature",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'dismissed')",
            name="ck_ai_finance_suggestions_status",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    feature: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'account_suggest'")
    )
    suggested_code: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_name: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    lines_json: Mapped[list[object] | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
