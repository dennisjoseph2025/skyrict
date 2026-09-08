"""Unit tests for the finance eval-run repository (FIN-AI-002).

String-level verification against the PostgreSQL dialect pins the INSERT
shape: RETURNING is needed so the runner can print persisted ids, and the
feature/prompt_id/detail columns must reach their typed columns.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.dialects import postgresql

from ai_agent.db.finance_eval_runs_repository import FinanceEvalRunsRepository


class _Result:
    def scalar_one(self) -> object:
        return object()


class _FakeSession:
    def __init__(self) -> None:
        self.executed: list[object] = []

    async def execute(self, statement: object) -> _Result:
        self.executed.append(statement)
        return _Result()


def _compile(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[arg-type]


async def test_insert_run_persists_feature_row() -> None:
    session = _FakeSession()
    repo = FinanceEvalRunsRepository(session)  # type: ignore[arg-type]
    row = await repo.insert_run(
        feature="a7_narrate",
        prompt_id="prompts-v1-2026-09",
        model_used="gpt-4o-mini",
        considered=5,
        abstained=1,
        precision=Decimal("0.8000"),
        passed=True,
        details={"a7-001": "correct"},
    )

    assert row is not None
    assert len(session.executed) == 1
    sql = _compile(session.executed[0])
    assert "INSERT INTO ai_finance_eval_runs" in sql
    assert "RETURNING ai_finance_eval_runs" in sql
    assert "feature" in sql
    assert "prompt_id" in sql
    assert "model_used" in sql
    assert "considered" in sql
    assert "abstained" in sql
    assert "precision" in sql
    assert "passed" in sql
    assert "details" in sql


async def test_insert_run_allows_null_precision() -> None:
    """A run that wholly abstained (no considered cases) still records a row."""
    session = _FakeSession()
    repo = FinanceEvalRunsRepository(session)  # type: ignore[arg-type]
    await repo.insert_run(
        feature="a2_draft",
        prompt_id="prompts-v1-2026-09",
        model_used="",
        considered=0,
        abstained=3,
        precision=None,
        passed=False,
        details={"x": "abstained"},
    )

    sql = _compile(session.executed[0])
    assert "INSERT INTO ai_finance_eval_runs" in sql
    assert "precision" in sql
