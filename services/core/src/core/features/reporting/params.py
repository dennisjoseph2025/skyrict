"""Report parameter validation - typed bind values from user-supplied params.

Phase-1 report definitions (RPT-DATA-001 seeds) declare exactly two kinds of
parameter, and the runner types them by a documented convention
(``docs/erp/reporting-endpoints.md`` §params):

- ``tenant_id``: server-managed. When the caller supplies it, it MUST match the
  session tenant or the request fails with 422; the runner always binds the
  caller's real tenant from the request context.
- ``from_date`` / ``to_date`` / ``as_of_date`` (and any ``*_date`` name): an
  ISO-8601 ``YYYY-MM-DD`` date bound as a ``datetime.date``.

Validation fails CLOSED before any SQL executes: an undeclared parameter, a
missing required parameter, an unconvertible date, or a tenant mismatch all
raise :class:`skyrict_common.exceptions.ValidationError` (RFC 7807, 422) so
injection-shaped payloads (e.g. ``as_of_date="2026-01-01'; DROP TABLE ..."``)
are rejected at the boundary, never interpolated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from skyrict_common.exceptions import ValidationError

__all__ = ["build_report_binds", "resolve_period"]

_DATE_SUFFIX = "_date"
_DATE_NAMES = {"from_date", "to_date", "as_of_date"}


def _is_date_param(name: str) -> bool:
    return name in _DATE_NAMES or name.endswith(_DATE_SUFFIX)


def _parse_date(name: str, value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValidationError(f"Invalid value for report parameter {name!r}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(
            f"Invalid date for report parameter {name!r}: {value!r}; expected YYYY-MM-DD"
        ) from None


def build_report_binds(
    *,
    declared: tuple[str, ...],
    raw_params: dict[str, Any],
    tenant_id: uuid.UUID,
) -> dict[str, Any]:
    """Coerce the request's ``params`` into typed bind values for the report SQL.

    Args:
        declared: Names the definition's SQL may bind (``definition.params``).
        raw_params: User-supplied values from the request body.
        tenant_id: The authenticated caller's tenant (server-authoritative).

    Returns:
        A ``dict`` of ``:name`` -> bind value. ``tenant_id`` is always present
        and always equals ``tenant_id``; date params are ``datetime.date``
        objects safe for parameterized SQL.

    Raises:
        ValidationError: On unknown params, missing required params, a
            mismatched ``tenant_id``, or an unconvertible date value.
    """
    declared_set = set(declared)
    for name in raw_params:
        if name not in declared_set:
            raise ValidationError(f"Unknown report parameter: {name!r}")

    try:
        tenant_param = raw_params["tenant_id"]
    except KeyError:
        tenant_param = None
    if tenant_param is not None:
        try:
            supplied = uuid.UUID(str(tenant_param))
        except (ValueError, TypeError):
            raise ValidationError(
                "Invalid value for report parameter 'tenant_id': expected a UUID"
            ) from None
        if supplied != tenant_id:
            raise ValidationError(
                "report parameter 'tenant_id' must match the authenticated tenant"
            )

    binds: dict[str, Any] = {"tenant_id": tenant_id}
    for name in declared:
        if name == "tenant_id":
            continue
        if name not in raw_params:
            raise ValidationError(f"Missing required report parameter: {name!r}")
        if _is_date_param(name):
            binds[name] = _parse_date(name, raw_params[name])
        else:
            raise ValidationError(
                f"Unsupported report parameter type for {name!r}: "
                "Phase-1 parameters are tenant_id and ISO dates only"
            )
    return binds


def resolve_period(
    raw_params: dict[str, Any],
    *,
    today: date | None = None,
) -> date:
    """The snapshot period for a run - ``as_of_date`` -> ``from_date`` -> today.

    A snapshot is uniquely keyed by ``(definition, period)``; picking the period
    deterministically lets a re-run with the same as-of date refresh the same
    row (idempotent snapshot, erp-phase1.md §M-RPT).
    """
    for name in ("as_of_date", "from_date"):
        value = raw_params.get(name)
        if value is not None:
            return _parse_date(name, value)
    return today or datetime.now(UTC).date()
