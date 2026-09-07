"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, CalendarClock, ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { FilterChipGroup } from "@/components/dashboard/shared/filter-chip-group";
import { SearchableSelect, type SearchableSelectOption } from "@/components/dashboard/shared/searchable-select";
import { StatCard } from "@/components/dashboard/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getAnomalySummary,
  getEmployeeAnomalies,
  getEmployeeUtilization,
  getUtilizationSummary,
  listEmployees,
  type Employee,
  type HrAnomalyOrg,
  type HrLeaveAnomaly,
  type HrUtilizationAlert,
  type HrUtilizationOrg,
} from "@/lib/api/hr-api";
import { ApiError } from "@/lib/api/http";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "utilization" | "anomaly";

const SEVERITY_STYLES: Record<string, string> = {
  high: "bg-destructive/10 text-destructive ring-1 ring-destructive/30",
  medium: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-400",
  low: "bg-sky-500/15 text-sky-700 ring-1 ring-sky-500/30 dark:text-sky-400",
};

const SEVERITY_BAR: Record<string, string> = {
  high: "bg-destructive",
  medium: "bg-amber-500",
  low: "bg-sky-500",
};

const SEVERITY_ORDER = ["high", "medium", "low"] as const;

const SEVERITY_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

function humanize(code: string): string {
  return code.replaceAll("_", " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("capitalize", SEVERITY_STYLES[severity] ?? "bg-muted text-muted-foreground")}
    >
      {SEVERITY_LABEL[severity] ?? humanize(severity)}
    </Badge>
  );
}

function L1Badge() {
  return (
    <Badge
      variant="outline"
      className="border-indigo-500/30 bg-indigo-500/10 text-indigo-700 dark:text-indigo-400"
    >
      L1 aggregate
    </Badge>
  );
}

function L2Badge() {
  return (
    <Badge
      variant="outline"
      className="border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-400"
    >
      L2 individual
    </Badge>
  );
}

function CountBar({
  label,
  count,
  max,
  barClass,
}: {
  label: string;
  count: number;
  max: number;
  barClass: string;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-24 shrink-0 truncate text-muted-foreground">{label}</span>
      <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full", barClass)}
          style={{ width: `${max > 0 ? (count / max) * 100 : 0}%` }}
        />
      </span>
      <span className="w-6 shrink-0 text-right font-medium tabular-nums text-foreground">
        {count}
      </span>
    </div>
  );
}

