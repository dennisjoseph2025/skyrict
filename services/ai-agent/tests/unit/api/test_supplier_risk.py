"""Unit tests for the supplier-risk read endpoint (SKY-86).

The app is exercised through TestClient without lifespan (no DB/Redis pools),
with the auth dependency stubbed to a fixed caller and the repository read
replaced by a scripted fake. These tests cover the wire contract: tenant
scoping, payload mapping (Decimal -> str), and the empty-tenancy shape.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.db.supplier_risk_repository import SupplierRiskRepository
from ai_agent.domain.supplier_risk import SupplierRiskAssessment
from ai_agent.main import create_app

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

_TENANT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_CALLER = {
    "user_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
    "tenant_id": _TENANT_ID,
    "token_payload": {"sub": "11111111-1111-4111-8111-111111111111"},
}


class _NullSession:
    """Stands in for the async session (the read is fully faked away)."""

    async def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("repository is faked; session must not be touched")

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def _app_with_read(
    monkeypatch: pytest.MonkeyPatch,
    grades: list[SupplierRiskAssessment],
) -> tuple[TestClient, Callable[..., object]]:
    # The tenant middleware resolves the slug against Postgres; bypass it
    # (its behaviour has its own tests) and stub the auth dependency with a
    # fixed caller instead - same seam as the other API unit tests.
    monkeypatch.setattr("ai_agent.api.middleware.is_tenant_required_path", lambda _path: False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    app.dependency_overrides[get_db] = lambda: _NullSession()

    async def fake_list_all(self, *, tenant_id: uuid.UUID) -> list[SupplierRiskAssessment]:
        assert tenant_id == _TENANT_ID
        return grades

    return TestClient(app, raise_server_exceptions=True), fake_list_all


def _grade(
    *,
    supplier_id: uuid.UUID,
    score: str = "0.313",
    band: str = "low",
    confidence: str = "0.8",
    reason: str = "low risk, on-time delivery 100.0%",
) -> SupplierRiskAssessment:
    return SupplierRiskAssessment(
        supplier_id=supplier_id,
        score=Decimal(score),
        risk_band=band,  # type: ignore[arg-type]
        confidence=Decimal(confidence),
        reason=reason,
    )


def test_empty_grades_return_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _app_with_read(monkeypatch, [])
    monkeypatch.setattr(SupplierRiskRepository, "list_all", fake)

    response = client.get("/api/v1/ai/supplier-risk", headers={"authorization": "Bearer t"})

    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"count": 0}}


def test_grades_have_stringified_decimals(monkeypatch: pytest.MonkeyPatch) -> None:
    supplier_id = uuid.uuid4()
    grade = _grade(
        supplier_id=supplier_id,
        score="0.6900",
        band="high",
        confidence="0.4000",
        reason="high risk, on-time delivery 51.0%",
    )
    client, fake = _app_with_read(monkeypatch, [grade])
    monkeypatch.setattr(SupplierRiskRepository, "list_all", fake)

    response = client.get("/api/v1/ai/supplier-risk", headers={"authorization": "Bearer t"})

    assert response.status_code == 200
    (item,) = response.json()["data"]
    assert item == {
        "supplier_id": str(supplier_id),
        "score": "0.6900",
        "risk_band": "high",
        "confidence": "0.4000",
        "reason": "high risk, on-time delivery 51.0%",
    }
    assert response.json()["meta"] == {"count": 1}
