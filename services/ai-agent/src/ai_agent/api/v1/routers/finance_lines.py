"""Finance invoice-line suggestion router (SKY-67 C1).

Retrieves the tenant's most similar past invoice lines for the text the user
is typing in the invoice form. Backed by a read-only pgvector snapshot
maintained by the ``finance reindex`` CLI; a missing embedding provider
degrades to an empty suggestion list (never a 503) so the form always falls
back to manual entry.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.finance_lines import (
    FinanceLineSuggestionItem,
    FinanceLineSuggestRequest,
    FinanceLineSuggestResponse,
)
from ai_agent.core.config import settings
from ai_agent.core.embedding import build_embedding_provider
from ai_agent.db.finance_line_embedding_repository import FinanceLineEmbeddingRepository
from ai_agent.features.finance_lines.search import FinanceLineSuggestService

router = APIRouter(prefix="/ai/finance/lines", tags=["ai-finance-lines"])


def get_finance_line_suggest_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FinanceLineSuggestService:
    return FinanceLineSuggestService(
        embedding_provider=build_embedding_provider(settings),
        store=FinanceLineEmbeddingRepository(session),
    )


@router.post("/suggest", response_model=FinanceLineSuggestResponse)
async def suggest_invoice_lines(
    body: FinanceLineSuggestRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[FinanceLineSuggestService, Depends(get_finance_line_suggest_service)],
) -> FinanceLineSuggestResponse:
    result = await service.suggest(
        description=body.description,
        tenant_id=user["tenant_id"],
    )
    return FinanceLineSuggestResponse(
        data=[
            FinanceLineSuggestionItem(
                description=item.description,
                account_code=item.account_code,
                account_name=item.account_name,
                times_used=item.times_used,
                score=item.score,
            )
            for item in result.data
        ],
        degraded=result.degraded,
        model_used=result.model_used,
        latency_ms=result.latency_ms,
    )