function SummaryCards({
  total,
  byType,
  bySeverity,
  generatedAt,
  narrative,
}: {
  total: number;
  byType: Record<string, number>;
  bySeverity: Record<string, number>;
  generatedAt: string;
  narrative: string;
}) {
  const typeEntries = Object.entries(byType).sort((a, b) => b[1] - a[1]);
  const severityEntries = SEVERITY_ORDER.map((severity) => [severity, bySeverity[severity] ?? 0] as const);
  const typeMax = Math.max(1, ...typeEntries.map(([, count]) => count));
  const severityMax = Math.max(1, ...severityEntries.map(([, count]) => count));

  return (
    <section aria-label="Alert summary" className="space-y-4">
      <div className="flex items-center gap-2">
        <L1Badge />
        <p className="text-xs text-muted-foreground">Aggregated counts only — no per-person data.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          icon={ShieldAlert}
          label="Total alerts"
          value={String(total)}
          hint={typeEntries.length > 0 ? `${typeEntries[0][0]} is the most common` : ""}
          tone={total > 0 ? "warning" : "success"}
        />
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            By severity
          </p>
          <div className="mt-3 space-y-2">
            {severityEntries.length > 0 ? (
              severityEntries.map(([severity, count]) => (
                <CountBar
                  key={severity}
                  label={SEVERITY_LABEL[severity] ?? humanize(severity)}
                  count={count}
                  max={severityMax}
                  barClass={SEVERITY_BAR[severity] ?? "bg-muted"}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">None</p>
            )}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            By type
          </p>
          <div className="mt-3 space-y-2">
            {typeEntries.length > 0 ? (
              typeEntries.map(([type, count]) => (
                <CountBar key={type} label={humanize(type)} count={count} max={typeMax} barClass="bg-primary/70" />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">None</p>
            )}
          </div>
        </div>
      </div>
      {narrative ? (
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-sm text-muted-foreground">{narrative}</p>
          {generatedAt ? (
            <p className="mt-2 text-xs text-muted-foreground">As of {formatDateTime(generatedAt)}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

type DetailState =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "blocked"; message: string }
  | { state: "error"; message: string }
  | { state: "ready"; rows: HrUtilizationAlert[] | HrLeaveAnomaly[] };

type SeverityFilter = "all" | "high" | "medium" | "low";

export function AiAlertsClient() {
  const [tab, setTab] = useState<Tab>("utilization");
  const [summary, setSummary] = useState<{ util: HrUtilizationOrg | null; anomaly: HrAnomalyOrg | null } | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [detail, setDetail] = useState<Record<Tab, DetailState>>({
    utilization: { state: "idle" },
    anomaly: { state: "idle" },
  });

  const loadSummary = useCallback(async () => {
    setSummaryError(null);
    const [util, anomaly] = await Promise.allSettled([getUtilizationSummary(), getAnomalySummary()]);
    if (util.status === "rejected" && anomaly.status === "rejected") {
      const error = util.reason;
      setSummaryError(
        error instanceof ApiError ? error.message : "Could not load HR AI alerts.",
      );
      return;
    }
    setSummary({
      util: util.status === "fulfilled" ? util.value : null,
      anomaly: anomaly.status === "fulfilled" ? anomaly.value : null,
    });
  }, []);

  const loadEmployees = useCallback(async () => {
    try {
      const result = await listEmployees({ pageSize: 200, filters: { status: "active" } });
      setEmployees(result.items);
    } catch {
      setEmployees((current) => current);
    }
  }, []);

  useEffect(() => {
    void loadSummary();
    void loadEmployees();
  }, [loadSummary, loadEmployees]);

  const loadDetail = useCallback(
    async (nextTab: Tab, employeeId: string) => {
      setDetail((current) => ({ ...current, [nextTab]: { state: "loading" } }));
      try {
        const rows =
          nextTab === "utilization"
            ? await getEmployeeUtilization(employeeId)
            : await getEmployeeAnomalies(employeeId);
        setDetail((current) => ({ ...current, [nextTab]: { state: "ready", rows } }));
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          setDetail((current) => ({
            ...current,
            [nextTab]: {
              state: "blocked",
              message:
                "Per-employee alerts need the erp.hr.ai.individual permission — the aggregate overview above is still available.",
            },
          }));
        } else {
          setDetail((current) => ({
            ...current,
            [nextTab]: {
              state: "error",
              message: error instanceof ApiError ? error.message : "Could not load employee alerts.",
            },
          }));
        }
      }
    },
    [],
  );

  const handleSelect = useCallback(
    (employeeId: string) => {
      setSelectedId(employeeId);
      if (employeeId) void loadDetail(tab, employeeId);
    },
    [loadDetail, tab],
  );

  const handleTab = useCallback(
    (nextTab: Tab) => {
      setTab(nextTab);
      if (selectedId && detail[nextTab].state === "idle") {
        void loadDetail(nextTab, selectedId);
      }
    },
    [detail, loadDetail, selectedId],
  );

  const currentSummary = tab === "utilization" ? summary?.util : summary?.anomaly;

  const employeeOptions = useMemo<SearchableSelectOption[]>(
    () =>
      employees.map((employee) => ({
        value: employee.id,
        label: `${employee.firstName} ${employee.lastName}`,
        keywords: employee.employeeNumber ?? undefined,
      })),
    [employees],
  );

  const severityOptions = useMemo<{ value: string; label: string }[]>(
    () => [
      { value: "all", label: "All" },
      { value: "high", label: "High" },
      { value: "medium", label: "Medium" },
      { value: "low", label: "Low" },
    ],
    [],
  );

  const currentDetail = detail[tab];
  const visibleRows = useMemo(() => {
    if (currentDetail.state !== "ready") return [];
    const rows = currentDetail.rows;
    const severityRank = (severity: string) => {
      const index = SEVERITY_ORDER.indexOf(severity as (typeof SEVERITY_ORDER)[number]);
      return index === -1 ? SEVERITY_ORDER.length : index;
    };
    const filtered =
      severityFilter === "all"
        ? rows
        : rows.filter((row) => row.severity === severityFilter);
    return [...filtered].sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  }, [currentDetail, severityFilter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI alerts"
        description="Leave-balance utilization risks and leave-pattern anomalies detected across the team."
        icon={BarChart3}
      />

      <div className="flex items-center gap-1 rounded-xl border border-border bg-card p-1">
        <button
          type="button"
          onClick={() => handleTab("utilization")}
          className={cn(
            "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            tab === "utilization"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          <CalendarClock aria-hidden="true" className="size-4" />
          Utilization
        </button>
        <button
          type="button"
          onClick={() => handleTab("anomaly")}
          className={cn(
            "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            tab === "anomaly"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          <ShieldAlert aria-hidden="true" className="size-4" />
          Leave anomalies
        </button>
      </div>

      {summaryError ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-10 text-center">
          <p className="text-sm font-medium text-destructive">{summaryError}</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => void loadSummary()}>
            Try again
          </Button>
        </div>
      ) : summary && currentSummary ? (
        <>
          <SummaryCards
            total={
              tab === "utilization"
                ? (currentSummary as HrUtilizationOrg).totalAlerts
                : (currentSummary as HrAnomalyOrg).totalAnomalies
            }
            byType={currentSummary.byType}
            bySeverity={currentSummary.bySeverity}
            generatedAt={currentSummary.generatedAt}
            narrative={currentSummary.narrative}
          />

          <section aria-label="Employee alerts" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                  Per-employee alerts
                </h2>
                <L2Badge />
              </div>
              <SearchableSelect
                className="w-full sm:w-64"
                options={employeeOptions}
                value={selectedId || null}
                onValueChange={handleSelect}
                placeholder={`Select an employee (${employees.length} available)`}
              />
            </div>

            {currentDetail.state === "blocked" ? (
              <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                {currentDetail.message}
              </p>
            ) : null}
            {currentDetail.state === "error" ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium text-destructive">
                {currentDetail.message}
              </p>
            ) : null}

            {selectedId && currentDetail.state !== "idle" ? (
              <>
                {currentDetail.state === "ready" && currentDetail.rows.length > 0 ? (
                  <FilterChipGroup
                    options={severityOptions}
                    value={severityFilter}
                    onChange={(value) => setSeverityFilter(value as SeverityFilter)}
                    ariaLabel="Filter by severity"
                  />
                ) : null}
                <div className="overflow-hidden rounded-xl border border-border bg-card">
                  {currentDetail.state === "loading" ? (
                    <div className="space-y-2 p-4">
                      <div className="h-14 animate-pulse rounded-lg bg-muted" />
                      <div className="h-14 animate-pulse rounded-lg bg-muted" />
                    </div>
                  ) : null}
                  {currentDetail.state === "ready" && visibleRows.length === 0 ? (
                    <p className="p-4 text-sm text-muted-foreground">
                      {currentDetail.rows.length === 0
                        ? `No open ${tab === "utilization" ? "utilization alerts" : "leave anomalies"} for this employee.`
                        : "No alerts match the current severity filter."}
                    </p>
                  ) : null}
                  {visibleRows.length > 0 ? (
                    <ul className="divide-y divide-border">
                      {visibleRows.map((row, index) => {
                        const isAlert = tab === "utilization";
                        const alert = row as HrUtilizationAlert;
                        const anomaly = row as HrLeaveAnomaly;
                        return (
                          <li key={`${tab}-${index}`} className="flex items-start justify-between gap-4 p-4">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-sm font-medium text-foreground">
                                  {isAlert ? humanize(alert.alertType) : anomaly.title}
                                </span>
                                <SeverityBadge severity={isAlert ? alert.severity : anomaly.severity} />
                                {isAlert && alert.leaveType ? (
                                  <span className="text-xs text-muted-foreground">
                                    {humanize(alert.leaveType)}
                                  </span>
                                ) : null}
                              </div>
                              <p className="mt-1 text-sm text-muted-foreground">
                                {isAlert
                                  ? `${alert.balanceDays} day(s) balance` +
                                    (alert.projectedForfeitureDays != null
                                      ? `, ${alert.projectedForfeitureDays} projected to forfeit`
                                      : "") +
                                    (alert.daysRemainingInYear != null
                                      ? `, ${alert.daysRemainingInYear} day(s) left in year`
                                      : "")
                                  : anomaly.description}
                              </p>
                              {!isAlert && anomaly.teamSize > 0 ? (
                                <p className="mt-1 text-xs text-muted-foreground">
                                  Team of {anomaly.teamSize}
                                </p>
                              ) : null}
                            </div>
                            <div className="shrink-0 text-right text-xs text-muted-foreground">
                              <p>{row.name}</p>
                              <p>{row.departmentName ?? "Unassigned"}</p>
                              <p>{formatDateTime(row.createdAt)}</p>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </div>
              </>
            ) : currentDetail.state === "idle" ? (
              <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                Pick an employee to see which risks or anomalies apply to them individually.
              </p>
            ) : null}
          </section>
        </>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl border border-border bg-card" />
            ))}
          </div>
          <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
        </div>
      )}
    </div>
  );
}