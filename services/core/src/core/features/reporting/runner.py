"""Pure helpers for rendering report query results (RPT-BE-001).

``json_safe_value`` is the single coercion point between raw database values
and what is stored in ``erp_report_snapshots.payload`` (JSONB) or streamed as
CSV columns. Keeping it here - outside the repository - makes the rules
unit-testable without a database and keeps the repository limited to SQL.

Coercion rules:
- ``Decimal`` amounts become canonical strings via ``format(value, "f")`` so
  money keeps full ``(19,4)`` precision and never suffers float artifacts
  (existing snapshot payloads already carry string numerals, e.g. ``"123.45"``).
- ``date`` / ``datetime`` become ISO-8601 strings.
- ``uuid.UUID`` becomes its canonical hex string.
- Anything else (custom types, bytea, enums) is stringified defensively.

CSV safety (OWASP CSV-injection guidance): cells whose text begins with ``=``,
``+``, ``@`` or a tab are prefixed with a single quote so a spreadsheet never
interprets report output as a formula. Numeric values - including legitimate
negative numbers such as ``-2.3`` - are never altered.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

__all__ = ["csv_buffer", "json_safe_value"]

# Spreadsheet formula sigils that make a CSV cell executable when opened in a
# spreadsheet tool. A leading ``-`` is deliberately NOT escaped: financial
# reports legitimately start cells with a minus sign, and a negative number is
# not a formula vector on its own.
_CSV_FORMULA_PREFIXES = ("=", "+", "@", "\t")


def _csv_safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def csv_buffer(columns: list[str], rows: list[dict[str, Any]]) -> str:
    r"""Serialize report rows into a UTF-8 CSV string.

    Uses the same coerced (\ ``json_safe_value``\ ) row values as the snapshot
    payload path, so an exported value is byte-for-byte what a snapshot would
    hold - except that string cells beginning with a spreadsheet formula sigil
    (``=`` ``+`` ``@`` tab) get a leading ``'`` (OWASP CSV-injection guidance).
    The buffer is built in memory and returned whole so the caller can stream
    it with a known body length.
    """
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=columns,
        extrasaction="ignore",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_safe_cell(json_safe_value(row.get(key))) for key in columns})
    return stream.getvalue()


def json_safe_value(value: Any) -> Any:
    """Coerce one raw row value into a JSON/CSV-safe scalar."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)
