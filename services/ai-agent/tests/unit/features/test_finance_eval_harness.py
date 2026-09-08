"""Unit tests for the finance prompt-eval harness (FIN-AI-002).

A scripted FakeLlmRouter (no network, no provider) drives every feature
runner through the production prompt functions. Covers correctness scoring
for a1_suggest / a2_draft / a7_narrate / a8_remind, abstention accounting,
threshold verdicts, and registry validation.
"""

from __future__ import annotations

from ai_agent.core.providers import LlmCompletion
from ai_agent.features.finance_eval.harness import load_registry, run_registry


class FakeLlmRouter:
    """Returns scripted completions in call order; empty fallback abstains."""

    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.calls = 0

    async def complete(self, request: object) -> LlmCompletion:
        self.calls += 1
        if not self._texts:
            return LlmCompletion(text="{}", model_used="fake-model", latency_ms=0)
        return LlmCompletion(text=self._texts.pop(0), model_used="fake-model", latency_ms=0)


_REGISTRY = """
threshold: 0.8
prompt_id: test-v1
features:
  - name: a1_suggest
    cases:
      - {id: a1-ok, description: "Paid monthly rent from cash",
         accounts: [{code: "1000", name: "Cash"}, {code: "5000", name: "Rent Expense"}],
         expected_code: "5000"}
      - {id: a1-wrong, description: "Received customer payment",
         accounts: [{code: "1100", name: "Accounts Receivable"}, {code: "1000", name: "Cash"}],
         expected_code: "1100"}
      - {id: a1-abstain, description: "Vague purchase",
         accounts: [{code: "1000", name: "Cash"}, {code: "5000", name: "Rent Expense"}],
         expected_code: "5000"}
  - name: a2_draft
    cases:
      - {id: a2-balanced, description: "Bought equipment for cash $500",
         accounts: [{code: "1000", name: "Cash"}, {code: "1500", name: "Equipment"}],
         expected_min_lines: 2}
      - {id: a2-unbalanced, description: "Bought equipment for cash $600",
         accounts: [{code: "1000", name: "Cash"}, {code: "1500", name: "Equipment"}],
         expected_min_lines: 2}
      - {id: a2-abstain, description: "Lunch with client",
         accounts: [{code: "1000", name: "Cash"}, {code: "6000", name: "Meals Expense"}],
         expected_min_lines: 0}
  - name: a7_narrate
    cases:
      - {id: a7-cites, anomaly_type: duplicate_entry, severity: medium,
         description: "Two invoices totalling $8,100 appear twice.", expected_cites_figure: true}
      - {id: a7-nofig, anomaly_type: duplicate_entry, severity: low,
         description: "Two identical entries exist.", expected_cites_figure: true}
  - name: a8_remind
    cases:
      - {id: a8-ok, invoice_number: "INV-001", amount: 1500.0, days_overdue: 15, tone: polite}
      - {id: a8-missing-amount, invoice_number: "INV-002", amount: 500.0, days_overdue: 5, tone: firm}
"""

_RESPONSES = (
    # a1: ok, wrong (valid code, wrong pick), abstain
    '{"suggested_code": "5000", "suggested_name": "Rent Expense", "confidence": 0.9}',
    '{"suggested_code": "1000", "suggested_name": "Cash", "confidence": 0.8}',
    "not json",
    # a2: balanced, unbalanced, abstain-when-expected
    '{"lines": [{"account_code": "1500", "account_name": "Equipment", "amount": 500,'
    ' "side": "debit", "description": ""},'
    ' {"account_code": "1000", "account_name": "Cash", "amount": 500,'
    ' "side": "credit", "description": ""}],'
    ' "explanation": "T", "confidence": 0.9, "reasoning": "T"}',
    '{"lines": [{"account_code": "1500", "account_name": "Equipment", "amount": 600,'
    ' "side": "debit", "description": ""},'
    ' {"account_code": "1000", "account_name": "Cash", "amount": 500,'
    ' "side": "credit", "description": ""}],'
    ' "explanation": "T", "confidence": 0.9, "reasoning": "T"}',
    "not json",
    # a7: cites a figure, omits figures
    '{"narration": "Duplicate entries both post 8,100 - flagging for review.", "confidence": 0.9}',
    '{"narration": "A duplicate entry was detected.", "confidence": 0.9}',
    # a8: includes invoice + amount, omits the amount
    '{"subject": "Reminder", "body": "Please pay invoice INV-001 for 1,500.00.", "tone": "polite"}',
    '{"subject": "Reminder", "body": "Please pay invoice INV-002 now.", "tone": "firm"}',
)


