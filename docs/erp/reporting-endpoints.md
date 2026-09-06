# M-RPT - Reporting Endpoints (RPT-BE-001)

> **Status:** Implemented. Target: `services/core`.
> **Owner:** Skyrict engineering (SKY-78 / RPT-BE-001).
> **Spec:** `docs/architecture/erp-phase1.md` §M-RPT.
> **Permission:** `erp.reports.read` for every endpoint on this page.
> **Predecessor:** `docs/erp/reporting-data-layer.md` (RPT-DATA-001) — the tables and
> seed pack this API reads.

This document defines the **run/export chain** on top of the reporting data layer:
listing definitions, parametrized execution, snapshot history, CSV export (audited),
and the background retention job that keeps snapshots bounded.

---

## 1. Overview

The reporting chain has three links:

1. **Data layer** (RPT-DATA-001) — `erp_report_definitions` + `erp_report_snapshots`,
   the seed pack, the read-only SQL validator.
2. **Run/export chain** (this ticket) — the API that turns a definition into rows and
   rows into snapshots/CSV, plus the retention worker.
3. **Dashboard/agents** (RPT-DASH, phase 2) — the UI and question-answering consumers.

One idea to internalize: **the endpoint layer never accepts SQL or a tenant id — only a
slug and whitelisted parameter values.** The definition is resolved server-side from the
authenticated tenant; every param is type-checked against the definition's whitelist
before any SQL executes (unknown/`tenant_id`-mismatched/invalid-format → 422).

---

## 2. Endpoints

All routes are served under `/api/v1/reports` in `services/core` (router:
`core.features.reporting.reports_router`). `module`-filtering and pagination use query
params; parametrized runs use a JSON body.

### 2.1 `GET /api/v1/reports` — list definitions

Returns the tenant's active definitions, optionally filtered by `?module=finance`.

```json
{
  "success": true,
  "data": [
    {
      "id": "…",
      "slug": "ar_aging",
      "title": "AR Aging",
      "module": "finance",
      "description": "Aged receivables by bucket as of a date",
      "params": ["tenant_id", "as_of_date"],
      "permission_key": "erp.reports.read",
      "version": 1,
      "updated_at": "2026-09-05T09:00:00+00:00"
    }
  ],
  "message": "1 reports"
}
```

- `params` is the **build contract for the UI**: it tells the client exactly which fields
  a run request may (and must) supply.

### 2.2 `GET /api/v1/reports/{slug}` — definition metadata

One definition (404 when the slug is unknown to the tenant). Same shape as one list item.

### 2.3 `POST /api/v1/reports/{slug}/run` — parametrize, execute, snapshot

Body: `{"params": {"as_of_date": "2026-09-30"}}`. The JSON doc before execution:

1. **Resolve** the active definition (404 first).
2. **Type the params** — `tenant_id` must equal the session tenant or the run is 422'd
   (it is *never* trusted from the client); `*_date` / `from_date` / `to_date` /
   `as_of_date` must be ISO `YYYY-MM-DD`; unknown params → 422. This happens **before**
   any SQL executes.
3. **Execute** the definition SQL with a per-query statement timeout (config:
   `REPORTING_QUERY_TIMEOUT_SECONDS`, default 30s) and the `TenantContext` RLS bound.
4. **Cap** the result for the UI (config: `REPORTING_RESULT_CAP`, default 10,000;
   `truncated: true` when the cap applied).
5. **Store/refresh** the `(definition, period)` snapshot idempotently. `period` is
   `as_of_date` → `from_date` → UTC today (in that precedence).

Response — `ReportRunResult`:

```json
{
  "success": true,
  "data": {
    "columns": ["bucket", "total"],
    "rows": [{"bucket": "current", "total": "150.00"}],
    "truncated": false,
    "period": "2026-09-30",
    "snapshot_id": "…",
    "generated_at": "2026-09-05T09:00:00+00:00"
  }
}
```

### 2.4 `GET /api/v1/reports/{slug}/snapshots` — stored history

Newest-first list of stored snapshots for the definition (404 for an unknown slug).
`?limit=` (default 20, max 100) controls how many are returned.

```json
{
  "success": true,
  "data": [
    {
      "id": "…",
      "definition_id": "…",
      "period": "2026-09-30",
      "generated_at": "2026-09-05T09:00:00+00:00"
    }
  ],
  "message": "1 snapshots"
}
```

### 2.5 `POST /api/v1/reports/{slug}/export` — streamed, audited CSV

Same body shape as `/run`, but the response is the **full** result set (the UI cap is
never applied) streamed as `text/csv; charset=utf-8` with
`Content-Disposition: attachment; filename="{slug}-{period}.csv"` and
`X-Report-Rows` / `X-Report-Period` headers. Columns/values are serialized with the same
coercion as snapshot payloads, so **an export row matches the API row byte-for-byte**.

