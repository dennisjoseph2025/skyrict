"""Unit tests for report parameter validation (RPT-BE-001)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from core.features.reporting.params import build_report_binds, resolve_period
from skyrict_common.exceptions import ValidationError


class TestBuildReportBinds:
    @pytest.mark.asyncio
    async def test_binds_tenant_and_dates(self) -> None:
        tenant_id = uuid.uuid4()
        binds = build_report_binds(
            declared=("tenant_id", "from_date", "to_date"),
            raw_params={"from_date": "2026-01-01", "to_date": "2026-12-31"},
            tenant_id=tenant_id,
        )
        assert binds["tenant_id"] == tenant_id
        assert binds["from_date"] == date(2026, 1, 1)
        assert binds["to_date"] == date(2026, 12, 31)

    @pytest.mark.asyncio
    async def test_tenant_id_may_be_omitted_and_is_injected(self) -> None:
        tenant_id = uuid.uuid4()
        binds = build_report_binds(
            declared=("tenant_id",),
            raw_params={},
            tenant_id=tenant_id,
        )
        assert binds == {"tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_tenant_id_must_match_session(self) -> None:
        with pytest.raises(ValidationError, match="must match the authenticated tenant"):
            build_report_binds(
                declared=("tenant_id",),
                raw_params={"tenant_id": str(uuid.uuid4())},
                tenant_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_tenant_id_rejects_non_uuid(self) -> None:
        with pytest.raises(ValidationError, match="expected a UUID"):
            build_report_binds(
                declared=("tenant_id",),
                raw_params={"tenant_id": "not-a-uuid"},
                tenant_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_unknown_param_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Unknown report parameter"):
            build_report_binds(
                declared=("tenant_id", "as_of_date"),
                raw_params={"as_of_date": "2026-01-01", "per_page": "10"},
                tenant_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_missing_required_date_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Missing required report parameter"):
            build_report_binds(
                declared=("tenant_id", "from_date", "to_date"),
                raw_params={"from_date": "2026-01-01"},
                tenant_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_injection_shaped_date_rejected_before_sql(self) -> None:
        payload = "2026-01-01'; DROP TABLE erp_report_snapshots; --"
        with pytest.raises(ValidationError, match="Invalid date"):
            build_report_binds(
                declared=("tenant_id", "as_of_date"),
                raw_params={"as_of_date": payload},
                tenant_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_underscore_date_suffix_typed_as_date(self) -> None:
        tenant_id = uuid.uuid4()
        binds = build_report_binds(
            declared=("tenant_id", "start_date"),
            raw_params={"start_date": "2026-03-01"},
            tenant_id=tenant_id,
        )
        assert binds["start_date"] == date(2026, 3, 1)

    @pytest.mark.asyncio
    async def test_non_date_param_fails_closed(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported report parameter type"):
            build_report_binds(
                declared=("tenant_id", "warehouse"),
                raw_params={"warehouse": "WH-1"},
                tenant_id=uuid.uuid4(),
            )


class TestResolvePeriod:
    @pytest.mark.asyncio
    async def test_as_of_date_wins(self) -> None:
        assert resolve_period({"as_of_date": "2026-09-30", "from_date": "2026-01-01"}) == date(
            2026, 9, 30
        )

    @pytest.mark.asyncio
    async def test_from_date_fallback(self) -> None:
        assert resolve_period({"from_date": "2026-06-01"}) == date(2026, 6, 1)

    @pytest.mark.asyncio
    async def test_today_default(self) -> None:
        assert resolve_period({}, today=date(2026, 9, 5)) == date(2026, 9, 5)
