"""HR-AUT-002 wave 2 - run predictions + drift on a real seeded tenant.

Real Postgres + real migrations, driving the prediction through the composed
:class:`PayrollService` (same path the API uses). Coverage in this Commit 1
slice:

  * prediction on identical inputs equals the actual compute EXACTLY;
  * 18% department drift flagged, 8% not, at the default 10% threshold -
    and the prediction writes nothing (no entries, no run transition);
  * predicted skips preview the exact employees the commit will skip.

Later commits extend this file: skip-reason taxonomy, void intelligence, and
the full dry-run pipeline suite.

Skipped automatically when Postgres is unreachable (``migrated_schema``).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from core.api.deps import make_payroll_service
from core.db.session import async_session_factory, engine
from core.features.hr.models.department import DepartmentModel
from core.features.hr.models.employee import EmployeeModel
from core.features.payroll.models.compensation import CompensationModel
from core.features.payroll.models.payroll_run import PayrollRunModel, PayrollRunStatus
from core.features.payroll.models.payroll_settings import PayrollSettingsModel
from core.features.payroll.void_reasons import VoidReasonCategory
from core.models.tenant import TenantModel

pytestmark = pytest.mark.integration

MAY_START = date(2026, 5, 1)
MAY_END = date(2026, 5, 31)
JUNE_START = date(2026, 6, 1)
JUNE_END = date(2026, 6, 30)


@pytest.fixture(scope="module")
def prediction_world(migrated_schema: None) -> dict[str, str]:
    """One tenant: 2 departments, 4 employees (1 uncompensated), 2 runs.

    May run is computed (the "previous period" actual). June run stays DRAFT
    so the prediction is exercised before any commit. Salary bumps effective
    June 1 push Engineering +18% and Support +8% vs May; the unassigned
    employee is flat.
    """

    async def _setup() -> dict[str, str]:
        tenant_id = str(uuid.uuid4())
        eng_id = str(uuid.uuid4())
        sup_id = str(uuid.uuid4())
        emp_eng = str(uuid.uuid4())
        emp_sup = str(uuid.uuid4())
        emp_nocomp = str(uuid.uuid4())
        emp_unassigned = str(uuid.uuid4())
        prev_run_id = str(uuid.uuid4())
        current_run_id = str(uuid.uuid4())
        async with async_session_factory() as session:
            session.add(
                TenantModel(
                    id=uuid.UUID(tenant_id),
                    name="Prediction Tenant",
                    slug=f"prediction-{tenant_id[:8]}",
                    plan_tier="enterprise",
                    is_active=True,
                )
            )
            await session.flush()
            session.add(
                PayrollSettingsModel(
                    tenant_id=uuid.UUID(tenant_id),
                    default_currency="USD",
                    pf_rate=0,
                    tax_rate=0,
                )
            )
            for dept in (
                (eng_id, "Engineering"),
                (sup_id, "Support"),
            ):
                session.add(
                    DepartmentModel(
                        tenant_id=uuid.UUID(tenant_id),
                        id=uuid.UUID(dept[0]),
                        name=dept[1],
                    )
                )
            for employee in (
                (emp_eng, "EMP-0001", "Alex", "Eng", eng_id),
                (emp_sup, "EMP-0002", "Blake", "Sup", sup_id),
                (emp_nocomp, "EMP-0003", "Casey", "NoComp", sup_id),
                (emp_unassigned, "EMP-0004", "Dana", "Solo", None),
            ):
                session.add(
                    EmployeeModel(
                        tenant_id=uuid.UUID(tenant_id),
                        id=uuid.UUID(employee[0]),
                        employee_number=employee[1],
                        first_name=employee[2],
                        last_name=employee[3],
                        job_title="Engineer",
                        hire_date=date(2025, 1, 1),
                        department_id=uuid.UUID(employee[4]) if employee[4] else None,
                    )
                )
            await session.flush()
            for compensation in (
                (emp_eng, "1000", date(2026, 1, 1)),
                (emp_eng, "1180", date(2026, 6, 1)),  # +18% from June
                (emp_sup, "2000", date(2026, 1, 1)),
                (emp_sup, "2160", date(2026, 6, 1)),  # +8% from June
                (emp_unassigned, "500", date(2026, 1, 1)),
            ):
                session.add(
                    CompensationModel(
                        tenant_id=uuid.UUID(tenant_id),
                        id=uuid.uuid4(),
                        employee_id=uuid.UUID(compensation[0]),
                        monthly_salary=compensation[1],
                        currency="USD",
                        effective_from=compensation[2],
                    )
                )
            for run in (
                (prev_run_id, "PR-0060", MAY_START, MAY_END),
                (current_run_id, "PR-0061", JUNE_START, JUNE_END),
            ):
                session.add(
                    PayrollRunModel(
                        tenant_id=uuid.UUID(tenant_id),
                        id=uuid.UUID(run[0]),
                        run_code=run[1],
                        period_start=run[2],
                        period_end=run[3],
                        status=PayrollRunStatus.DRAFT,
                    )
                )
            await session.commit()
            # Compute the MAY run at module scope so the "previous period"
            # actual is genuinely persisted for the comparison.
            async with async_session_factory() as compute_session:
                service = make_payroll_service(compute_session)
                result = await service.compute_run(
                    run_id=uuid.UUID(prev_run_id), tenant_id=uuid.UUID(tenant_id)
                )
                await compute_session.commit()
                assert result.run.total_net is not None
                assert result.run.total_net.amount == Decimal("3500.00")
            await engine.dispose()
        return {
            "tenant_id": tenant_id,
            "prev_run_id": prev_run_id,
            "current_run_id": current_run_id,
            "emp_eng": emp_eng,
            "emp_sup": emp_sup,
            "emp_nocomp": emp_nocomp,
            "emp_unassigned": emp_unassigned,
        }

    world = asyncio.run(_setup())

    yield world

    async def _teardown() -> None:
        tid = uuid.UUID(world["tenant_id"])
        async with async_session_factory() as session:
            for table in (
                "erp_payroll_entries",
                "erp_payslip_reviews",
                "erp_payroll_runs",
                "erp_compensation",
                "erp_payroll_settings",
                "erp_employees",
                "erp_departments",
            ):
                await session.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                    {"tid": tid},
                )
            await session.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tid})
            await session.commit()
            await engine.dispose()

    asyncio.run(_teardown())


def _service(session: Any):
    """Composed payroll service on ``session`` - the API's exact seam."""
    return make_payroll_service(session)


