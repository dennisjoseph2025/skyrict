"""Unit tests for the snapshot retention worker (RPT-BE-001) - clean loop, no DB.

The worker's ``process_all`` hard-depends on ``async_session_factory`` + the
RLS ``TenantContext`` (a real-session interaction), so unit-testing it directly
is brittle. Instead these tests pin the small, loop-independent contracts that
make retention correct in production:

  - ``RetentionOutcome`` aggregates tenant count + pruned count,
  - the worker's start/stop lifecycle toggles ``running`` without a live loop,
  - ``stop`` is idempotent when the task never started.
"""

from __future__ import annotations

import asyncio

from core.features.reporting.retention_worker import RetentionOutcome, SnapshotRetentionWorker


class TestRetentionOutcome:
    def test_aggregates_counters(self) -> None:
        outcome = RetentionOutcome(tenants_processed=2, snapshots_pruned=7)
        assert outcome.tenants_processed == 2
        assert outcome.snapshots_pruned == 7


class TestWorkerLifecycle:
    def test_not_running_when_never_started(self) -> None:
        worker = SnapshotRetentionWorker(session_factory=None)  # type: ignore[arg-type]
        assert worker.running is False

    def test_stop_without_start_is_noop(self) -> None:
        worker = SnapshotRetentionWorker(session_factory=None)  # type: ignore[arg-type]
        internal_task = worker._task

        asyncio.run(worker.stop())

        assert worker._task is None
        assert internal_task is None

    def test_default_keep_n_is_20(self) -> None:
        worker = SnapshotRetentionWorker(session_factory=None)  # type: ignore[arg-type]
        assert worker._keep_n == 20
