"""Pydantic schemas for the reports API (RPT-BE-001)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportDefinitionRead(BaseModel):
    """Metadata for one report definition (the UI's build-from-metadata contract)."""

    id: uuid.UUID
    slug: str
    title: str
    module: str
    description: str | None = None
    params: list[str] = Field(default_factory=list)
    permission_key: str
    version: int
    updated_at: datetime


class ReportRunRequest(BaseModel):
    """Payload for POST /api/v1/reports/{slug}/run - raw user params."""

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Values for the definition's declared params (dates are ISO YYYY-MM-DD)",
    )


class ReportRunResult(BaseModel):
    """Result of one parametrized report run."""

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = Field(
        default=False,
        description="True when the UI cap truncated rows (export streams the full set)",
    )
    period: date
    snapshot_id: uuid.UUID
    generated_at: datetime


class ReportSnapshotRead(BaseModel):
    """One stored snapshot for a report definition."""

    id: uuid.UUID
    definition_id: uuid.UUID
    period: date
    generated_at: datetime
