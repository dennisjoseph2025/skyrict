"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Search, TrendingDown } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { FilterChipGroup } from "@/components/dashboard/shared/filter-chip-group";
import { RiskMeter } from "@/components/dashboard/shared/risk-meter";
import { StatCard } from "@/components/dashboard/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  acknowledgeAttrition,
  getAttrition,
  type HrAttritionFactor,
  type HrAttritionSummary,
  type HrAttritionView,
  type HrDepartmentRisk,
  type HrEmployeeRisk,
} from "@/lib/api/hr-api";
import { ApiError } from "@/lib/api/http";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const BAND_STYLES: Record<string, string> = {
  high: "bg-destructive/10 text-destructive ring-1 ring-destructive/30",
  medium: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-400",
  low: "bg-sky-500/15 text-sky-700 ring-1 ring-sky-500/30 dark:text-sky-400",
};

const BAND_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

type BandFilter = "all" | "high" | "medium" | "low";

function BandBadge({ band }: { band: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("capitalize", BAND_STYLES[band] ?? "bg-muted text-muted-foreground")}
    >
      {BAND_LABEL[band] ?? band}
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

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function signed(value: number): string {
  const formatted = value.toFixed(2);
  return value > 0 ? `+${formatted}` : formatted;
}

function departmentRisk(employees: HrEmployeeRisk[]): HrDepartmentRisk[] {
  const byDept = new Map<string, HrEmployeeRisk[]>();
  for (const employee of employees) {
    const name = employee.departmentName ?? "Unassigned";
    byDept.set(name, [...(byDept.get(name) ?? []), employee]);
  }
  return [...byDept.entries()]
    .map(([name, rows]) => ({
      departmentName: name,
      highRiskCount: rows.filter((row) => row.riskBand === "high").length,
      totalScores: rows.length,
      averageRisk: rows.length
        ? Number((rows.reduce((sum, row) => sum + row.score, 0) / rows.length).toFixed(4))
        : 0,
    }))
    .sort(
      (a, b) => b.highRiskCount - a.highRiskCount || b.averageRisk - a.averageRisk,
    );
}

/** A signed contribution bar: pushes risk up (right, red) or down (left, green). */
function FactorBar({ factor, maxAbs }: { factor: HrAttritionFactor; maxAbs: number }) {
  const positive = factor.contribution > 0;
  const width = maxAbs > 0 ? Math.min(Math.abs(factor.contribution) / maxAbs, 1) * 50 : 0;
  return (
    <li className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="w-32 shrink-0 truncate">{factor.feature.replaceAll("_", " ")}</span>
      <span className="relative h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <span className="absolute top-0 bottom-0 left-1/2 w-px bg-border" />
        {width > 0 ? (
          <span
            className={cn(
              "absolute top-0 bottom-0 rounded-full",
              positive ? "right-1/2 bg-destructive/70" : "left-1/2 bg-emerald-500",
            )}
            style={{ width: `${width}%` }}
          />
        ) : null}
      </span>
      <span
        className={cn(
          "w-11 shrink-0 text-right font-medium tabular-nums",
          positive ? "text-destructive" : "text-emerald-600 dark:text-emerald-400",
        )}
      >
        {signed(factor.contribution)}
      </span>
    </li>
  );
}

function SummaryCards({
  summary,
  narrative,
}: {
  summary: HrAttritionSummary;
  narrative?: string;
}) {
  const maxHigh = Math.max(1, ...summary.topRiskDepartments.map((dept) => dept.highRiskCount));
  return (
    <section aria-label="Attrition summary" className="space-y-4">
      <div className="flex items-center gap-2">
        <L1Badge />
        <p className="text-xs text-muted-foreground">Aggregated counts only — no per-person data.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={TrendingDown}
          label="High risk"
          value={String(summary.highRiskCount)}
          hint="Likely to leave"
          tone="destructive"
        />
        <StatCard
          icon={TrendingDown}
          label="Medium risk"
          value={String(summary.mediumRiskCount)}
          hint="Worth watching"
          tone="warning"
        />
        <StatCard
          icon={TrendingDown}
          label="Low risk"
          value={String(summary.lowRiskCount)}
          hint="Stable"
          tone="info"
        />
      </div>
      {summary.topRiskDepartments.length > 0 ? (
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            Top-risk departments
          </p>
          <ul className="mt-3 space-y-2">
            {summary.topRiskDepartments.map((dept) => (
              <li key={dept.departmentName} className="flex items-center gap-2 text-sm">
                <span className="w-40 shrink-0 truncate text-muted-foreground">
                  {dept.departmentName}
                </span>
                <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <span
                    className="absolute inset-y-0 left-0 rounded-full bg-destructive/70"
                    style={{ width: `${(dept.highRiskCount / maxHigh) * 100}%` }}
                  />
                </span>
                <span className="w-24 shrink-0 text-right tabular-nums text-muted-foreground">
                  {dept.highRiskCount}/{dept.totalScores} high · avg{" "}
                  <span className="font-medium text-foreground">{percent(dept.averageRisk)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {narrative || summary.generatedAt ? (
        <div className="rounded-xl border border-border bg-card p-5">
          {narrative ? <p className="text-sm text-muted-foreground">{narrative}</p> : null}
          {summary.generatedAt ? (
            <p className="mt-2 text-xs text-muted-foreground">As of {formatDateTime(summary.generatedAt)}</p>
          ) : null}
          {summary.modelVersion ? (
            <p className="mt-1 text-xs text-muted-foreground">Model {summary.modelVersion}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

type Column = "band" | "employee" | "probability" | "factors" | "status";

function EmployeeTable({
  employees,
  onAcknowledge,
  ackState,
}: {
  employees: HrEmployeeRisk[];
  onAcknowledge: (employeeId: string) => void;
  ackState: Record<string, { busy?: boolean; error?: string }>;
}) {
  if (employees.length === 0) {
    return (
      <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        No attrition scores yet — the model has not scored any employee.
      </p>
    );
  }
  const columns: Column[] = ["employee", "band", "probability", "factors", "status"];
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
            {columns.map((column) => (
              <th key={column} className="px-4 py-3 font-medium">
                {column === "employee" ? "Employee" : column === "band" ? "Risk" : column === "probability" ? "Probability" : column === "factors" ? "Top factors" : "Status"}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {employees.map((employee) => {
            const state = ackState[employee.employeeId];
            const maxAbs = Math.max(
              1,
              ...employee.factors.map((factor) => Math.abs(factor.contribution)),
            );
            return (
              <tr key={employee.employeeId}>
                <td className="px-4 py-3">
                  <p className="font-medium text-foreground">{employee.name ?? "Unnamed employee"}</p>
                  <p className="text-xs text-muted-foreground">
                    {employee.employeeNumber ?? ""}
                    {employee.employeeNumber && employee.departmentName ? " · " : ""}
                    {employee.departmentName ?? ""}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <BandBadge band={employee.riskBand} />
                </td>
                <td className="px-4 py-3">
                  <RiskMeter value={employee.score} className="max-w-36" />
                  <p className="mt-1 text-xs text-muted-foreground">
                    confidence {percent(employee.confidence)}
                  </p>
                </td>
                <td className="px-4 py-3">
                  {employee.factors.length > 0 ? (
                    <ul className="space-y-1">
                      {employee.factors.map((factor) => (
                        <FactorBar key={factor.feature} factor={factor} maxAbs={maxAbs} />
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">No factors reported</p>
                  )}
                </td>
                <td className="px-4 py-3">
                  {employee.acknowledged ? (
                    <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 aria-hidden="true" className="size-4" />
                      <span>
                        Acknowledged{employee.acknowledgedAt ? ` ${formatDateTime(employee.acknowledgedAt)}` : ""}
                      </span>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={state?.busy}
                        onClick={() => onAcknowledge(employee.employeeId)}
                      >
                        {state?.busy ? "Acknowledging…" : "Acknowledge"}
                      </Button>
                      {state?.error ? (
                        <p className="max-w-56 text-xs font-medium text-destructive">{state.error}</p>
                      ) : null}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function AttritionClient() {
  const [view, setView] = useState<
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "summary"; summary: HrAttritionSummary }
    | { state: "detail"; generatedAt: string; modelVersion: string; employees: HrEmployeeRisk[] }
  >({ state: "loading" });
  const [ackState, setAckState] = useState<Record<string, { busy?: boolean; error?: string }>>({});
  const [bandFilter, setBandFilter] = useState<BandFilter>("all");
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setView({ state: "loading" });
    try {
      const result: HrAttritionView = await getAttrition();
      if (result.mode === "summary") {
        setView({ state: "summary", summary: result.summary });
      } else {
        setView({
          state: "detail",
          generatedAt: result.generatedAt,
          modelVersion: result.modelVersion,
          employees: result.employees,
        });
      }
    } catch (error) {
      setView({
        state: "error",
        message: error instanceof ApiError ? error.message : "Could not load attrition risk.",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAcknowledge = useCallback((employeeId: string) => {
    setAckState((current) => ({ ...current, [employeeId]: { busy: true, error: undefined } }));
    acknowledgeAttrition(employeeId)
      .then(() => {
        setView((current) =>
          current.state === "detail"
            ? {
                ...current,
                employees: current.employees.map((employee) =>
                  employee.employeeId === employeeId
                    ? { ...employee, acknowledged: true, acknowledgedAt: new Date().toISOString() }
                    : employee,
                ),
              }
            : current,
        );
        setAckState((current) => ({ ...current, [employeeId]: { busy: false } }));
      })
      .catch((error) => {
        setAckState((current) => ({
          ...current,
          [employeeId]: {
            busy: false,
            error:
              error instanceof ApiError && error.status === 403
                ? "Acknowledgement needs the erp.hr.ai.acknowledge permission."
                : error instanceof ApiError
                  ? error.message
                  : "Could not acknowledge this employee.",
          },
        }));
      });
  }, []);

  const detailSummary: HrAttritionSummary | null =
    view.state === "detail"
      ? {
          generatedAt: view.generatedAt,
          modelVersion: view.modelVersion,
          highRiskCount: view.employees.filter((employee) => employee.riskBand === "high").length,
          mediumRiskCount: view.employees.filter((employee) => employee.riskBand === "medium").length,
          lowRiskCount: view.employees.filter((employee) => employee.riskBand === "low").length,
          topRiskDepartments: departmentRisk(view.employees),
          narrative: "",
        }
      : null;

  const visibleEmployees = useMemo(() => {
    if (view.state !== "detail") return [];
    const needle = query.trim().toLowerCase();
    return [...view.employees]
      .filter((employee) => {
        if (bandFilter !== "all" && employee.riskBand !== bandFilter) return false;
        if (!needle) return true;
        const haystack = `${employee.name ?? ""} ${employee.employeeNumber ?? ""} ${employee.departmentName ?? ""}`.toLowerCase();
        return haystack.includes(needle);
      })
      .sort((a, b) => b.score - a.score);
  }, [view, bandFilter, query]);

  const bandOptions = useMemo(() => {
    if (view.state !== "detail") return [{ value: "all", label: "All bands" }];
    const count = (band: "high" | "medium" | "low") =>
      view.employees.filter((employee) => employee.riskBand === band).length;
    return [
      { value: "all", label: `All · ${view.employees.length}` },
      { value: "high", label: `High · ${count("high")}` },
      { value: "medium", label: `Medium · ${count("medium")}` },
      { value: "low", label: `Low · ${count("low")}` },
    ];
  }, [view]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attrition risk"
        description="Modelled retention risk per employee, scored on demand against the bundled attrition model."
        icon={TrendingDown}
      />

      {view.state === "error" ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-10 text-center">
          <p className="text-sm font-medium text-destructive">{view.message}</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : null}

      {view.state === "loading" ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl border border-border bg-card" />
            ))}
          </div>
          <div className="h-40 animate-pulse rounded-xl border border-border bg-card" />
        </div>
      ) : null}

      {view.state === "summary" ? (
        <>
          <SummaryCards summary={{ ...view.summary, modelVersion: view.summary.modelVersion }} />
          <section aria-label="Individual scores locked" className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2">
              <L2Badge />
              <p className="text-xs text-muted-foreground">
                Per-employee drill-down needs the erp.hr.ai.individual permission — the aggregate
                overview above is still available.
              </p>
            </div>
          </section>
        </>
      ) : null}

      {view.state === "detail" ? (
        <>
          <SummaryCards
            summary={detailSummary as HrAttritionSummary}
            narrative={detailSummary?.narrative}
          />
          <section aria-label="Per-employee attrition risk" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
                  Per-employee risk
                </h2>
                <L2Badge />
                <p className="ml-auto hidden text-xs text-muted-foreground sm:block">
                  {view.employees.length} scored employee(s)
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search
                  aria-hidden="true"
                  className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  className="pl-8"
                  placeholder="Search by name or department…"
                  aria-label="Search employees"
                />
              </div>
              <FilterChipGroup
                options={bandOptions}
                value={bandFilter}
                onChange={(value) => setBandFilter(value as BandFilter)}
                ariaLabel="Filter by risk band"
              />
            </div>
            <EmployeeTable
              employees={visibleEmployees}
              onAcknowledge={handleAcknowledge}
              ackState={ackState}
            />
          </section>
        </>
      ) : null}
    </div>
  );
}