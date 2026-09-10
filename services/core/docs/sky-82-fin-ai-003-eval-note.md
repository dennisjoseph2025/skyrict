# SKY-82 / FIN-AI-003 — A4 Revenue Forecast Eval Note

Module: finance (`core.features.revenue_forecast`). Companion note to the A3
finance-chat reconciliation suite in `services/ai-agent/tests/eval/`.

## Model

- Method: **damped linear trend + seasonal echo** over a **12-month horizon**
  (`HORIZON_MONTHS = 12`). A least-squares trend is fit to the recognized
  revenue series and projected forward with damping (`TREND_DAMPING = 0.90`, so
  each later month's increment shrinks and the projection curves toward a
  plateau instead of over-extrapolating). For every calendar month already seen,
  the average deviation from the trend line is added back to the projected
  month with the same calendar month, reproducing observed ups and downs
  (seasonality, quarterly peaks) rather than a flat line.
- Source: recognized revenue = **approved invoices only**, bucketed by month.
- Abstention guardrail: with **fewer than 3 months** of history the model
  returns an empty point set (`MIN_HISTORY_MONTHS = 3`) and the weekly/manual
  refresh persists nothing (per FIN-AI-003).
- Confidence band: `predicted ± 1.5σ` of the walk-forward signed prediction
  error, floored at zero; band is omitted when there are no backtest errors.
- Walk-forward backtest: for each month `t ≥ 3`, refit the trend + seasonal
  echo over the prior months and score the prediction against the actual;
  aggregate error = **MAPE** (weighted by actual revenue). Backtest errors start
  accumulating once ≥3 months are available, so band/MAPE confidence densifies
  as history accrues.

## Seed data

Both seeds are deterministic over 18 months of monthly recognized revenue
(2025-01 → 2026-06), measured with the current calculator:

| Seed | Construction | Backtest MAPE | σ |
|------|--------------|---------------|-----|
| Linear ramp | `revenue = 10,000 + m·1,000` (month 1…18) | **0.00%** | <0.01 (floored at `0.0001`; a deterministic ramp is exactly predictable to a trend fit) |
| Seasonal + wobble | `20,000 + 1,200·sin(2π(m−1)/12) + 300·cos(3(m−1))` | **4.48%** | ≈ **1,085.53** |

Seasonal example band on the first forecast point (predicted 20,246.04):
`[18,617.73, 21,874.34]`, i.e. ±1.5σ ≈ ±1,628.30. The ramp seed projects
upward (28,900 → 30,439 → … with damping) — neither seed produces a flat line.

## Tolerance

Stated tolerance: **MAPE ≤ 25%** on seed data. Both seeds pass (0.00% and
4.48%), improved over the previous SMA-6 baseline (15.56% / 4.97%), and the
seasonal seed exercises the expected ups/downs and banding behaviour.

## Pipeline conversion weighting (SKY-82)

Implemented: each forecast month may carry an **additive weighted-pipeline
uplift** over the damped-trend + seasonal baseline. The repository reads the
tenant's own open CRM opportunities in the shared database (same tenant
scope) and for every non-terminal deal with an amount and an
`expected_close_date` in the horizon adds `probability/100 × amount` to that
deal's expected close month. The uplift applies to **projected months only** —
the walk-forward backtest, MAPE, and σ band are computed over historical
months, so pipeline input can never inflate the model's reported accuracy.
The run-level total is persisted as `erp_revenue_forecast.pipeline_value`
(migration 0044, `NULL` when the forecast abstains or predates the feature)
and surfaced on the forecast response.

Live acme tenant (2026-09-09 refresh): weighted pipeline $604,875 —
Sep 2026 +$518,800 (four deals), Oct 2026 +$75,275, Nov 2026 +$10,800; a
$79,200 prospecting deal without an amount is correctly excluded. MAPE and σ
are unchanged (32.0870% / 17,332.45) because the uplift only shifts projected
points.

Still open (cross-module dependency): **deal-health modulation** — a
green/yellow/red health factor from the ai-agent's deal-health engine that
would scale the weighted value per deal. Deals are currently weighted by
stage probability only; feeding deal health requires a finance-consumable,
authenticated bulk feed from ai-agent to core (the scheduled refresh runs on
a system-agent token with no background auth bridge today). That is a
hand-off to the ai-agent module, not a forecast-model gap.