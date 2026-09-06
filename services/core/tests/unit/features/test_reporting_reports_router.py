"""Unit tests for the ``/api/v1/reports`` router (RPT-BE-001)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from core.core.exceptions import (
    request_validation_error_handler,
    skyrict_error_handler,
)
from core.features.reporting import reports_router
from skyrict_common.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    SkyrictError,
    ValidationError,
)


def _app_with_mocks() -> tuple[TestClient, AsyncMock]:
    app = FastAPI()
    app.include_router(reports_router.router, prefix="/api/v1")
    app.add_exception_handler(SkyrictError, skyrict_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]

    mock_service = AsyncMock()
    tenant_id = uuid.uuid4()

    app.dependency_overrides[reports_router._get_service] = lambda: mock_service
    app.dependency_overrides[reports_router._require_reports_read] = lambda: {
        "user_id": uuid.uuid4(),
        "tenant_id": tenant_id,
    }

    return TestClient(app), mock_service


def _definition(slug: str, module: str = "finance") -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "slug": slug,
        "title": slug.replace("_", " ").title(),
        "module": module,
        "description": "a report",
        "params": ["tenant_id", "as_of_date"],
        "permission_key": "erp.reports.read",
        "version": 1,
        "updated_at": datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC),
    }


def test_list_reports_route_200() -> None:
    client, service = _app_with_mocks()
    service.list_reports.return_value = [_definition("ar_aging")]

    response = client.get("/api/v1/reports")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["slug"] == "ar_aging"


def test_list_reports_filters_by_module() -> None:
    client, service = _app_with_mocks()
    service.list_reports.return_value = [_definition("ar_aging", module="finance")]

    response = client.get("/api/v1/reports?module=finance")

    assert response.status_code == 200, response.text
    service.list_reports.assert_awaited_once()
    assert service.list_reports.await_args.kwargs["module"] == "finance"


def test_get_report_metadata_route_200() -> None:
    client, service = _app_with_mocks()
    service.get_report.return_value = _definition("ar_aging")

    response = client.get("/api/v1/reports/ar_aging")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["slug"] == "ar_aging"


def test_get_report_metadata_route_404() -> None:
    client, service = _app_with_mocks()
    service.get_report.side_effect = NotFoundError("Report 'nope' was not found")

    response = client.get("/api/v1/reports/nope")

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["type"].endswith("/not-found")


def test_run_report_route_200() -> None:
    client, service = _app_with_mocks()
    service.run_report.return_value = {
        "columns": ["bucket", "total"],
        "rows": [{"bucket": "current", "total": "150.00"}],
        "truncated": False,
        "period": date(2026, 9, 30),
        "snapshot_id": uuid.uuid4(),
        "generated_at": datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC),
    }

    response = client.post(
        "/api/v1/reports/ar_aging/run", json={"params": {"as_of_date": "2026-09-30"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["columns"] == ["bucket", "total"]
    assert body["data"]["rows"][0]["total"] == "150.00"
    assert body["data"]["period"] == "2026-09-30"
    service.run_report.assert_awaited_once()
    assert service.run_report.await_args.kwargs["raw_params"] == {"as_of_date": "2026-09-30"}


def test_run_report_route_422_on_validation_error() -> None:
    client, service = _app_with_mocks()
    service.run_report.side_effect = ValidationError("Invalid date for report parameter")

    response = client.post(
        "/api/v1/reports/ar_aging/run",
        json={"params": {"as_of_date": "2026-01-01"}},
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("/validation-error")


def test_list_snapshots_route_200() -> None:
    client, service = _app_with_mocks()
    service.list_snapshots.return_value = [
        {
            "id": uuid.uuid4(),
            "definition_id": uuid.uuid4(),
            "period": date(2026, 9, 30),
            "generated_at": datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC),
        }
    ]

    response = client.get("/api/v1/reports/ar_aging/snapshots")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"][0]["period"] == "2026-09-30"
    service.list_snapshots.assert_awaited_once()
    assert service.list_snapshots.await_args.kwargs["limit"] == 20


def test_list_snapshots_route_respects_limit_query() -> None:
    client, service = _app_with_mocks()
    service.list_snapshots.return_value = []

    response = client.get("/api/v1/reports/ar_aging/snapshots?limit=5")

    assert response.status_code == 200, response.text
    assert service.list_snapshots.await_args.kwargs["limit"] == 5


def test_export_report_route_streams_csv_and_sets_headers() -> None:
    client, service = _app_with_mocks()
    service.export_report.return_value = {
        "columns": ["bucket", "total"],
        "csv": "bucket,total\r\ncurrent,150.00\r\n",
        "rows": 1,
        "period": date(2026, 9, 30),
        "filename": "ar_aging-2026-09-30.csv",
    }

    response = client.post(
        "/api/v1/reports/ar_aging/export",
        json={"params": {"as_of_date": "2026-09-30"}},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="ar_aging-2026-09-30.csv"' in response.headers["content-disposition"]
    assert response.headers["x-report-rows"] == "1"
    assert response.content.decode("utf-8") == "bucket,total\r\ncurrent,150.00\r\n"
    service.export_report.assert_awaited_once()
    assert service.export_report.await_args.kwargs["raw_params"] == {"as_of_date": "2026-09-30"}
    assert service.export_report.await_args.kwargs["user_id"] is not None
    assert service.export_report.await_args.kwargs["actor_ip"] is not None


def test_router_requires_permission() -> None:
    app = FastAPI()
    app.include_router(reports_router.router, prefix="/api/v1")
    app.add_exception_handler(SkyrictError, skyrict_error_handler)  # type: ignore[arg-type]

    async def deny() -> None:
        raise PermissionDeniedError("Missing required permission: erp.reports.read")

    app.dependency_overrides[reports_router._require_reports_read] = deny

    client = TestClient(app)
    response = client.get("/api/v1/reports")

    assert response.status_code == 403, response.text
    assert response.json()["type"].endswith("/permission-denied")
