# SKY-82 / FIN-AI-003 — A4 Revenue Forecast Eval Note

Module: finance (`core.features.revenue_forecast`). Companion note to the A3
finance-chat reconciliation suite in `services/ai-agent/tests/eval/`.

## Model

- Method: trailing **6-month simple moving average (SMA-6)**, flat across a
  **12-month horizon** (`HORIZON_MONTHS = 12`).
- Source: recognized revenue = **approved invoices only**, bucketed by month.
- Abstention guardrail: with **fewer than 6 months** of history the model
  returns an empty point set (`MIN_HISTORY_MONTHS = 6`) and the weekly/manual
  refresh persists nothing.
- Confidence band: `predicted ± 1.5σ` of the walk-forward signed prediction
  error, floored at zero; band is omitted when there are no backtest errors.
- Walk-forward backtest: for each month `t` with 6 prior months, score SMA-6
  against the actual; aggregate error = **MAPE** (weighted by actual revenue).

## Seed data

Both seeds are deterministic over 18 months of monthly recognized revenue
(2025-01 → 2026-06), run with the current calculator:

| Seed | Construction | Backtest MAPE | σ |
|------|--------------|---------------|-----|
| Linear ramp | `revenue = 10,000 + m·1,000` (month 1…18) | **15.56%** | <0.01 (floored at `0.0001`; a deterministic ramp is nearly perfectly predictable) |
| Seasonal + wobble | `20,000 + 1,200·sin(2π(m−1)/12) + 300·cos(3(m−1))` | **4.97%** | ≈ **1,124.35** |

Seasonal example band on the first forecast point (predicted 20,764):
`[19,078, 22,451]`, i.e. ±1.5σ ≈ ±1,687.

## Tolerance

Stated tolerance: **MAPE ≤ 25%** on seed data. Both seeds pass (15.56% and
4.97%), and the seasonal seed exercises the expected banding behaviour.

## Open item (cross-module dependency)

Ticket scope lists "pipeline conversion weighting from CRM deal health".
Deal-health data lives in the CRM module, which is out of the finance module
boundary, so the weighting is **not implemented** in this increment. The
forecast model is architected to accept an optional weighted-pipeline
contribution (per-stage conversion probability × open deal amount) when a
finance-consumable feed exists; until then the forecast uses invoicing
curves only. This is tracked as a hand-off to the CRM module, not a
forecast-model gap.