async def test_prediction_matches_actual_exactly(prediction_world: dict[str, str]) -> None:
    """Same inputs -> the estimate and the real compute agree to the cent."""
    async with async_session_factory() as session:
        service = _service(session)
        current_id = uuid.UUID(prediction_world["current_run_id"])
        tenant_id = uuid.UUID(prediction_world["tenant_id"])

        prediction = await service.predict_run(run_id=current_id, tenant_id=tenant_id)
        result = await service.compute_run(run_id=current_id, tenant_id=tenant_id)

        assert result.run.total_gross is not None
        assert result.run.total_net is not None
        assert prediction.predicted_total_gross.amount == result.run.total_gross.amount
        assert prediction.predicted_total_net.amount == result.run.total_net.amount
        assert prediction.predicted_total_net.amount == Decimal("3840.00")


async def test_drift_split_18pct_flagged_8pct_not_and_prediction_writes_nothing(
    prediction_world: dict[str, str],
) -> None:
    """Department drift split + read-only guarantee on a real tenant."""
    async with async_session_factory() as session:
        service = _service(session)
        current_id = uuid.UUID(prediction_world["current_run_id"])
        tenant_id = uuid.UUID(prediction_world["tenant_id"])

        prediction = await service.predict_run(run_id=current_id, tenant_id=tenant_id)

        assert prediction.drift_threshold_pct == Decimal("0.10")
        assert prediction.previous_run is not None
        by_name = {d.department_name: d for d in prediction.departments}
        engineering = by_name["Engineering"]
        support = by_name["Support"]
        assert engineering.predicted_net.amount == Decimal("1180.00")
        assert engineering.previous_net.amount == Decimal("1000.00")
        assert engineering.delta_pct == Decimal("18.00")
        assert engineering.drifted is True
        assert support.predicted_net.amount == Decimal("2160.00")
        assert support.previous_net.amount == Decimal("2000.00")
        assert support.delta_pct == Decimal("8.00")
        assert support.drifted is False
        unassigned = by_name["Unassigned"]
        assert unassigned.delta_pct == Decimal("0.00")
        assert unassigned.drifted is False
        # Read-only: nothing persisted for the current run.
        persisted = await session.execute(
            text("SELECT count(*) FROM erp_payroll_entries WHERE run_id = :rid"),
            {"rid": current_id},
        )
        assert persisted.scalar_one() == 0
        # Predicted skips equal the exact uncompensated employee.
        assert [(record.employee_id, record.reason) for record in prediction.predicted_skipped] == [
            (uuid.UUID(prediction_world["emp_nocomp"]), "no effective compensation")
        ]


