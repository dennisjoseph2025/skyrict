"""Unit tests for ReportService.run_report (RPT-BE-001) - fake repo, no database."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

from core.features.reporting.service import ReportService
from skyrict_common.exceptions import NotFoundError, ValidationError


class FakeRepo:
    """In-memory ReportRepository double recording calls."""

    def __init__(self) -> None:
        self.definitions: dict[str, Any] = {}
        self.snapshots: list[Any] = []
        self.run_calls: list[tuple[str, dict[str, Any]]] = []

    async def list_active_definitions(self, *, tenant_id: uuid.UUID) -> list[Any]:
        return [d for d in self.definitions.values() if d.tenant_id == tenant_id and d.is_active]

    async def get_definition(self, *, tenant_id: uuid.UUID, slug: str) -> Any | None:
        definition = self.definitions.get(slug)
        if definition is None:
            return None
        return definition if definition.tenant_id == tenant_id and definition.is_active else None

    async def run_query(
        self,
        *,
        sql: str,
        binds: dict[str, Any],
        statement_timeout_seconds: int = 30,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        self.run_calls.append((sql, binds))
        return (["bucket", "total"], [{"bucket": "current", "total": "150.00"}])

    async def upsert_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        period: date,
        payload: list[dict[str, Any]],
    ) -> Any:
        snapshot = type(
            "Snapshot",
            (),
            {
                "id": uuid.uuid4(),
                "generated_at": datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC),
            },
        )()
        self.snapshots.append((tenant_id, definition_id, period, payload))
        return snapshot

    async def list_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        limit: int,
    ) -> list[Any]:
        return self.snapshots[-limit:]

    async def list_definition_ids(self, *, tenant_id: uuid.UUID) -> list[Any]:
        return [
            definition.id
            for definition in self.definitions.values()
            if definition.tenant_id == tenant_id
        ]

    async def prune_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        keep_n: int,
    ) -> int:
        return 3


def _definition(*, tenant_id: uuid.UUID, slug: str, params: tuple[str, ...]) -> Any:
    definition = type("Definition", (), {})()
    definition.tenant_id = tenant_id
    definition.id = uuid.uuid4()
    definition.slug = slug
    definition.sql = "SELECT 1"
    definition.params = list(params)
    definition.params_tuple = params
    definition.is_active = True
    return definition


def _make_service(definitions: dict[str, Any]) -> ReportService:
    repo = FakeRepo()
    repo.definitions = definitions
    return ReportService(repository=repo)  # type: ignore[arg-type]


class TestRunReport:
    @pytest.mark.asyncio
    async def test_run_returns_columns_rows_and_snapshot(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(
            tenant_id=tenant_id, slug="ar_aging", params=("tenant_id", "as_of_date")
        )
        service = _make_service({definition.slug: definition})

        result = await service.run_report(
            tenant_id=tenant_id,
            slug="ar_aging",
            raw_params={"as_of_date": "2026-09-30"},
        )

        assert result["columns"] == ["bucket", "total"]
        assert result["rows"] == [{"bucket": "current", "total": "150.00"}]
        assert result["truncated"] is False
        assert result["period"] == date(2026, 9, 30)

    @pytest.mark.asyncio
    async def test_run_404_for_unknown_slug(self) -> None:
        service = _make_service({})

        with pytest.raises(NotFoundError):
            await service.run_report(
                tenant_id=uuid.uuid4(),
                slug="missing",
                raw_params={},
            )

    @pytest.mark.asyncio
    async def test_run_422_for_invalid_params(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(
            tenant_id=tenant_id, slug="ar_aging", params=("tenant_id", "as_of_date")
        )
        service = _make_service({definition.slug: definition})

        with pytest.raises(ValidationError):
            await service.run_report(
                tenant_id=tenant_id,
                slug="ar_aging",
                raw_params={"as_of_date": "2026-01-01'; DROP TABLE erp_report_snapshots; --"},
            )

    @pytest.mark.asyncio
    async def test_run_caps_rows_for_ui_path(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(tenant_id=tenant_id, slug="pnl", params=("tenant_id",))
        service = _make_service({definition.slug: definition})
        service._repo.run_query = _run_query_with_rows(15)  # type: ignore[attr-defined]

        result = await service.run_report(
            tenant_id=tenant_id,
            slug="pnl",
            raw_params={},
            result_cap=10,
        )

        assert result["truncated"] is True
        assert len(result["rows"]) == 10


def _run_query_with_rows(count: int) -> Any:
    async def run_query(**kwargs: Any) -> tuple[list[str], list[dict[str, Any]]]:
        return ["n"], [{"n": i} for i in range(count)]

    return run_query


class TestListSnapshots:
    @pytest.mark.asyncio
    async def test_returns_snapshots_for_known_definition(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(tenant_id=tenant_id, slug="ar_aging", params=("tenant_id",))
        service = _make_service({definition.slug: definition})

        result = await service.list_snapshots(tenant_id=tenant_id, slug="ar_aging", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_404_for_unknown_slug(self) -> None:
        service = _make_service({})

        with pytest.raises(NotFoundError):
            await service.list_snapshots(tenant_id=uuid.uuid4(), slug="missing", limit=5)


class TestExportReport:
    @pytest.mark.asyncio
    async def test_export_runs_full_and_writes_audit(self) -> None:
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        definition = _definition(
            tenant_id=tenant_id, slug="ar_aging", params=("tenant_id", "as_of_date")
        )
        fake_audit = FakeAudit()
        repo = FakeRepo()
        repo.definitions = {definition.slug: definition}
        service = ReportService(repository=repo, audit=fake_audit)  # type: ignore[arg-type]

        prepared = await service.export_report(
            tenant_id=tenant_id,
            user_id=user_id,
            actor_ip="203.0.113.9",
            actor_agent="pytest",
            slug="ar_aging",
            raw_params={"as_of_date": "2026-09-30"},
        )

        assert prepared["filename"] == "ar_aging-2026-09-30.csv"
        assert prepared["rows"] == 1
        assert "bucket,total" in prepared["csv"]
        assert "current,150.00" in prepared["csv"]
        assert len(fake_audit.entries) == 1
        entry = fake_audit.entries[0]
        assert entry["action"] == "report.exported"
        assert entry["target"] == "report:ar_aging"
        assert entry["tenant_id"] == tenant_id
        assert entry["user_id"] == user_id
        assert entry["ip_address"] == "203.0.113.9"
        assert entry["user_agent"] == "pytest"
        assert entry["details"]["rows"] == 1

    @pytest.mark.asyncio
    async def test_export_404_for_unknown_slug_without_audit(self) -> None:
        fake_audit = FakeAudit()
        repo = FakeRepo()
        service = ReportService(repository=repo, audit=fake_audit)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await service.export_report(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                actor_ip=None,
                actor_agent=None,
                slug="missing",
                raw_params={},
            )

        assert len(fake_audit.entries) == 0

    @pytest.mark.asyncio
    async def test_export_no_audit_service_is_optional(self) -> None:
        tenant_id = uuid.uuid4()
        definition = _definition(tenant_id=tenant_id, slug="ar_aging", params=("tenant_id",))
        service = _make_service({definition.slug: definition})

        prepared = await service.export_report(
            tenant_id=tenant_id,
            user_id=uuid.uuid4(),
            actor_ip=None,
            actor_agent=None,
            slug="ar_aging",
            raw_params={},
        )

        assert prepared["rows"] == 1
        assert prepared["csv"].startswith("bucket,total")


class FakeAudit:
    """Minimal AuditService double recording log() calls."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log(
        self,
        *,
        action: str,
        target: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> Any:
        self.entries.append(
            {
                "action": action,
                "target": target,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "details": details or {},
            }
        )
        return None


class TestPruneSnapshots:
    @pytest.mark.asyncio
    async def test_prunes_each_definition_of_the_tenant(self) -> None:
        tenant_id = uuid.uuid4()
        definition_a = _definition(tenant_id=tenant_id, slug="a", params=("tenant_id",))
        definition_b = _definition(tenant_id=tenant_id, slug="b", params=("tenant_id",))
        service = _make_service({definition_a.slug: definition_a, definition_b.slug: definition_b})

        total = await service.prune_snapshots(tenant_id=tenant_id, keep_n=3)

        assert total == 6  # 3 pruned per definition, two definitions
