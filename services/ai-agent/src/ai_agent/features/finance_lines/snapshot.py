"""Invoice line-item snapshot writer (SKY-67 C1) - feature layer.

Embeds and persists one tenant's invoice line history (description text +
most-frequent account + usage count) that the invoice-form suggest endpoint
searches. The only write surface is the ``finance reindex`` CLI - no request
path ever writes the snapshot.

Degradation contract: with no embedding provider the writer skips upserts and
reports ``skipped=True`` instead of erroring (the reindex CLI is stricter and
refuses to start without a provider - see ``ai_agent/finance_reindex.py``).

Layering (import-linter "feature layer, no models/db"): the store is a
protocol implemented by the DB repository, injected at the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import structlog

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.embedding import EmbeddingProvider

logger = structlog.get_logger("ai_agent.finance_lines_snapshot")


@dataclass(frozen=True, slots=True)
class FinanceLineSnapshot:
    """One aggregate invoice-line row: description + canonical account + count.

    ``account_id`` is the account the description was most often posted to
    across the tenant's history (resolved to code/name by the loader).
    """

    description: str
    account_id: uuid.UUID
    account_code: str
    account_name: str
    times_used: int = 1


@dataclass(frozen=True, slots=True)
class FinanceLineSnapshotReport:
    """Outcome of one reindex apply for audit + logging."""

    upserts_applied: int
    skipped: bool
    model_used: str | None
    dims: int | None


class FinanceLineSnapshotStore(Protocol):
    """Write contract implemented by db/finance_line_embedding_repository."""

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
    ) -> None: ...

    async def delete_all(self, *, tenant_id: uuid.UUID) -> None: ...


class FinanceLineSnapshotService:
    """Embeds and persists aggregated invoice-line rows for one tenant."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None,
        store: FinanceLineSnapshotStore,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._store = store

    async def apply(
        self,
        *,
        tenant_id: uuid.UUID,
        upserts: list[FinanceLineSnapshot],
    ) -> FinanceLineSnapshotReport:
        """Embed and upsert one batch of aggregated line rows."""
        provider = self._embedding_provider
        if provider is None:
            if upserts:
                logger.warning(
                    "finance_lines_snapshot.upserts_skipped",
                    tenant_id=str(tenant_id),
                    reason="no embedding provider configured",
                    count=len(upserts),
                )
            return FinanceLineSnapshotReport(
                upserts_applied=0, skipped=bool(upserts), model_used=None, dims=None
            )

        if not upserts:
            return FinanceLineSnapshotReport(
                upserts_applied=0, skipped=False, model_used=None, dims=None
            )

        texts = [row.description for row in upserts]
        embedded = await provider.embed(texts)
        for row, vector in zip(upserts, embedded.vectors, strict=True):
            await self._store.upsert(
                tenant_id=tenant_id,
                description=row.description,
                account_id=row.account_id,
                account_code=row.account_code,
                account_name=row.account_name,
                times_used=row.times_used,
                embedding=vector,
                embedding_model=embedded.model_used,
                dims=embedded.dims,
            )
        return FinanceLineSnapshotReport(
            upserts_applied=len(upserts),
            skipped=False,
            model_used=embedded.model_used,
            dims=embedded.dims,
        )