async def test_post_run_analysis_full_reasons_and_bank_risk_rows(
    prediction_world: dict[str, str],
) -> None:
    """Every skip has a taxonomy code; bank-less paid employees are risk rows.

    HR-AUT-002 §5.3.5: zero silent / unclassified skips after a real compute,
    and the missing-bank-details fix group reads back from the persisted run.
    """
    async with async_session_factory() as session:
        tenant_id = uuid.UUID(prediction_world["tenant_id"])
        prev_run_id = uuid.UUID(prediction_world["prev_run_id"])
        row = (
            await session.execute(
                text(
                    "SELECT skipped_employees FROM erp_payroll_runs "
                    "WHERE id = :rid AND tenant_id = :tid"
                ),
                {"rid": prev_run_id, "tid": tenant_id},
            )
        ).scalar_one()
        assert isinstance(row, list) and len(row) == 4
        by_id = {entry["employee_id"]: entry for entry in row}
        assert by_id[prediction_world["emp_nocomp"]]["reason_code"] == "no_compensation"
        assert by_id[prediction_world["emp_nocomp"]]["category"] == "skip"
        for paid_id in (
            prediction_world["emp_eng"],
            prediction_world["emp_sup"],
            prediction_world["emp_unassigned"],
        ):
            assert by_id[paid_id]["reason_code"] == "missing_bank_details"
            assert by_id[paid_id]["category"] == "risk"
        assert all(entry["reason_code"] != "unclassified" for entry in row)


async def test_void_with_reason_classifies_and_persists_raw_text(
    prediction_world: dict[str, str],
) -> None:
    """§5.8.3: the operator's raw void reason is stored verbatim (not the old
    hardcoded default) and the report derives the Duplicate category."""
    async with async_session_factory() as session:
        service = _service(session)
        current_id = uuid.UUID(prediction_world["current_run_id"])
        tenant_id = uuid.UUID(prediction_world["tenant_id"])

        voided = await service.void_run(
            run_id=current_id,
            tenant_id=tenant_id,
            reason="created twice by mistake",
        )
        assert voided.status.value == PayrollRunStatus.VOID.value
        assert voided.void_reason == "created twice by mistake"
        assert "voided via API" not in (voided.void_reason or "")

        report = await service.void_reason_report(tenant_id=tenant_id, months=6)
        assert report.category_totals[VoidReasonCategory.DUPLICATE] == 1
        june = next(month for month in report.months if month.month == date(2026, 6, 1))
        assert june.counts[VoidReasonCategory.DUPLICATE] == 1
