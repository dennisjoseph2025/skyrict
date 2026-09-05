"""Wire-contract tests for the /ai/finance routers (FIN-AI-002, SKY-67).

Exercised through TestClient WITHOUT lifespan (no DB/Redis), with the auth
dependency stubbed and a fake LlmRouter installed on app.state. The LLM
primitives themselves are unit-tested in features/test_account_suggest.py;
here we assert the router mapping (body -> request -> response) only.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from ai_agent.api.deps import get_current_user
from ai_agent.core.providers import LlmCompletion
from ai_agent.main import create_app


class _FakeLlmRouter:
    def __init__(self, text: str) -> None:
        self._text = text

    async def complete(self, request: object) -> LlmCompletion:
        return LlmCompletion(text=self._text, model_used="fake-model", latency_ms=10)


_CALLER = {
    "user_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
    "tenant_id": uuid.UUID("22222222-2222-4222-8222-222222222222"),
    "token_payload": {"sub": "11111111-1111-4111-8111-111111111111"},
}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Bypass the tenant middleware like test_chat.py does: the endpoint
    # behaviour is what we cover, the middleware has its own tests.
    monkeypatch.setattr("ai_agent.api.middleware.is_tenant_required_path", lambda _path: False)
    test_client = TestClient(create_app(), raise_server_exceptions=False)
    test_client.app.dependency_overrides[get_current_user] = lambda: _CALLER
    yield test_client
    test_client.app.dependency_overrides.clear()


def _set_llm(client: TestClient, text: str) -> None:
    client.app.state.llm_router = _FakeLlmRouter(text)


def test_narrate_anomaly_router_maps_fields(client: TestClient) -> None:
    _set_llm(
        client,
        '{"narration": "Duplicate entries both post 1,200 - flagging for review.",'
        ' "confidence": 0.9}',
    )
    response = client.post(
        "/api/v1/ai/finance/anomalies/narrate",
        json={
            "anomaly_type": "duplicate_entry",
            "description": "Two identical entries posted on the same day.",
            "severity": "medium",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "narration": "Duplicate entries both post 1,200 - flagging for review.",
        "model_used": "fake-model",
    }


def test_narrate_anomaly_router_abstains_on_empty(client: TestClient) -> None:
    _set_llm(client, '{"narration": "", "confidence": 0.1}')
    response = client.post(
        "/api/v1/ai/finance/anomalies/narrate",
        json={"anomaly_type": "x", "description": "y", "severity": "low"},
    )
    assert response.status_code == 200
    assert response.json() == {"narration": "", "model_used": ""}


def test_draft_reminder_router_maps_fields(client: TestClient) -> None:
    _set_llm(
        client,
        '{"subject": "Payment Reminder - Invoice INV-009",'
        ' "body": "Please settle invoice INV-009 for 1,500.", "tone": "polite"}',
    )
    response = client.post(
        "/api/v1/ai/finance/reminders/draft",
        json={
            "customer_name": "Acme Corp",
            "invoice_number": "INV-009",
            "amount": 1500.0,
            "days_overdue": 15,
            "tone": "polite",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "subject": "Payment Reminder - Invoice INV-009",
        "body": "Please settle invoice INV-009 for 1,500.",
        "tone": "polite",
        "model_used": "fake-model",
    }


def test_draft_reminder_router_defaults_tone_on_abstention(client: TestClient) -> None:
    _set_llm(client, '{"subject": "", "body": "", "tone": "polite"}')
    response = client.post(
        "/api/v1/ai/finance/reminders/draft",
        json={
            "invoice_number": "INV-010",
            "amount": 500.0,
            "days_overdue": 5,
            "tone": "firm",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "subject": "",
        "body": "",
        "tone": "firm",
        "model_used": "",
    }


def test_draft_entry_router_maps_lines(client: TestClient) -> None:
    _set_llm(
        client,
        '{"lines": ['
        ' {"account_code": "1500", "account_name": "Equipment", "amount": 500,'
        '  "side": "debit", "description": "Purchase"},'
        ' {"account_code": "1000", "account_name": "Cash", "amount": 500,'
        '  "side": "credit", "description": "Payment"}],'
        ' "explanation": "Debit equipment, credit cash.",'
        ' "confidence": 0.92, "reasoning": "Standard purchase."}',
    )
    response = client.post(
        "/api/v1/ai/finance/draft-entry",
        json={
            "description": "paid cash to buy furniture",
            "accounts": [
                {"code": "1000", "name": "Cash"},
                {"code": "1500", "name": "Equipment"},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["lines"]) == 2
    assert body["lines"][0]["account_code"] == "1500"
    assert body["lines"][1]["account_code"] == "1000"
    assert body["confidence"] == 0.92
    assert body["model_used"] == "fake-model"


def test_draft_entry_router_abstains_empty(client: TestClient) -> None:
    _set_llm(client, '{"lines": [], "explanation": "", "confidence": 0.0}')
    response = client.post(
        "/api/v1/ai/finance/draft-entry",
        json={
            "description": "mystery",
            "accounts": [{"code": "1000", "name": "Cash"}],
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "lines": [],
        "explanation": "",
        "confidence": 0.0,
        "reasoning": "",
        "model_used": "",
    }
