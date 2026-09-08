"""Seed-data consistency - stock levels must reconcile with the movement ledger.

The AI-agent ledger-mismatch rule (and core's recompute_stock_level) define
``qty_on_hand`` as the sum of all non-reservation/release movements. The demo
seed backs each opening-balance stock level with a balancing movement
(``_opening_balance_rows``), so the two constant tables must always reconcile
once that balancing set is applied.
"""

from __future__ import annotations

from decimal import Decimal

from core.seed_demo import (
    PRODUCT_ROWS,
    STOCK_LEVEL_ROWS,
    STOCK_MOVEMENT_ROWS,
    SUPPLIER_PERFORMANCE_ROWS,
    SUPPLIER_PRODUCT_MAP,
    SUPPLIER_ROWS,
    _opening_balance_rows,
)


def test_every_stock_level_reconciles_with_ledger() -> None:
    opening_rows = _opening_balance_rows(STOCK_LEVEL_ROWS, STOCK_MOVEMENT_ROWS)
    reservation_types = {"reservation", "release"}
    ledger_sum: dict[tuple[int, int], Decimal] = {}
    for mrow in [*STOCK_MOVEMENT_ROWS, *opening_rows]:
        if mrow["type"].value in reservation_types:
            continue
        key = (int(str(mrow["prod"])), int(str(mrow["wh"])))
        ledger_sum[key] = ledger_sum.get(key, Decimal(0)) + Decimal(str(mrow["qty"]))

    assert STOCK_LEVEL_ROWS, "expected at least one stock level row"
    for srow in STOCK_LEVEL_ROWS:
        key = (int(str(srow["prod"])), int(str(srow["wh"])))
        assert ledger_sum.get(key, Decimal(0)) == Decimal(str(srow["on_hand"])), (
            f"stock level {srow} does not reconcile with the movement ledger"
        )


def test_every_product_has_a_supplier_mapping() -> None:
    assert SUPPLIER_ROWS, "expected at least one supplier row"
    assert PRODUCT_ROWS, "expected at least one product row"
    mapped = {int(prod_idx) for prod_idx, _ in SUPPLIER_PRODUCT_MAP}
    assert mapped == set(range(len(PRODUCT_ROWS))), (
        "every product must be mapped to a supplier (SKY-86)"
    )
    max_supplier_idx = max(int(sup_idx) for _, sup_idx in SUPPLIER_PRODUCT_MAP)
    assert max_supplier_idx < len(SUPPLIER_ROWS), "product map references an unknown supplier"


def test_supplier_performance_rows_are_well_formed() -> None:
    assert SUPPLIER_PERFORMANCE_ROWS, "expected at least one performance row"
    for row in SUPPLIER_PERFORMANCE_ROWS:
        assert int(str(row["start_days"])) >= int(str(row["end_days"])), (
            f"period end (end_days) must not predate start (start_days): {row}"
        )
        for key in ("on_time", "defect", "stability"):
            assert 0 <= Decimal(str(row[key])) <= 100, f"{key} out of 0-100 range: {row}"
        assert Decimal(str(row["resp"])) >= 0, f"negative responsiveness: {row}"
        assert int(str(row["sup"])) < len(SUPPLIER_ROWS), (
            f"performance row references unknown supplier: {row}"
        )