**Audit:** an immutable `report.exported` event is written (via
`core.core.audit_service.AuditService`, actor + IP + user-agent + row/byte counts)
**before** the stream starts — an export is on record even if the client disconnects
mid-download.

---

## 3. Param typing (the 422 contract)

`core.features.reporting.params.build_report_binds(declared, raw_params, tenant_id)`
types every value against the definition's whitelist:

| Declared param | Acceptance | Bind value |
|---|---|---|
| `tenant_id` | must equal the session tenant | session tenant UUID (client value ignored/rejected) |
| `*_date`, `from_date`, `to_date`, `as_of_date` | ISO `YYYY-MM-DD` | `date` |
| anything else (e.g. `status`) | string ≤ 255 chars | string |
| undeclared name | rejected | — |

All of this runs before SQL; a 422 means "your params could not be typed", never "the
query failed". The `period` for snapshotting is resolved separately (`resolve_period`).

---

## 4. Retention — newest N per definition

Snapshots are bounded by a **per-definition** limit (default 20, config
`REPORTING_RETENTION_LIMIT`), enforced two ways:

- `core.features.reporting.retention_worker.SnapshotRetentionWorker` — an asyncio loop
  (mirroring the payroll automation worker) that walks every tenant's definitions once
  per `REPORTING_RETENTION_POLL_SECONDS` (default 3600s, config
  `REPORTING_RETENTION_ENABLED` gates it) and deletes everything older than the newest
  `keep_n` by `generated_at`.
- `uv run --directory services/core core retention run` — the same prune as a one-shot
  CLI (used for ops/manual cleanups and smoke tests).

`prune_snapshots` issues `DELETE ... WHERE id NOT IN (SELECT id … ORDER BY generated_at
DESC LIMIT n)` per definition inside the tenant's transaction — RLS keeps every delete
tenant-scoped. Retention is per-definition on purpose: a 30-period AR report never
crowds out a weekly headcount report.

---

## 5. Config

All settings in `core.core.config`, section `REPORTING_*`:

| Setting | Default | Meaning |
|---|---|---|
| `REPORTING_QUERY_TIMEOUT_SECONDS` | 30 | `statement_timeout` for a definition run |
| `REPORTING_RESULT_CAP` | 10,000 | UI row cap (`/run`); export ignores it |
| `REPORTING_RETENTION_ENABLED` | `true` | Start the retention worker on boot |
| `REPORTING_RETENTION_LIMIT` | 20 | Newest N snapshots kept per definition |
| `REPORTING_RETENTION_POLL_SECONDS` | 3600 | Retention sweep interval |

---

## 6. Web BFF (RPT-BE-001, frontend half)

`apps/web` exposes the same contract to the browser via
`/api/v1/reports/**` (`apps/web/src/app/api/v1/reports/[...path]/route.ts`), which:

- forwards every path/query/body to the Core service with the tenant slug resolved
  server-side and the client's Bearer token forwarded;
- applies the same same-origin CSRF gate as the other BFF segments on state-changing
  methods;
- when **Core is unreachable**, a `GET` of the bare list falls back to the sample
  `reportsKpis` payload (`X-Mock-Fallback: true`) so the ERP reports widget still
  renders in local dev; every other reports call returns the standard 502.

`/api/v1/reports` was added to the catch-all's Core-service allowlist in
`apps/web/src/app/api/v1/[...path]/route.ts` as well, keeping the fallback segment
explicit and the generic proxy consistent with every other ERP segment.

---

## 7. Security

- **Tenant boundary**: `tenant_id` is always bound from the session; the client-supplied
  value is rejected (422). RLS (`tenant_isolation_erp_report_*`) remains the backstop —
  a definition can only ever read rows in `current_tenant_id()`.
- **No client SQL**: the slug resolves to a server-authored definition; the only client
  inputs are whitelisted parameter values, typed before execution.
- **No secret/PII leakage**: run/export return only the definition's declared columns;
  error responses are sanitized (no SQL text echoed).
- **CSV-formula safe**: cells whose text begins with `=`, `+`, `@` or a tab are prefixed
  with a single quote (OWASP CSV-injection guidance) — negative numbers are never
  altered, so financial deltas export unchanged.
- **Audited export**: `report.exported` is immutable (hash-chained, append-only) and
  written before streaming.

## 8. Acceptance criteria (from erp-phase1.md §M-RPT)

- ✅ Every report returns the tenant's data only — RLS integration tests.
- ✅ Snapshot refresh idempotent per `(definition, period)` — unique constraint.
- ✅ Exports match the API payload row-for-row — shared `json_safe_value` coercion +
  `csv_buffer`; verified row-for-row in runner/export tests.