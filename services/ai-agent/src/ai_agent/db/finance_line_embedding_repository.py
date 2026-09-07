"""Persistence for the per-tenant invoice line-item snapshot (SKY-67 C1).

One row per ``(tenant_id, description)`` holds the description's 768-dim
embedding, the account it was most often posted to, and a usage count. Writes
happen ONLY via the ``finance reindex`` CLI (never a request path); ``upsert``
``delete_all`` are idempotent so re-running a reindex is safe. Search reads
via ``semantic_search`` on the invoice-form suggest hot path.

RLS bounds every row to the current session tenant; the caller must populate
:class:`ai_agent.core.tenant_context.TenantContext` (session GUC) before
writing, or the writes silently match no rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ai_agent.models.ai_finance_line_embedding import AiFinanceLineEmbeddingModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class FinanceLineEmbeddingHit:
    """One line row retrieved by vector similarity."""

    description: str
    account_id: uuid.UUID
    account_code: str
    account_name: str
    times_used: int
    cosine_distance: float
    embedding_model: str


class FinanceLineEmbeddingRepository:
    """Tenant-scoped access to the invoice line-item snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        """Insert or replace one line row keyed by ``(tenant_id, description)``."""
        if len(embedding) != dims:
            raise ValueError(f"vector dimension {len(embedding)} != expected {dims}")
        stmt = pg_insert(AiFinanceLineEmbeddingModel).values(
            tenant_id=tenant_id,
            description=description,
            account_id=account_id,
            account_code=account_code,
            account_name=account_name,
            times_used=times_used,
            embedding=embedding,
            embedding_model=embedding_model,
            embedding_dims=dims,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                AiFinanceLineEmbeddingModel.tenant_id,
                AiFinanceLineEmbeddingModel.description,
            ],
            set_={
                "account_id": account_id,
                "account_code": account_code,
                "account_name": account_name,
                "times_used": times_used,
                "embedding": embedding,
                "embedding_model": embedding_model,
                "embedding_dims": dims,
            },
        )
        await self.session.execute(stmt)

    async def delete_all(self, *, tenant_id: uuid.UUID) -> None:
        """Wipe the tenant's snapshot (used by ``finance reindex --full``)."""
        await self.session.execute(
            delete(AiFinanceLineEmbeddingModel).where(
                AiFinanceLineEmbeddingModel.tenant_id == tenant_id
            )
        )

    async def semantic_search(
        self,
        *,
        tenant_id: uuid.UUID,
        query_vector: list[float],
        top_k: int,
    ) -> list[FinanceLineEmbeddingHit]:
        """Cosine-similarity search over line embeddings (ivfflat)."""
        distance = AiFinanceLineEmbeddingModel.embedding.cosine_distance(query_vector)
        stmt = (
            select(AiFinanceLineEmbeddingModel, distance)
            .where(AiFinanceLineEmbeddingModel.tenant_id == tenant_id)
            .order_by(distance)
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return [
            FinanceLineEmbeddingHit(
                description=row.description,
                account_id=row.account_id,
                account_code=row.account_code,
                account_name=row.account_name,
                times_used=row.times_used,
                cosine_distance=float(distance_value),
                embedding_model=row.embedding_model,
            )
            for row, distance_value in result.all()
        ]
