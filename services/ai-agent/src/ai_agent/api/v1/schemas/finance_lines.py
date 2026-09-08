"""API schemas for the finance line-item suggestion endpoint (SKY-67 C1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinanceLineSuggestRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=512)


class FinanceLineSuggestionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str
    account_code: str
    account_name: str
    times_used: int = Field(..., ge=1)
    score: float = Field(..., ge=0, le=1)


class FinanceLineSuggestResponse(BaseModel):
    data: list[FinanceLineSuggestionItem]
    degraded: bool
    model_used: str | None = None
    latency_ms: int = Field(..., ge=0)
