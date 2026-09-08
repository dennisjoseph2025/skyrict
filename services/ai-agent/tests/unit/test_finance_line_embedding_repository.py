"""Unit tests for the finance line-embedding repository (SKY-67 C1).

The repository is pure orchestration over the SQLAlchemy session, so a fake
session records the emitted statements instead of hitting Postgres: upserts
must be idempotent (``ON CONFLICT`` on ``(tenant_id, description)``), deletes
must be tenant-scoped, and semantic search must filter the tenant and order by
cosine distance.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy
from sqlalchemy.dialects.postgresql import dialect as pg_dialect

from ai_agent.db.finance_line_embedding_repository import FinanceLineEmbeddingRepository
from ai_agent.models.ai_finance_line_embedding import AiFinanceLineEmbeddingModel

TENANT_ID = uuid.uuid4()
ACCOUNT_ID = uuid.uuid4()


class _FakeSession:
    """Records executed statements - no real SQL."""

    def __init__(self) -> None:
        self.executed: list[object] = []

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)
        return None


class _Cursor:
    """Minimal result cursor for the retrieval-path queries."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _RetrievalFakeSession:
    """Session that returns queued cursors from ``execute``."""

    def __init__(self, cursors: list[_Cursor]) -> None:
        self._cursors = list(cursors)
        self.executed: list[object] = []

    async def execute(self, statement: object) -> _Cursor:
        self.executed.append(statement)
        return self._cursors.pop(0) if self._cursors else _Cursor([])


def _compile(statement: object) -> str:
    return str(statement.compile(dialect=pg_dialect(), compile_kwargs={"literal_binds": True}))


def _snapshot_row(description: str = "Professional services") -> AiFinanceLineEmbeddingModel:
    return AiFinanceLineEmbeddingModel(
        tenant_id=TENANT_ID,
        description=description,
        account_id=ACCOUNT_ID,
        account_code="4000",
        account_name="Service Revenue",
        times_used=3,
    )


class TestUpsert:
    async def test_inserts_with_on_conflict_update_on_tenant_and_description(self) -> None:
        session = _FakeSession()
        repo = FinanceLineEmbeddingRepository(session)  # type: ignore[arg-type]
        await repo.upsert(
            tenant_id=TENANT_ID,
            description="Professional services",
            account_id=ACCOUNT_ID,
            account_code="4000",
            account_name="Service Revenue",
            times_used=3,
            embedding=[0.1, 0.2, 0.3, 0.4],
            embedding_model="text-embedding-3-small",
            dims=4,
        )

        assert len(session.executed) == 1
        statement = session.executed[0]
        assert getattr(statement, "table", None) is not None
        compiled = _compile(statement)
        assert "INSERT INTO ai_finance_line_embeddings" in compiled
        assert "ON CONFLICT" in compiled
        assert "Professional services" in compiled
        assert "text-embedding-3-small" in compiled

    async def test_dimension_mismatch_raises(self) -> None:
        session = _FakeSession()
        repo = FinanceLineEmbeddingRepository(session)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="dimension"):
            await repo.upsert(
                tenant_id=TENANT_ID,
                description="x",
                account_id=ACCOUNT_ID,
                account_code="",
                account_name="",
                times_used=1,
                embedding=[0.1],  # dim 1 != 768
                embedding_model="m",
                dims=768,
            )


class TestDeleteAll:
    async def test_delete_all_scoped_to_tenant(self) -> None:
        session = _FakeSession()
        repo = FinanceLineEmbeddingRepository(session)  # type: ignore[arg-type]
        await repo.delete_all(tenant_id=TENANT_ID)

        assert len(session.executed) == 1
        statement = session.executed[0]
        assert isinstance(statement, sqlalchemy.Delete)
        compiled = str(statement.compile(dialect=pg_dialect()))
        assert "DELETE FROM ai_finance_line_embeddings" in compiled
        assert "ai_finance_line_embeddings.tenant_id" in compiled


class TestSemanticSearch:
    async def test_filters_tenant_and_orders_by_cosine_distance_with_limit(self) -> None:
        row = _snapshot_row()
        session = _RetrievalFakeSession([_Cursor([(row, 0.15)])])
        repo = FinanceLineEmbeddingRepository(session)  # type: ignore[arg-type]

        hits = await repo.semantic_search(tenant_id=TENANT_ID, query_vector=[0.1, 0.2], top_k=6)

        assert len(hits) == 1
        assert hits[0].description == "Professional services"
        assert hits[0].account_code == "4000"
        assert hits[0].account_name == "Service Revenue"
        assert hits[0].times_used == 3
        assert hits[0].cosine_distance == pytest.approx(0.15)
        compiled = str(session.executed[0].compile(dialect=pg_dialect()))
        assert "ai_finance_line_embeddings.tenant_id" in compiled
        assert "ai_finance_line_embeddings.embedding <=>" in compiled
        assert "LIMIT" in compiled
