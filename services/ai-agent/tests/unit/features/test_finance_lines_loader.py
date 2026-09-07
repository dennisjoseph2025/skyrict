"""Unit tests for the finance line-hist loader (SKY-67 C1).

Paginates core's invoice lines through an in-memory httpx transport (no
network): accounts mapping, aggregation by description, envelope parsing, and
the typed AiUnavailableError mapping for transport/schema failures.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest

from ai_agent.core.exceptions import AiUnavailableError
from ai_agent.features.finance_lines.loader import FinanceLineLoader

if TYPE_CHECKING:
    from collections.abc import Callable

BASE_URL = "http://core.test"
PAGES: dict[int, list[dict[str, object]]] = {}
ACCOUNT_ID = uuid.uuid4()


def _invoice_row() -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "invoice_number": "INV-0001",
        "customer_name": "Acme Corp",
        "total": "1000.00",
        "lines": [
            {"id": str(uuid.uuid4()), "description": "Professional services", "account_id": str(ACCOUNT_ID)},
            {"id": str(uuid.uuid4()), "description": "Professional services", "account_id": str(ACCOUNT_ID)},
            {"id": str(uuid.uuid4()), "description": "Travel reimbursement", "account_id": str(uuid.uuid4())},
            {"id": str(uuid.uuid4()), "description": "  ", "account_id": str(ACCOUNT_ID)},
        ],
    }


@pytest.fixture(autouse=True)
def _reset_pages() -> None:
    PAGES.clear()


def _handler_factory() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/accounts"):
            body = {
                "success": True,
                "data": [{"id": str(ACCOUNT_ID), "code": "4000", "name": "Service Revenue"}],
            }
            return httpx.Response(200, json=body)
        offset = int(request.url.params.get("offset", 0))
        page_index = offset // 100 + 1
        rows = PAGES.get(page_index, [])
        return httpx.Response(200, json={"success": True, "data": rows})

    return handler


def _loader() -> FinanceLineLoader:
    loader = FinanceLineLoader(
        base_url=BASE_URL,
        bearer_token="ingest-secret",
        tenant_slug="acme",
    )
    transport = httpx.MockTransport(_handler_factory())
    loader._create_client = lambda: httpx.AsyncClient(transport=transport, timeout=1.0)
    return loader


class TestFinanceLineLoader:
    @pytest.mark.anyio
    async def test_aggregates_lines_by_description_with_canonical_account(self) -> None:
        PAGES[1] = [_invoice_row()]

        snapshots = await _loader().load_all()

        assert {row.description for row in snapshots} == {
            "Professional services",
            "Travel reimbursement",
        }
        services = next(
            row for row in snapshots if row.description == "Professional services"
        )
        assert services.account_id == ACCOUNT_ID
        assert services.account_code == "4000"
        assert services.account_name == "Service Revenue"
        assert services.times_used == 2
        travel = next(
            row for row in snapshots if row.description == "Travel reimbursement"
        )
        assert travel.times_used == 1

    @pytest.mark.anyio
    async def test_empty_page_stops_early(self) -> None:
        PAGES[1] = [_invoice_row()]

        snapshots = await _loader().load_all()
        assert len(snapshots) == 2

    @pytest.mark.anyio
    async def test_no_lines_is_empty(self) -> None:
        PAGES[1] = [
            {"id": str(uuid.uuid4()), "invoice_number": "INV-9", "lines": []}
        ]

        assert await _loader().load_all() == []

    @pytest.mark.anyio
    async def test_transport_failure_is_typed_503(self) -> None:
        def failing(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        loader = FinanceLineLoader(base_url=BASE_URL, bearer_token="x", tenant_slug="acme")
        loader._create_client = lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(failing), timeout=1.0
        )

        with pytest.raises(AiUnavailableError):
            await loader.load_all()

    @pytest.mark.anyio
    async def test_unusable_envelope_is_typed_503(self) -> None:
        def bad(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=json.dumps({"success": True}).encode())

        loader = FinanceLineLoader(base_url=BASE_URL, bearer_token="x", tenant_slug="acme")
        loader._create_client = lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(bad), timeout=1.0
        )

        with pytest.raises(AiUnavailableError):
            await loader.load_all()
