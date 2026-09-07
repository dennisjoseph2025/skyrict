"""Supplier-risk reindex runner - composition root for the ``supplier-risk
reindex`` CLI (SKY-86 / INV-AI-004).

Wires the pieces the feature layer may not import itself (repositories,
sessions, settings) around the pure grading pipeline, mirroring
``ai_agent/inventory_reindex.py``. Lives at the package root so it can compose
``ai_agent.db`` + ``ai_agent.features`` without violating the import-linter
layering contracts.

RLS note: the session's ``after_begin`` hook sets ``app.current_tenant_id``
from ``TenantContext``; without it every upsert would silently match zero rows
under the tenant policy. The runner therefore pins the resolved tenant id
BEFORE any write runs.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import typer

from ai_agent.core.config import settings
from ai_agent.core.exceptions import StartupError
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.session import async_session_factory
from ai_agent.db.supplier_risk_repository import SupplierRiskRepository
from ai_agent.db.tenant_resolver import resolve_tenant_id
from ai_agent.features.supplier_risk.loader import SupplierSnapshotLoader
from ai_agent.features.supplier_risk.service import SupplierRiskService

if TYPE_CHECKING:
    import uuid

    from ai_agent.domain.supplier_risk import SupplierRiskAssessment


async def run_supplier_risk_reindex(*, tenant: str) -> None:
    """Rebuild one tenant's supplier risk grades; prints a summary."""
    if not settings.INGEST_TOKEN:
        raise StartupError(
            "AI_INGEST_TOKEN is required to pull the supplier catalog from the core service"
        )

    async with async_session_factory() as session:
        tenant_id = await resolve_tenant_id(session, tenant)
        # Pin the security context BEFORE the first write so the session's
        # RLS hook constrains every upsert to this tenant.
        TenantContext.set(str(tenant_id))
        TenantContext.set_tenant_slug(tenant)

        loader = SupplierSnapshotLoader(
            base_url=settings.INVENTORY_SERVICE_URL,
            bearer_token=settings.INGEST_TOKEN,
            tenant_slug=tenant,
            timeout_seconds=settings.INVENTORY_SERVICE_TIMEOUT_SECONDS,
        )
        snapshots = await loader.load_all()
        if not snapshots:
            typer.echo(f"No suppliers to grade for tenant {tenant}.")
            return

        service = SupplierRiskService()
        grades: list[tuple[uuid.UUID, SupplierRiskAssessment]] = service.grade_all(
            snapshots, as_of=date.today(), tenant_id=tenant_id
        )

        repository = SupplierRiskRepository(session)
        for tid, grade in grades:
            await repository.upsert(tenant_id=tid, grade=grade)
        await session.commit()

    bands = _band_counts(grades)
    typer.echo(
        f"Reindexed supplier risk for tenant {tenant}: {len(grades)} grade(s) - "
        f"low={bands['low']} medium={bands['medium']} high={bands['high']}"
    )


def _band_counts(
    grades: list[tuple[uuid.UUID, SupplierRiskAssessment]],
) -> dict[str, int]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for _, grade in grades:
        counts[grade.risk_band] = counts.get(grade.risk_band, 0) + 1
    return counts
