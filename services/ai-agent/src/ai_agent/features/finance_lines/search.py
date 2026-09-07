"""Invoice line-item suggestion (SKY-67 C1) - feature layer.

Embeds the text the user typed in the invoice dialog and retrieves the closest
past lines from the tenant's snapshot, ranking frequent lines first. Never
raises: a missing/failed embedding provider degrades to an empty suggestion
list so the dialog always falls back to manual entry.

Layering (import-linter "feature layer, no models/db"): the store is a
protocol implemented by the DB repository. Query text never appears in logs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import structlog

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.embedding import EmbeddingProvider
    from ai_agent.db.finance_line_embedding_repository import FinanceLineEmbeddingHit

logger = structlog.get_logger("ai_agent.finance_lines_suggest")

_DEFAULT_TOP_K = 6


@dataclass(frozen=True, slots=True)
class FinanceLineSuggestion:
    """One suggested line item for the invoice form (never auto-inserted)."""

    description: str
    account_code: str
    account_name: str
    times_used: int
    score: float


@dataclass(frozen=True, slots=True)
class FinanceLineSuggestResult:
    """One suggest execution with degradation status."""

    data: list[FinanceLineSuggestion]
    degraded: bool
    model_used: str | None
    latency_ms: int


class FinanceLineSearchStore(Protocol):
    """Persistence contract (implemented by db/finance_line_embedding_repository)."""

    async def semantic_search(
        self,
        *,
        tenant_id: uuid.UUID,
        query_vector: list[float],
        top_k: int,
    ) -> list[FinanceLineEmbeddingHit]: ...


class FinanceLineSuggestService:
    """Retrieves the tenant's most relevant past line items for a description."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None,
        store: FinanceLineSearchStore,
        top_k: int = _DEFAULT_TOP_K,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self._embeddings = embedding_provider
        self._store = store
        self._top_k = top_k

    async def suggest(
        self,
        *,
        description: str,
        tenant_id: uuid.UUID,
    ) -> FinanceLineSuggestResult:
        started = time.perf_counter()
        normalized = description.strip()
        if not normalized or self._embeddings is None:
            return FinanceLineSuggestResult(
                data=[], degraded=True, model_used=None, latency_ms=0
            )

        try:
            embedded = await self._embeddings.embed([normalized])
            vector = embedded.vectors[0]
            hits = await self._store.semantic_search(
                tenant_id=tenant_id,
                query_vector=vector,
                top_k=self._top_k,
            )
        except Exception as exc:
            logger.warning("finance_lines_suggest.degraded", error=str(exc))
            return FinanceLineSuggestResult(
                data=[], degraded=True, model_used=None, latency_ms=0
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        data = [
            FinanceLineSuggestion(
                description=hit.description,
                account_code=hit.account_code,
                account_name=hit.account_name,
                times_used=hit.times_used,
                score=round(1.0 - hit.cosine_distance, 4),
            )
            for hit in sorted(
                hits, key=lambda hit: (-hit.times_used, hit.cosine_distance)
            )
        ]
        logger.info(
            "finance_lines_suggest.completed",
            tenant_id=str(tenant_id),
            hits=len(data),
            latency_ms=latency_ms,
        )
        return FinanceLineSuggestResult(
            data=data,
            degraded=False,
            model_used=embedded.model_used,
            latency_ms=latency_ms,
        )
