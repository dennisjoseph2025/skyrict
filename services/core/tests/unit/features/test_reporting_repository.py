"""ReportRepository unit tests - fake async session, no database (RPT-DATA-001)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from core.features.reporting.repository import ReportRepository


class FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class FakeResult:
    def __init__(
        self,
        rows: list[Any],
        *,
        rowcount: int | None = None,
    ) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._rows)

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Record executed statements and serve canned results in FIFO order."""

    def __init__(
        self,
        results: list[list[Any]] | None = None,
        *,
        rowcount: int | None = None,
    ) -> None:
        self.queue = list(results or [])
        self.rowcount = rowcount
        self.statements: list[Any] = []
        self.added: list[Any] = []
        self.flushed = 0

    async def execute(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        rows = self.queue.pop(0) if self.queue else []
        return FakeResult(rows, rowcount=self.rowcount)

    def add(self, model: Any) -> None:
        self.added.append(model)

    async def flush(self) -> None:
        self.flushed += 1


def _definition(tenant_id: uuid.UUID, slug: str, is_active: bool = True) -> Any:
    model = type("Definition", (), {})()
    model.tenant_id = tenant_id
    model.slug = slug
    model.is_active = is_active
    return model


def _snapshot(
    tenant_id: uuid.UUID,
    definition_id: uuid.UUID,
    period: date,
    payload: list[dict[str, Any]],
) -> Any:
    model = type("Snapshot", (), {})()
    model.tenant_id = tenant_id
    model.definition_id = definition_id
    model.period = period
    model.payload = payload
    return model


class TestListDefinitions:
    @pytest.mark.asyncio
    async def test_returns_definitions_and_filters_tenant(self) -> None:
        tenant_id = uuid.uuid4()
        rows = [_definition(tenant_id, "pnl_by_period"), _definition(tenant_id, "ar_aging")]
        session = FakeSession(results=[rows])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.list_active_definitions(tenant_id=tenant_id)

        assert result == rows
        assert len(session.statements) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_found(self) -> None:
        session = FakeSession(results=[[]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.list_active_definitions(tenant_id=uuid.uuid4())

        assert result == []


class TestGetDefinition:
    @pytest.mark.asyncio
    async def test_returns_row_when_found(self) -> None:
        tenant_id = uuid.uuid4()
        row = _definition(tenant_id, "pnl_by_period")
        session = FakeSession(results=[[row]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.get_definition(tenant_id=tenant_id, slug="pnl_by_period")

        assert result is row

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        session = FakeSession(results=[[]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.get_definition(tenant_id=uuid.uuid4(), slug="missing")

        assert result is None


class TestSnapshotUpsert:
    @pytest.mark.asyncio
    async def test_inserts_new_snapshot_when_missing(self) -> None:
        tenant_id = uuid.uuid4()
        definition_id = uuid.uuid4()
        period = date(2026, 9, 1)
        payload = [{"account": "revenue", "total": "123.45"}]
        session = FakeSession(results=[[]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.upsert_snapshot(
            tenant_id=tenant_id,
            definition_id=definition_id,
            period=period,
            payload=payload,
        )

        assert result in session.added
        assert result.tenant_id == tenant_id
        assert result.definition_id == definition_id
        assert result.period == period
        assert result.payload == payload
        assert session.flushed == 1

    @pytest.mark.asyncio
    async def test_replaces_payload_when_snapshot_exists(self) -> None:
        tenant_id = uuid.uuid4()
        definition_id = uuid.uuid4()
        period = date(2026, 9, 1)
        existing = _snapshot(tenant_id, definition_id, period, [{"old": True}])
        session = FakeSession(results=[[existing]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        new_payload = [{"account": "expense", "total": "-9.00"}]
        result = await repo.upsert_snapshot(
            tenant_id=tenant_id,
            definition_id=definition_id,
            period=period,
            payload=new_payload,
        )

        assert result is existing
        assert existing.payload == new_payload
        assert session.added == []
        assert session.flushed == 1


class TestGetSnapshot:
    @pytest.mark.asyncio
    async def test_returns_row_when_found(self) -> None:
        tenant_id = uuid.uuid4()
        definition_id = uuid.uuid4()
        period = date(2026, 9, 1)
        row = _snapshot(tenant_id, definition_id, period, [{"x": 1}])
        session = FakeSession(results=[[row]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.get_snapshot(
            tenant_id=tenant_id, definition_id=definition_id, period=period
        )

        assert result is row

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        session = FakeSession(results=[[]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.get_snapshot(
            tenant_id=uuid.uuid4(), definition_id=uuid.uuid4(), period=date(2026, 9, 1)
        )

        assert result is None


class FakeRow:
    """Minimal Row double exposing ``_mapping`` like SQLAlchemy's Row."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping


class FakeRunResult:
    """Minimal CursorResult double exposing ``keys`` and row iteration."""

    def __init__(self, columns: list[str], rows: list[FakeRow]) -> None:
        self._columns = columns
        self._rows = rows

    def keys(self) -> list[str]:
        return self._columns

    def __iter__(self):
        return iter(self._rows)


class FakeRunSession:
    """Fake session for run_query: first execute is set_config, second is the query."""

    def __init__(self, columns: list[str], rows: list[dict[str, Any]]) -> None:
        self._columns = columns
        self._rows = [FakeRow(row) for row in rows]
        self.executions: list[tuple[Any, dict[str, Any] | None]] = []
        self.exec_count = 0

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> Any:
        self.executions.append((stmt, params))
        self.exec_count += 1
        if self.exec_count == 1:
            return None
        return FakeRunResult(self._columns, self._rows)


class TestRunQuery:
    @pytest.mark.asyncio
    async def test_sets_statement_timeout_then_runs_query_with_binds(self) -> None:
        session = FakeRunSession(["bucket"], [{"bucket": "current"}])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        columns, rows = await repo.run_query(
            sql="SELECT :bucket AS bucket",
            binds={"bucket": "current"},
            statement_timeout_seconds=30,
        )

        assert session.exec_count == 2
        timeout_stmt, timeout_params = session.executions[0]
        assert str(timeout_stmt).startswith("SELECT set_config('statement_timeout'")
        assert timeout_params == {"value": "30s"}
        query_stmt, query_params = session.executions[1]
        assert "SELECT :bucket" in str(query_stmt)
        assert query_params == {"bucket": "current"}
        assert columns == ["bucket"]
        assert rows == [{"bucket": "current"}]

    @pytest.mark.asyncio
    async def test_coerces_values_to_json_safe_scalars(self) -> None:
        tenant_id = uuid.uuid4()
        session = FakeRunSession(
            ["amount", "as_of", "at", "tenant", "flag", "empty"],
            [
                {
                    "amount": Decimal("150.50"),
                    "as_of": date(2026, 9, 30),
                    "at": datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC),
                    "tenant": tenant_id,
                    "flag": True,
                    "empty": None,
                }
            ],
        )
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        _, rows = await repo.run_query(sql="SELECT 1", binds={})

        assert rows[0]["amount"] == "150.50"
        assert rows[0]["as_of"] == "2026-09-30"
        assert rows[0]["at"] == "2026-09-05T09:00:00+00:00"
        assert rows[0]["tenant"] == str(tenant_id)
        assert rows[0]["flag"] is True
        assert rows[0]["empty"] is None


class TestListSnapshots:
    @pytest.mark.asyncio
    async def test_returns_snapshots_for_definition(self) -> None:
        tenant_id = uuid.uuid4()
        definition_id = uuid.uuid4()
        row = _snapshot(tenant_id, definition_id, date(2026, 9, 1), [])
        session = FakeSession(results=[[row]])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.list_snapshots(
            tenant_id=tenant_id, definition_id=definition_id, limit=5
        )

        assert result == [row]
        assert "ORDER BY" in str(session.statements[0])


class TestListDefinitionIds:
    @pytest.mark.asyncio
    async def test_returns_all_definition_ids_for_tenant(self) -> None:
        tenant_id = uuid.uuid4()
        definition_ids = [uuid.uuid4(), uuid.uuid4()]
        session = FakeSession(results=[definition_ids])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.list_definition_ids(tenant_id=tenant_id)

        assert result == definition_ids


class TestListAllDefinitionPairs:
    @pytest.mark.asyncio
    async def test_returns_all_tenant_definition_pairs(self) -> None:
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        pairs = [(tenant_a, uuid.uuid4()), (tenant_b, uuid.uuid4())]
        session = FakeSession(results=[pairs])
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        result = await repo.list_all_definition_pairs()

        assert result == pairs


class TestPruneSnapshots:
    @pytest.mark.asyncio
    async def test_deletes_beyond_newest_keep_and_returns_count(self) -> None:
        session = FakeSession(results=[[]], rowcount=4)
        repo = ReportRepository(session=session)  # type: ignore[arg-type]

        deleted = await repo.prune_snapshots(
            tenant_id=uuid.uuid4(),
            definition_id=uuid.uuid4(),
            keep_n=3,
        )

        assert deleted == 4
        assert len(session.statements) == 1
        assert str(session.statements[0]).strip().upper().startswith("DELETE")