async def test_run_registry_scores_every_feature(tmp_path) -> None:
    registry = tmp_path / "finance_prompts.yaml"
    registry.write_text(_REGISTRY, encoding="utf-8")

    metrics = {
        m.feature: m
        for m in await run_registry(registry, FakeLlmRouter(*_RESPONSES))  # type: ignore[arg-type]
    }

    suggest = metrics["a1_suggest"]
    assert suggest.considered == 2
    assert suggest.abstained == 1
    assert suggest.precision == 0.5
    assert not suggest.met_threshold

    draft = metrics["a2_draft"]
    assert draft.considered == 3
    assert draft.precision == 2 / 3
    assert not draft.met_threshold

    narrate = metrics["a7_narrate"]
    assert narrate.considered == 2
    assert narrate.precision == 0.5
    assert narrate.details == {"a7-cites": "correct", "a7-nofig": "incorrect"}

    remind = metrics["a8_remind"]
    assert remind.considered == 2
    assert remind.precision == 0.5
    assert remind.model_used == "fake-model"
    assert remind.prompt_id == "test-v1"
    assert remind.threshold == 0.8


_ALL_PASS_REGISTRY = """
threshold: 0.8
prompt_id: pass-v1
features:
  - name: a1_suggest
    cases:
      - {id: a1-ok, description: "Paid monthly rent from cash",
         accounts: [{code: "1000", name: "Cash"}, {code: "5000", name: "Rent Expense"}],
         expected_code: "5000"}
      - {id: a1-also, description: "Paid office rent",
         accounts: [{code: "1000", name: "Cash"}, {code: "5000", name: "Rent Expense"}],
         expected_code: "5000"}
      - {id: a1-third, description: "Rent from petty cash",
         accounts: [{code: "1000", name: "Cash"}, {code: "5000", name: "Rent Expense"}],
         expected_code: "5000"}
  - name: a2_draft
    cases:
      - {id: a2-one, description: "Bought equipment for cash $500",
         accounts: [{code: "1000", name: "Cash"}, {code: "1500", name: "Equipment"}],
         expected_min_lines: 2}
      - {id: a2-two, description: "Bought supplies for cash $200",
         accounts: [{code: "1000", name: "Cash"}, {code: "1500", name: "Equipment"}],
         expected_min_lines: 2}
      - {id: a2-three, description: "Bought furniture for cash $300",
         accounts: [{code: "1000", name: "Cash"}, {code: "1500", name: "Equipment"}],
         expected_min_lines: 2}
  - name: a7_narrate
    cases:
      - {id: a7-one, anomaly_type: duplicate_entry, severity: medium,
         description: "Two invoices totalling $8,100 appear twice.", expected_cites_figure: true}
      - {id: a7-two, anomaly_type: duplicate_entry, severity: low,
         description: "Two identical $300 entries exist.", expected_cites_figure: true}
  - name: a8_remind
    cases:
      - {id: a8-one, invoice_number: "INV-001", amount: 1500.0, days_overdue: 15, tone: polite}
      - {id: a8-two, invoice_number: "INV-002", amount: 500.0, days_overdue: 5, tone: firm}
"""


async def test_run_registry_all_pass_meets_threshold(tmp_path) -> None:
    registry = tmp_path / "all_pass.yaml"
    registry.write_text(_ALL_PASS_REGISTRY, encoding="utf-8")

    def _pick(feature: str, index: int) -> str:
        if feature == "a1_suggest":
            return '{"suggested_code": "5000", "suggested_name": "Rent", "confidence": 0.9}'
        if feature == "a2_draft":
            return (
                '{"lines": [{"account_code": "1500", "account_name": "Equipment", "amount": 500,'
                ' "side": "debit", "description": ""},'
                ' {"account_code": "1000", "account_name": "Cash", "amount": 500,'
                ' "side": "credit", "description": ""}],'
                ' "explanation": "T", "confidence": 0.9, "reasoning": "T"}'
            )
        if feature == "a7_narrate":
            return '{"narration": "Duplicate posts total 8,100 today.", "confidence": 0.9}'
        amount = 1500.0 if index == 0 else 500.0
        body = f"Invoice INV-00{index + 1}, amount {amount:,.2f}."
        return f'{{"subject": "R", "body": "{body}", "tone": "polite"}}'

    texts: list[str] = []
    order = [("a1_suggest", 3), ("a2_draft", 3), ("a7_narrate", 2), ("a8_remind", 2)]
    for feature, count in order:
        for index in range(count):
            texts.append(_pick(feature, index))

    metrics = {
        m.feature: m
        for m in await run_registry(registry, FakeLlmRouter(*texts))  # type: ignore[arg-type]
    }
    assert all(m.met_threshold for m in metrics.values())
    assert metrics["a1_suggest"].precision == 1.0
    assert metrics["a2_draft"].precision == 1.0
    assert metrics["a7_narrate"].precision == 1.0
    assert metrics["a8_remind"].precision == 1.0


async def test_load_registry_rejects_bad_schema(tmp_path) -> None:
    bad_only = tmp_path / "bad.yaml"
    bad_only.write_text("models: []\n", encoding="utf-8")
    try:
        load_registry(bad_only)
    except ValueError:
        pass
    else:  # pragma: no cover - guard against silent schema drift
        raise AssertionError("expected ValueError for a registry without threshold/features")

    bad_threshold = tmp_path / "bad2.yaml"
    bad_threshold.write_text("threshold: nope\nfeatures: []\n", encoding="utf-8")
    try:
        load_registry(bad_threshold)
    except ValueError:
        pass
    else:  # pragma: no cover - guard against silent schema drift
        raise AssertionError("expected ValueError for a non-numeric threshold")
