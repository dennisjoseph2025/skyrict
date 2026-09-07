"""Unit tests for the finance line snapshot + suggest services (SKY-67 C1).

Feature-layer orchestration with fake adapters (no models/db - import-linter
contract): the snapshot writer embeds each aggregated description and upserts
it (skipping when no provider is configured), and the suggest service embeds
the query, ranks frequent lines first, and degrades (empty, never raises) when
the provider is missing or fails.
"""

from __future__ import annotations

import uuid

import pytest

from ai_agent.core.embedding import EmbeddingResult
from ai_agent.features.finance_lines.search import FinanceLineSuggestService
from ai_agent.features.finance_lines.snapshot import (
    FinanceLineSnapshot,
    FinanceLineSnapshotService,
)

TENANT_ID = uuid.uuid4()
ACCOUNT_ID = uuid.uuid4()


class _FakeEmbeddingProvider:
    name = "openai"
    model = "text-embedding-3-small"
    dims = 4

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.failure: Exception | None = None

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        self.calls.append(texts)
        if self.failure is not None:
            raise self.failure
        return EmbeddingResult(
            vectors=[[0.1, 0.2, 0.3, 0.4] for _ in texts],
            model_used=self.model,
            dims=self.dims,
            latency_ms=7,
        )


class _FakeStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []

    async def upsert(
        self,
        *,
        tenant_id: uuid.UUID,
        description: str,
        account_id: uuid.UUID,
        account_code: str,
        account_name: str,
        times_used: int,
        embedding: list[float],
        embedding_model: str,
        dims: int,
    ) -> None:
        self.upserts.append(
            {
                "tenant_id": tenant_id,
                "description": description,
                "account_id": account_id,
                "account_code": account_code,
                "account_name": account_name,
                "times_used": times_used,
                "embedding": embedding,
                "embedding_model": embedding_model,
                "dims": dims,
            }
        )

    async def delete_all(self, *, tenant_id: uuid.UUID) -> None:
        self.deletes.append({"tenant_id": tenant_id})


class _FakeSearchStore:
    def __init__(self, hits: list[object]) -> None:
        self.hits = hits
        self.queries: list[dict[str, object]] = []

    async def semantic_search(
        self,
        *,
        tenant_id: uuid.UUID,
        query_vector: list[float],
        top_k: int,
    ) -> list[object]:
        self.queries.append(
            {"tenant_id": tenant_id, "query_vector": query_vector, "top_k": top_k}
        )
        return self.hits


def _line(description: str = "Professional services") -> FinanceLineSnapshot:
    return FinanceLineSnapshot(
        description=description,
        account_id=ACCOUNT_ID,
        account_code="4000",
        account_name="Service Revenue",
        times_used=1,
    )


def _hit(
    *,
    description: str = "Professional services",
    times_used: int = 1,
    distance: float = 0.2,
) -> object:
    attrs: dict[str, object] = {
        "description": description,
        "account_code": "4000",
        "account_name": "Service Revenue",
        "times_used": times_used,
        "cosine_distance": distance,
        "embedding_model": "text-embedding-3-small",
    }
    fake_hit = type("FakeHit", (), attrs)
    return fake_hit()


class TestFinanceLineSnapshotService:
    async def test_embeds_and_upserts_each_line_batch(self) -> None:
        provider = _FakeEmbeddingProvider()
        store = _FakeStore()
        service = FinanceLineSnapshotService(embedding_provider=provider, store=store)

        report = await service.apply(
            tenant_id=TENANT_ID,
            upserts=[_line("Professional services"), _line("Travel reimbursement")],
        )

        assert provider.calls == [["Professional services", "Travel reimbursement"]]
        assert [entry["description"] for entry in store.upserts] == [
            "Professional services",
            "Travel reimbursement",
        ]
        assert store.upserts[0]["account_code"] == "4000"
        assert all(
            entry["embedding"] == [0.1, 0.2, 0.3, 0.4] and entry["dims"] == 4
            for entry in store.upserts
        )
        assert report.upserts_applied == 2
        assert report.skipped is False
        assert report.model_used == "text-embedding-3-small"

    async def test_skips_upserts_without_embedding_provider(self) -> None:
        store = _FakeStore()
        service = FinanceLineSnapshotService(embedding_provider=None, store=store)

        report = await service.apply(tenant_id=TENANT_ID, upserts=[_line()])

        assert store.upserts == []
        assert report.upserts_applied == 0
        assert report.skipped is True
        assert report.model_used is None

    async def test_embeds_nothing_when_no_rows(self) -> None:
        provider = _FakeEmbeddingProvider()
        store = _FakeStore()
        service = FinanceLineSnapshotService(embedding_provider=provider, store=store)

        report = await service.apply(tenant_id=TENANT_ID, upserts=[])

        assert provider.calls == []
        assert report.upserts_applied == 0
        assert report.skipped is False
        assert report.dims is None


class TestFinanceLineSuggestService:
    async def test_suggests_most_used_lines_first(self) -> None:
        provider = _FakeEmbeddingProvider()
        store = _FakeSearchStore(
            [
                _hit(description="Consulting", times_used=1, distance=0.05),
                _hit(description="Professional services", times_used=9, distance=0.2),
            ]
        )
        service = FinanceLineSuggestService(embedding_provider=provider, store=store)

        result = await service.suggest(description="Professional ", tenant_id=TENANT_ID)

        assert not result.degraded
        assert result.model_used == "text-embedding-3-small"
        assert [item.description for item in result.data] == [
            "Professional services",
            "Consulting",
        ]
        assert result.data[0].times_used == 9
        assert result.data[0].score == pytest.approx(0.8)
        assert store.queries[0]["tenant_id"] == TENANT_ID
        assert store.queries[0]["top_k"] == 6
        assert store.queries[0]["query_vector"] == [0.1, 0.2, 0.3, 0.4]

    async def test_degrades_to_empty_without_provider(self) -> None:
        store = _FakeSearchStore([])
        service = FinanceLineSuggestService(embedding_provider=None, store=store)

        result = await service.suggest(description="Consulting", tenant_id=TENANT_ID)

        assert result.data == []
        assert result.degraded is True
        assert store.queries == []

    async def test_blank_description_returns_empty_without_query(self) -> None:
        store = _FakeSearchStore([])
        service = FinanceLineSuggestService(
            embedding_provider=_FakeEmbeddingProvider(), store=store
        )

        result = await service.suggest(description="   ", tenant_id=TENANT_ID)

        assert result.data == []
        assert result.degraded is True
        assert store.queries == []

    async def test_provider_failure_degrades_to_empty(self) -> None:
        provider = _FakeEmbeddingProvider()
        provider.failure = RuntimeError("provider down")
        store = _FakeSearchStore([])
        service = FinanceLineSuggestService(embedding_provider=provider, store=store)

        result = await service.suggest(description="Consulting", tenant_id=TENANT_ID)

        assert result.data == []
        assert result.degraded is True
