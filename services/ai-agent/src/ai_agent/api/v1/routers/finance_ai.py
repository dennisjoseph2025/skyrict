"""/ai/finance/* LLM endpoints - draft entry, anomaly narration, reminders (FIN-AI-002).

Authentication happens here (JWT re-verification); authorization happens
upstream at the core monolith proxy (``erp.finance.read`` / ``erp.finance.ai.read``)
before any request reaches this service, matching the account-suggest posture.
The core client relays the caller's ``Authorization`` and tenant slug unchanged,
so ai-agent sees exactly the identity the core proxy already vetted.

Each endpoint is stateless: the chart of accounts / anomaly / invoice context is
sent in the request body and the LLM primitives in
:mod:`ai_agent.features.account_suggest.suggest` produce strict JSON or abstain
(``None`` -> empty fields, letting core fall back to deterministic logic).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ai_agent.api.deps import get_current_user
from ai_agent.features.account_suggest.schemas import AccountOption, SuggestRequest
from ai_agent.features.account_suggest.suggest import (
    draft_entry as llm_draft_entry,
)
from ai_agent.features.account_suggest.suggest import (
    draft_reminder as llm_draft_reminder,
)
from ai_agent.features.account_suggest.suggest import (
    narrate_anomaly as llm_narrate_anomaly,
)


class AccountIn(BaseModel):
    code: str
    name: str


class DraftPayload(BaseModel):
    description: str
    accounts: list[AccountIn]


class DraftLineOut(BaseModel):
    account_code: str
    account_name: str
    amount: float
    side: str
    description: str


class DraftResponse(BaseModel):
    lines: list[DraftLineOut]
    explanation: str
    confidence: float
    reasoning: str
    model_used: str


draft_entry_router = APIRouter(prefix="/ai/finance/draft-entry", tags=["ai-finance"])


@draft_entry_router.post("", response_model=DraftResponse)
async def draft_entry(
    body: DraftPayload,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    request: Request,
) -> DraftResponse:
    """Draft a multi-line journal entry for a transaction description."""
    req = SuggestRequest(
        description=body.description,
        accounts=[AccountOption(code=a.code, name=a.name) for a in body.accounts],
    )
    result = await llm_draft_entry(request.app.state.llm_router, req)
    if result is None:
        return DraftResponse(lines=[], explanation="", confidence=0.0, reasoning="", model_used="")
    return DraftResponse(
        lines=[
            DraftLineOut(
                account_code=line.account_code,
                account_name=line.account_name,
                amount=line.amount,
                side=line.side,
                description=line.description,
            )
            for line in result.lines
        ],
        explanation=result.explanation,
        confidence=result.confidence,
        reasoning=result.reasoning,
        model_used=result.model_used,
    )


class NarratePayload(BaseModel):
    anomaly_type: str
    description: str
    severity: str


class NarrateResponse(BaseModel):
    narration: str
    model_used: str


anomaly_narrate_router = APIRouter(prefix="/ai/finance/anomalies/narrate", tags=["ai-finance"])


@anomaly_narrate_router.post("", response_model=NarrateResponse)
async def narrate_anomaly(
    body: NarratePayload,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    request: Request,
) -> NarrateResponse:
    """Explain a finance anomaly in plain English, citing the triggering figures."""
    result = await llm_narrate_anomaly(
        request.app.state.llm_router,
        anomaly_type=body.anomaly_type,
        description=body.description,
        severity=body.severity,
    )
    if result is None:
        return NarrateResponse(narration="", model_used="")
    return NarrateResponse(narration=result["narration"], model_used=result["model_used"])


class ReminderPayload(BaseModel):
    customer_name: str | None = None
    invoice_number: str
    amount: float
    days_overdue: int
    tone: str


class ReminderResponse(BaseModel):
    subject: str
    body: str
    tone: str
    model_used: str


reminders_router = APIRouter(prefix="/ai/finance/reminders/draft", tags=["ai-finance"])


@reminders_router.post("", response_model=ReminderResponse)
async def draft_reminder(
    body: ReminderPayload,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    request: Request,
) -> ReminderResponse:
    """Draft a payment reminder email for an overdue invoice."""
    result = await llm_draft_reminder(
        request.app.state.llm_router,
        customer_name=body.customer_name,
        invoice_number=body.invoice_number,
        amount=body.amount,
        days_overdue=body.days_overdue,
        tone=body.tone,
    )
    if result is None:
        return ReminderResponse(subject="", body="", tone=body.tone, model_used="")
    return ReminderResponse(
        subject=result["subject"],
        body=result["body"],
        tone=result["tone"],
        model_used=result["model_used"],
    )
