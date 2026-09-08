"""Unit tests for the supplier-risk slice (SKY-86 / INV-AI-004).

Covers the deterministic scorer (dimension lift, weights, bands, confidence,
recency, missing-performance), the service wrapper, and the catalog loader
(two-endpoint pagination via in-memory httpx transport, typed 503 mapping).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.domain.supplier_risk import (
    SupplierPerformanceFacts,
    SupplierRiskAssessment,
)
from ai_agent.features.supplier_risk.loader import (
    SupplierSnapshot,
    SupplierSnapshotLoader,
)
from ai_agent.features.supplier_risk.scorer import assess_supplier_risk
from ai_agent.features.supplier_risk.service import SupplierRiskService

if TYPE_CHECKING:
    from collections.abc import Callable

BASE_URL = "http://core.test"
AS_OF = date(2026, 9, 7)

SUPPLIER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _facts(
    *,
    on_time: str = "98",
    defect: str = "0.8",
    price: str = "95",
    resp: str = "1.5",
    end: date = date(2026, 8, 23),
) -> SupplierPerformanceFacts:
    return SupplierPerformanceFacts(
        supplier_id=SUPPLIER_ID,
        period_start=end - timedelta(days=30),
        period_end=end,
        on_time_delivery_pct=Decimal(on_time),
        defect_rate_pct=Decimal(defect),
        price_stability_index=Decimal(price),
        responsiveness_days=Decimal(resp),
    )


class TestScorerBands:
    def test_excellent_supplier_grades_low(self) -> None:
        grade = assess_supplier_risk(
            [_facts(on_time="98", defect="0.8", price="95", resp="1.5")],
            lead_time_days=5,
            as_of=AS_OF,
        )
        assert grade is not None
        assert grade.risk_band == "low"
        assert grade.score == Decimal("0.263")

    def test_reliable_supplier_grades_low(self) -> None:
        # Arabian Gulf profile: 96% on-time, 1.5% defect, stability 90,
        # 2-day turnaround on a 7-day lead.
        grade = assess_supplier_risk(
            [_facts(on_time="96", defect="1.5", price="90", resp="2")],
            lead_time_days=7,
            as_of=AS_OF,
        )
        assert grade is not None
        assert grade.risk_band == "low"
        assert grade.score == Decimal("0.313")

    def test_risky_supplier_grades_high(self) -> None:
        # Al-Fahad profile (two periods averaged): ~51% on-time, ~10% defect,
        # ~54% stability, ~10-day turnaround on a 14-day lead.
        grade = assess_supplier_risk(
            [
                _facts(on_time="55", defect="9", price="58", resp="9", end=date(2026, 7, 24)),
                _facts(on_time="48", defect="11", price="51", resp="11", end=date(2026, 8, 23)),
            ],
            lead_time_days=14,
            as_of=AS_OF,
        )
        assert grade is not None
        assert grade.risk_band == "high"
        assert grade.score == Decimal("0.690")

    def test_worst_supplier_grades_high(self) -> None:
        grade = assess_supplier_risk(
            [
                _facts(on_time="40", defect="14", price="40", resp="14", end=date(2026, 7, 24)),
                _facts(on_time="35", defect="16", price="36", resp="15", end=date(2026, 8, 23)),
            ],
            lead_time_days=21,
            as_of=AS_OF,
        )
        assert grade is not None
        assert grade.risk_band == "high"
        assert grade.score == Decimal("0.759")


class TestScorerEdgeCases:
    def test_no_performance_returns_none(self) -> None:
        assert assess_supplier_risk([], lead_time_days=7, as_of=AS_OF) is None

    def test_reason_exposes_dimensions_for_tooltip(self) -> None:
        grade = assess_supplier_risk(
            [_facts(on_time="96", defect="1.5", price="90", resp="2")],
            lead_time_days=7,
            as_of=AS_OF,
        )
        assert grade is not None
        reason = grade.reason.lower()
        assert reason.startswith("low risk")
        assert "on-time delivery" in reason
        assert "defect rate" in reason
        assert "price stability" in reason
        assert "of 7d lead time" in reason

    def test_confidence_grows_with_periods(self) -> None:
        one = assess_supplier_risk([_facts(end=date(2026, 8, 23))], lead_time_days=5, as_of=AS_OF)
        three = assess_supplier_risk(
            [
                _facts(end=date(2026, 6, 23)),
                _facts(end=date(2026, 7, 23)),
                _facts(end=date(2026, 8, 23)),
            ],
            lead_time_days=5,
            as_of=AS_OF,
        )
        assert one is not None and three is not None
        assert three.confidence > one.confidence

    def test_stale_facts_decay_confidence(self) -> None:
        fresh = assess_supplier_risk([_facts(end=date(2026, 9, 1))], lead_time_days=5, as_of=AS_OF)
        stale = assess_supplier_risk([_facts(end=date(2026, 1, 1))], lead_time_days=5, as_of=AS_OF)
        assert fresh is not None and stale is not None
        assert fresh.confidence > stale.confidence


class TestSupplierRiskService:
    def test_grade_all_returns_tenant_grade_pairs(self) -> None:
        snapshot = SupplierSnapshot(
            supplier_id=SUPPLIER_ID,
            name="Al-Fahad Logistics Supplies",
            lead_time_days=14,
            performance=[
                _facts(on_time="55", defect="9", price="58", resp="9", end=date(2026, 7, 24)),
                _facts(on_time="48", defect="11", price="51", resp="11", end=date(2026, 8, 23)),
            ],
        )
        service = SupplierRiskService()
        pairs = service.grade_all([snapshot], as_of=AS_OF, tenant_id=TENANT_ID)

        assert len(pairs) == 1
        tenant_id, grade = pairs[0]
        assert tenant_id == TENANT_ID
        assert isinstance(grade, SupplierRiskAssessment)
        assert grade.supplier_id == SUPPLIER_ID

    def test_snapshot_without_facts_is_skipped(self) -> None:
        snapshot = SupplierSnapshot(
            supplier_id=SUPPLIER_ID,
            name="Fresh Vendor",
            lead_time_days=7,
            performance=[],
        )
        service = SupplierRiskService()
        pairs = service.grade_all([snapshot], as_of=AS_OF, tenant_id=TENANT_ID)
        assert pairs == []


# ---------------------------------------------------------------------------
# Loader tests (in-memory httpx transport, no network).
# ---------------------------------------------------------------------------

SUPPLIERS_PAGES: dict[int, list[dict[str, object]]] = {}
PERFORMANCE: dict[str, list[dict[str, object]]] = {}


@pytest.fixture(autouse=True)
def _reset_loader_state() -> None:
    SUPPLIERS_PAGES.clear()
    PERFORMANCE.clear()


def _supplier_row(sid: uuid.UUID, *, name: str = "Vendor") -> dict[str, object]:
    return {
        "id": str(sid),
        "name": name,
        "contact_name": "Contact",
        "contact_email": "vendor@example.sa",
        "lead_time_days": 14,
    }


def _perf_row() -> dict[str, object]:
    return {
        "period_start": "2026-07-24",
        "period_end": "2026-08-23",
        "on_time_delivery_pct": "48",
        "defect_rate_pct": "11",
        "price_stability_index": "51",
        "responsiveness_days": "11",
    }


def _loader_handler() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.rstrip("/").split("/")
        if parts[-1] == "performance":
            sid = parts[-2]
            body = {"success": True, "data": PERFORMANCE.get(sid, [])}
            return httpx.Response(200, json=body)
        page = int(request.url.params.get("page", 1))
        rows = SUPPLIERS_PAGES.get(page, [])
        body = {"success": True, "data": rows, "meta": {"total_pages": len(SUPPLIERS_PAGES)}}
        return httpx.Response(200, json=body)

    return handler


def _loader() -> SupplierSnapshotLoader:
    loader = SupplierSnapshotLoader(
        base_url=BASE_URL,
        bearer_token="ingest-secret",
        tenant_slug="acme",
    )
    transport = httpx.MockTransport(_loader_handler())
    loader._create_client = lambda: httpx.AsyncClient(transport=transport, timeout=1.0)
    return loader


class TestSupplierSnapshotLoader:
    @pytest.mark.anyio
    async def test_load_all_paginates_and_pulls_performance(self) -> None:
        sid = uuid.uuid4()
        SUPPLIERS_PAGES[1] = [_supplier_row(sid, name="Al-Fahad Logistics Supplies")]
        PERFORMANCE[str(sid)] = [_perf_row()]

        snapshots = await _loader().load_all()

        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.name == "Al-Fahad Logistics Supplies"
        assert snap.lead_time_days == 14
        assert len(snap.performance) == 1
        assert snap.performance[0].defect_rate_pct == Decimal("11")

    @pytest.mark.anyio
    async def test_single_page_stops_early(self) -> None:
        sid = uuid.uuid4()
        SUPPLIERS_PAGES[1] = [_supplier_row(sid)]

        snapshots = await _loader().load_all()
        assert len(snapshots) == 1

    @pytest.mark.anyio
    async def test_transport_failure_is_typed_503(self) -> None:
        def failing(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        loader = SupplierSnapshotLoader(base_url=BASE_URL, bearer_token="x", tenant_slug="acme")
        loader._create_client = lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(failing), timeout=1.0
        )

        with pytest.raises(AiUnavailableError):
            await loader.load_all()

    @pytest.mark.anyio
    async def test_unusable_envelope_is_typed_503(self) -> None:
        def bad(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=json.dumps({"success": True}).encode())

        loader = SupplierSnapshotLoader(base_url=BASE_URL, bearer_token="x", tenant_slug="acme")
        loader._create_client = lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(bad), timeout=1.0
        )

        with pytest.raises(AiUnavailableError):
            await loader.load_all()

    @pytest.mark.anyio
    async def test_rejects_bad_base_url(self) -> None:
        with pytest.raises(ValueError):
            SupplierSnapshotLoader(base_url="ftp://bad", bearer_token="x", tenant_slug="acme")
