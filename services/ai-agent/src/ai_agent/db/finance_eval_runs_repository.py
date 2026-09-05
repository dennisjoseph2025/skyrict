"""Persistence for ai_finance_eval_runs - finance prompt-eval rows (FIN-AI-002).

One row per evaluated feature per night. The table is global (cross-tenant,
no tenant_id column, no RLS) and append-only: the nightly ``eval-finance``
warns (never gates) and records historical precision, so prompt regressions
are visible in the DB before they reach users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import insert

from ai_agent.models.ai_finance_eval_run import AiFinanceEvalRunModel

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession


class FinanceEvalRunsRepository:
    """Write path for finance eval rows (read path: none yet)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_run(
        self,
        *,
        feature: str,
        prompt_id: str,
        model_used: str,
        considered: int,
        abstained: int,
        precision: Decimal | None,
        passed: bool,
        details: dict[str, object],
    ) -> AiFinanceEvalRunModel:
        """Persist one feature evaluation and return the stored row."""
        stmt = (
            insert(AiFinanceEvalRunModel)
            .values(
                feature=feature,
                prompt_id=prompt_id,
                model_used=model_used,
                considered=considered,
                abstained=abstained,
                precision=precision,
                passed=passed,
                details=details,
            )
            .returning(AiFinanceEvalRunModel)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
