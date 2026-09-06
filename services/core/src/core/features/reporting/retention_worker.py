"""In-process report snapshot retention worker (RPT-BE-001).

A single background asyncio task walks every tenant's report definitions once
per poll and prunes each definition's ``erp_report_snapshots`` rows beyond the
newest ``keep_n`` (default ``REPORTING_RETENTION_LIMIT``, 20). The per-
definition limit is the ticket's contract: "keeping N per definition".

The worker sets the request-scoped ``TenantContext`` per tenant so RLS binds
each DELETE to that tenant's rows (the owner role bypasses RLS, but the context
keeps the worker's semantic identical to request-path behaviour). Each tenant's
prune runs in its own session/transaction so a failure for one tenant never
rolls back another's.

The worker is owned by the core app lifespan (``api/lifespan.py``) and guarded
by ``REPORTING_RETENTION_ENABLED`` + non-test environment; ``core retention
run`` is the manual/CI equivalent that drives ``process_all`` without the
background loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.core.tenant_context import TenantContext
from core.features.reporting.repository import ReportRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionOutcome:
    """Result of one retention pass, for the log line and the CLI."""

    tenants_processed: int
    snapshots_pruned: int


class SnapshotRetentionWorker:
    """Background loop that prunes report snapshots past the per-definition cap."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        poll_seconds: float = 3600.0,
        keep_n: int = 20,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._keep_n = keep_n
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._worker_id = f"core-{socket.gethostname()}-{os.getpid()}"

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Begin the background polling loop (idempotent)."""
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run_loop(),
            name="reporting-retention-worker",
        )

    async def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the loop to stop and await it (cancels on timeout)."""
        self._stop.set()
        task, self._task = self._task, None
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run_loop(self) -> None:
        logger.info(
            "reporting.retention.worker.started",
            extra={"worker_id": self._worker_id, "keep_n": self._keep_n},
        )
        try:
            while not self._stop.is_set():
                try:
                    outcome = await self.process_all()
                    if outcome.snapshots_pruned:
                        logger.info(
                            "reporting.retention.worker.pass",
                            extra={"worker_id": self._worker_id, **outcome.__dict__},
                        )
                except Exception:
                    logger.exception(
                        "reporting.retention.worker.pass_failed",
                        extra={"worker_id": self._worker_id},
                    )
                await asyncio.sleep(self._poll_seconds)
        finally:
            logger.info(
                "reporting.retention.worker.stopped",
                extra={"worker_id": self._worker_id},
            )

    async def process_all(self) -> RetentionOutcome:
        """Run one full retention pass across every tenant's definitions."""
        async with self._session_factory() as session:
            pairs = await ReportRepository(session).list_all_definition_pairs()

        pruned_total = 0
        for tenant_id, _ in pairs:
            tid = str(tenant_id)
            async with self._session_factory() as session:
                TenantContext.set(tid)
                try:
                    from core.api.deps import make_report_service

                    service = make_report_service(session)
                    pruned = await service.prune_snapshots(
                        tenant_id=tenant_id,
                        keep_n=self._keep_n,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    TenantContext.reset()
            pruned_total += pruned

        tenants_processed = len({str(tenant_id) for tenant_id, _ in pairs})
        return RetentionOutcome(
            tenants_processed=tenants_processed,
            snapshots_pruned=pruned_total,
        )


__all__ = ["RetentionOutcome", "SnapshotRetentionWorker"]
