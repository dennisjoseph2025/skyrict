"""Backtest: risk-adjusted restock v2 vs plain v2 vs v1 (SKY-86 / INV-AI-004).

Deterministic simulation - no LLM, no network, no DB. It replays a
synthetic demand history through the production restock formula variants and
measures, for each variant:

  * Stockout days   - days on hand reached/exceeded zero (a demand miss).
  * Order volume    - total units ordered over the horizon.
  * Days of cover   - average inventory on hand expressed as days of demand.

The goal is a reproducible sanity check that the risk-adjusted formula keeps
high-risk suppliers covered during long, variable lead times without
unreasonably exploding order volume vs the plain v2 baseline.

Run from anywhere inside the repo (the console script adds ai-agent's source
to ``sys.path`` so it imports the real calculator):

    python scripts/backtest/supplier_risk_demand.py
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from ai_agent.features.nl_query.gateway import ProductRef
from ai_agent.features.restock.calculator import (
    DemandProfile,
    SuggestionDraft,
    compute_suggestion,
)

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "services" / "ai-agent" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# --- Scenario ----------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """One replayable demand/lead scenario."""

    name: str
    avg_daily_demand: Decimal
    demand_volatility: float  # 0 = constant, higher = burstier
    lead_time_days: Decimal
    safety_factor: Decimal
    risk_band: str | None
    horizon_days: int = 240
    seed: int = 20260807


_SCENARIOS = (
    Scenario(
        name="high-risk long-lead",
        avg_daily_demand=Decimal("20"),
        demand_volatility=0.4,
        lead_time_days=Decimal("14"),
        safety_factor=Decimal("1.0"),
        risk_band="high",
    ),
    Scenario(
        name="same-demand plain-v2",
        avg_daily_demand=Decimal("20"),
        demand_volatility=0.4,
        lead_time_days=Decimal("14"),
        safety_factor=Decimal("1.0"),
        risk_band=None,
    ),
    Scenario(
        name="same-demand v1",
        avg_daily_demand=Decimal("20"),
        demand_volatility=0.4,
        lead_time_days=Decimal("14"),
        safety_factor=Decimal("1.0"),
        risk_band=None,
    ),
)


@dataclass
class Run:
    """Outcome of replaying one formula variant over one scenario."""

    variant: str
    scenario: str
    stockout_days: int = 0
    units_ordered: int = 0
    inventory_days: list[Decimal] = field(default_factory=list)

    @property
    def avg_cover_days(self) -> float:
        if not self.inventory_days:
            return 0.0
        raw = sum(float(d) for d in self.inventory_days) / len(self.inventory_days)
        return round(raw, 1)


def _daily_demand(scenario: Scenario, rng: random.Random) -> list[Decimal]:
    """Constant-plus-noise demand sequence (never negative)."""
    daily: list[Decimal] = []
    for _ in range(scenario.horizon_days):
        noise = rng.gauss(0, float(scenario.avg_daily_demand) * scenario.demand_volatility)
        value = max(Decimal("2"), scenario.avg_daily_demand + Decimal(str(round(noise, 2))))
        daily.append(value)
    return daily


def _as_product(risk_band: str | None) -> ProductRef:
    return ProductRef(
        id=uuid4(),
        sku="SIM-001",
        name="Simulated SKU",
        reorder_point=Decimal("40"),
        cost_price=Decimal("10.00"),
        supplier_id=uuid4() if risk_band else None,
    )


def _variant_suggestion(
    day: int, on_hand: Decimal, scenario: Scenario, variant: str
) -> SuggestionDraft:
    qty = Decimal(on_hand)
    if variant == "v1":
        return compute_suggestion(
            product=_as_product(None),
            warehouse_id=uuid4(),
            qty_on_hand=qty,
            movements=None,
            demand=None,
        )
    risk_band = scenario.risk_band if variant == "risk" else None
    demand = DemandProfile(
        avg_daily_demand=scenario.avg_daily_demand,
        eligible=True,
        lead_time_days=scenario.lead_time_days,
        safety_factor=scenario.safety_factor,
        risk_band=risk_band,  # type: ignore[arg-type]
    )
    return compute_suggestion(
        product=_as_product(risk_band),
        warehouse_id=uuid4(),
        qty_on_hand=qty,
        movements=None,
        demand=demand,
    )


def _replay(scenario: Scenario, variant: str) -> Run:
    rng = random.Random(scenario.seed)
    daily = _daily_demand(scenario, rng)
    run = Run(variant=variant, scenario=scenario.name)

    on_hand = Decimal("25")  # start low enough to trigger reorders
    pending = Decimal(0)  # units in transit for the plain delivery model
    for day, demand_today in enumerate(daily):
        # Deliver any order placed `lead_time_days` ago (simplified FIFO in flight).
        if pending > 0 and day % max(1, int(scenario.lead_time_days)) == 0:
            on_hand += pending
            pending = Decimal(0)

        draft = _variant_suggestion(day, on_hand, scenario, variant)
        target = draft.suggested_qty
        if target > 0:
            run.units_ordered += int(target)
            pending = target if variant != "v1" else max(pending, target)

        on_hand -= demand_today
        if on_hand < 0:
            on_hand = Decimal(0)
            run.stockout_days += 1

        run.inventory_days.append(
            max(Decimal(0), on_hand) / max(Decimal("1"), scenario.avg_daily_demand)
        )

    return run


def main() -> None:
    print("SKY-86 backtest - risk-adjusted restock v2 vs plain v2 vs v1")
    print(f"  today: {date.today().isoformat()}")
    print()

    rows: list[Run] = []
    for scenario in _SCENARIOS:
        variant = {
            "high-risk long-lead": "risk",
            "same-demand plain-v2": "v2",
            "same-demand v1": "v1",
        }[scenario.name]
        rows.append(_replay(scenario, variant))

    header = f"{'variant':<22}{'scenario':<26}{'stockouts':>10}{'units':>9}{'avg cover d':>13}"
    print(header)
    print("-" * len(header))
    for run in rows:
        print(
            f"{run.variant:<22}{run.scenario:<26}{run.stockout_days:>10}"
            f"{run.units_ordered:>9}{run.avg_cover_days:>13}"
        )

    print()
    by = {r.variant: r for r in rows}
    print("Interpretation (same demand stream, so the models differ only in policy):")
    print(
        f"  risk vs v2  -> stockouts {by['risk'].stockout_days - by['v2'].stockout_days:+d}, "
        f"units {by['risk'].units_ordered - by['v2'].units_ordered:+d}"
    )
    print(
        f"  v2   vs v1  -> stockouts {by['v2'].stockout_days - by['v1'].stockout_days:+d}, "
        f"units {by['v2'].units_ordered - by['v1'].units_ordered:+d}"
    )


if __name__ == "__main__":
    main()
