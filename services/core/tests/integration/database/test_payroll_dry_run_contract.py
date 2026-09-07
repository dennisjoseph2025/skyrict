"""HR-AUT-002 wave 2 Commit 4 - dry-run contract suite across seed tenants.

The "dry run" IS the prediction: a read-only rehearsal of what a committed
compute would pay, surfaced to the HR admin before anything is written. This
suite pins the contract on a real database with two tenants:

  * ``dry``      - Engineering bumps +18% in June (drift flagged) and one
                   employee has no compensation (predicted skip, bank risk).
  * ``steady``   - identical salaries May->June (no drift), everyone paid.

Contract under test (reads the wave-2 plan Commit 4):
  1. predicting on a DRAFT run writes NOTHING - no entries, no totals, no
     run transition - for every tenant;
  2. per-tenant forecast data is tenant-isolated (A's departments/skips never
     leak into B);
  3. the committed compute reproduces the dry-run forecast EXACTLY, proving
     the rehearsal is faithful and usable as an approval gate.

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
from core.models.tenant import TenantModel

pytestmark = pytest.mark.integration

MAY_START = date(2026, 5, 1)
MAY_END = date(2026, 5, 31)
JUNE_START = date(2026, 6, 1)
JUNE_END = date(2026, 6, 30)


async def _seed_tenant(
    session: Any,
    *,
    suffix: str,
    drift_pct: int,
    with_skip: bool,
) -> dict[str, str]:
    """Seed one tenant: dept, employees, comp, a computed May run, draft June."""
    tenant_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    emp_paid = str(uuid.uuid4())
    emp_skipped = str(uuid.uuid4())
    prev_run_id = str(uuid.uuid4())
    current_run_id = str(uuid.uuid4())

    session.add(
        TenantModel(
            id=uuid.UUID(tenant_id),
            name=f"Dry-Run {suffix}",
            slug=f"dryrun-{suffix}-{tenant_id[:8]}",
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
    session.add(
        DepartmentModel(tenant_id=uuid.UUID(tenant_id), id=uuid.UUID(dept_id), name="Engineering")
    )
    session.add(
        EmployeeModel(
            tenant_id=uuid.UUID(tenant_id),
            id=uuid.UUID(emp_paid),
            employee_number=f"DR-{suffix}-1",
            first_name="Ali",
            last_name="Paid",
            job_title="Engineer",
            hire_date=date(2025, 1, 1),
            department_id=uuid.UUID(dept_id),
        )
    )
    if with_skip:
        session.add(
            EmployeeModel(
                tenant_id=uuid.UUID(tenant_id),
                id=uuid.UUID(emp_skipped),
                employee_number=f"DR-{suffix}-2",
                first_name="Bo",
                last_name="NoPay",
                job_title="Engineer",
                hire_date=date(2025, 1, 1),
                department_id=uuid.UUID(dept_id),
            )
        )
    await session.flush()
    session.add(
        CompensationModel(
            tenant_id=uuid.UUID(tenant_id),
            id=uuid.uuid4(),
            employee_id=uuid.UUID(emp_paid),
            monthly_salary="1000",
            currency="USD",
            effective_from=date(2026, 1, 1),
        )
    )
    if drift_pct:
        session.add(
            CompensationModel(
                tenant_id=uuid.UUID(tenant_id),
                id=uuid.uuid4(),
                employee_id=uuid.UUID(emp_paid),
                monthly_salary=str(1000 * (100 + drift_pct) // 100),
                currency="USD",
                effective_from=date(2026, 6, 1),
            )
        )
    for run in (
        (prev_run_id, f"PR-{suffix}-1", MAY_START, MAY_END),
        (current_run_id, f"PR-{suffix}-2", JUNE_START, JUNE_END),
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
    return {
        "tenant_id": tenant_id,
        "prev_run_id": prev_run_id,
        "current_run_id": current_run_id,
        "emp_paid": emp_paid,
        "emp_skipped": emp_skipped,
        "drift_pct": str(drift_pct),
    }


@pytest.fixture(scope="module")
def dry_run_world(migrated_schema: None) -> dict[str, dict[str, str]]:
    async def _setup() -> dict[str, dict[str, str]]:
        async with async_session_factory() as session:
            dry = await _seed_tenant(session, suffix="a", drift_pct=18, with_skip=True)
            steady = await _seed_tenant(session, suffix="b", drift_pct=0, with_skip=False)
            await session.commit()
        # Commit each tenant's May run so "previous period" actuals are real.
        for tenant in (dry, steady):
            async with async_session_factory() as compute_session:
                service = make_payroll_service(compute_session)
                result = await service.compute_run(
                    run_id=uuid.UUID(tenant["prev_run_id"]),
                    tenant_id=uuid.UUID(tenant["tenant_id"]),
                )
                await compute_session.commit()
                assert result.run.total_net is not None
            await engine.dispose()
        return {"dry": dry, "steady": steady}

    world = asyncio.run(_setup())
    yield world

    async def _teardown() -> None:
        for tenant in world.values():
            tid = uuid.UUID(tenant["tenant_id"])
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


async def _predict(session: Any, tenant: dict[str, str]):
    service = make_payroll_service(session)
    return await service.predict_run(
        run_id=uuid.UUID(tenant["current_run_id"]),
        tenant_id=uuid.UUID(tenant["tenant_id"]),
    )


async def test_dry_run_predicts_drift_and_writes_nothing_for_each_tenant(
    dry_run_world: dict[str, dict[str, str]],
) -> None:
    """Contract #1 + #2: read-only rehearsal, tenant-isolated, drift split."""
    official = dry_run_world["dry"]
    steady = dry_run_world["steady"]

    for tenant, expected_drift in ((official, True), (steady, False)):
        async with async_session_factory() as session:
            prediction = await _predict(session, tenant)
            tenant_id = uuid.UUID(tenant["tenant_id"])
            run_id = uuid.UUID(tenant["current_run_id"])

            assert prediction.drift_threshold_pct == Decimal("0.10")
            assert prediction.predicted_total_net is not None
            # Tenant-isolated departments: only this tenant's dept shows up.
            assert [d.department_name for d in prediction.departments] == ["Engineering"]
            assert prediction.departments[0].drifted is expected_drift

            # Nothing persisted by the dry run: run stays draft with NULL totals
            # and no entries are materialized anywhere.
            persisted = await session.execute(
                text(
                    "SELECT status, total_gross, total_net FROM erp_payroll_runs "
                    "WHERE id = :rid AND tenant_id = :tid"
                ),
                {"rid": run_id, "tid": tenant_id},
            )
            status, gross, net = persisted.one()
            assert status == PayrollRunStatus.DRAFT.value
            assert gross is None and net is None
            entries = await session.execute(
                text(
                    "SELECT count(*) FROM erp_payroll_entries "
                    "WHERE run_id = :rid AND tenant_id = :tid"
                ),
                {"rid": run_id, "tid": tenant_id},
            )
            assert entries.scalar_one() == 0

            # Predicted skips listen to tenant data only.
            predicted_ids = {record.employee_id for record in prediction.predicted_skipped}
            if tenant is official:
                assert predicted_ids == {uuid.UUID(official["emp_skipped"])}
            else:
                assert predicted_ids == set()


async def test_dry_run_forecast_matches_committed_compute_per_tenant(
    dry_run_world: dict[str, dict[str, str]],
) -> None:
    """Contract #3: the commit reproduces the forecast exactly - per tenant."""
    for key, tenant in dry_run_world.items():
        async with async_session_factory() as session:
            prediction = await _predict(session, tenant)
            service = make_payroll_service(session)
            result = await service.compute_run(
                run_id=uuid.UUID(tenant["current_run_id"]),
                tenant_id=uuid.UUID(tenant["tenant_id"]),
            )
            assert result.run.total_gross is not None
            assert prediction.predicted_total_gross.amount == result.run.total_gross.amount
            assert prediction.predicted_total_net.amount == result.run.total_net.amount
            expected_net = Decimal("1000") if key == "steady" else Decimal("1180")
            assert result.run.total_net.amount == expected_net
            # Steady pays everyone (one bank-detail risk row only); the dry-run
            # tenant has an uncompensated skip + one bank risk row.
            assert len(result.run.skipped_employees or []) == (1 if key == "steady" else 2)
            await session.commit()
        await engine.dispose()
