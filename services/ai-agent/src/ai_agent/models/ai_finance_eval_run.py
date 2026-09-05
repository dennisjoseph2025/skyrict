"""ai_finance_eval_runs - finance prompt-eval run results (FIN-AI-002).

Global (not tenant-scoped) table recording nightly finance prompt evaluations,
one row per evaluated feature (a1_suggest / a2_draft / a7_narrate / a8_remind).
Each row stores the feature, registry prompt_id used, the responding model,
the observed precision over considered cases, an abstention count, the
pass/fail verdict against the registry threshold, and a details JSONB with
per-case scores for drill-down.

Mirrors ai_eval_runs (RAGAS) but deliberately separate: finance eval runs are
experimental prompt-quality signals and must not pollute the RAGAS gate's
``passed``-driven history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiFinanceEvalRunModel(Base):
    """One finance prompt-evaluation feature row."""

    __tablename__ = "ai_finance_eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    feature: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_used: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("''")
    )
    considered: Mapped[int] = mapped_column(Integer, nullable=False)
    abstained: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    precision: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
