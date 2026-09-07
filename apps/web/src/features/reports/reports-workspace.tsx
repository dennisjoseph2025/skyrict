"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { BarChart3, ChevronRight, Search, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/dashboard/erp/empty-state";
import { ErrorState } from "@/components/dashboard/erp/error-state";
import { RequirePermission } from "@/components/dashboard/shared/require-permission";
import { Input } from "@/components/ui/input";
import { ListSkeleton } from "@/components/ui/page-skeletons";
import {
  REPORT_MODULES,
  REPORT_MODULE_LABELS,
  listReportsWithProvenance,
  normalizeModule,
  type ReportDefinition,
  type ReportModule,
} from "@/lib/api/reports-api";
import { ApiError } from "@/lib/api/http";
import { cn } from "@/lib/utils";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; reports: ReportDefinition[]; mockFallback: boolean };

function groupReports(reports: ReportDefinition[]): [ReportModule, ReportDefinition[]][] {
  const grouped = new Map<ReportModule, ReportDefinition[]>();
  for (const report of reports) {
    const moduleKey = normalizeModule(report.module);
    const bucket = grouped.get(moduleKey) ?? [];
    bucket.push(report);
    grouped.set(moduleKey, bucket);
  }
  const ordered: [ReportModule, ReportDefinition[]][] = [];
  for (const moduleKey of REPORT_MODULES) {
    const bucket = grouped.get(moduleKey);
    if (bucket && bucket.length > 0) ordered.push([moduleKey, bucket]);
  }
  const other = grouped.get("other");
  if (other && other.length > 0) ordered.push(["other", other]);
  return ordered;
}

export function ReportsWorkspace() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const { reports, mockFallback } = await listReportsWithProvenance();
      setState({ status: "ready", reports, mockFallback });
    } catch (error) {
      setState({
        status: "error",
        message:
          error instanceof ApiError ? error.message : "Could not load reports.",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
    if (state.status !== "ready") return [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return groupReports(state.reports);
    const filtered = state.reports.filter((report) => {
      const haystack = [report.title, report.description ?? "", report.module, ...report.params]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalized);
    });
    return groupReports(filtered);
  }, [state, query]);

  if (state.status === "loading") {
    return (
      <div className="space-y-6">
        <ListSkeleton rows={4} />
      </div>
    );
  }

  if (state.status === "error") {
    return <ErrorState message={state.message} onRetry={() => void load()} />;
  }

  const totalMatches = groups.reduce((sum, [, reports]) => sum + reports.length, 0);

  return (
    <RequirePermission permission="erp.reports.read">
      <div className="space-y-6">
        {state.mockFallback ? (
          <div
            role="status"
            className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
          >
            <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <p>
              Live report data is currently unavailable — showing sample
              definitions so the workspace stays navigable. Re-run when the
              reporting service is back.
            </p>
          </div>
        ) : null}

        <div className="relative">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search reports…"
            aria-label="Search reports"
            className="pl-8"
          />
        </div>

        {totalMatches === 0 ? (
          <EmptyState
            icon={BarChart3}
            title={query.trim() ? "No matching reports" : "No reports yet"}
            description={
              query.trim()
                ? "Try a different search term — nothing matches your current filter."
                : "Reports will appear here once the reporting service seeds your tenant."
            }
          />
        ) : (
          <div className="space-y-8">
            {groups.map(([module, reports]) => (
              <section key={module} aria-labelledby={`reports-${module}`}>
                <div className="mb-3 flex items-center gap-2">
                  <h2
                    id={`reports-${module}`}
                    className="font-display text-sm font-semibold tracking-wide text-muted-foreground uppercase"
                  >
                    {REPORT_MODULE_LABELS[module]}
                  </h2>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {reports.length}
                  </span>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {reports.map((report) => (
                    <Link
                      key={report.id}
                      href={`/dashboard/erp/reports/${report.slug}`}
                      className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:border-ring/70 hover:bg-muted/40"
                    >
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <BarChart3 aria-hidden="true" className="size-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate font-display text-sm font-semibold text-foreground">
                          {report.title}
                        </h3>
                        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                          {report.description ?? "No description"}
                        </p>
                        <div className="mt-2 flex items-center gap-2">
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-[0.7rem] font-medium",
                              "bg-muted text-muted-foreground",
                            )}
                          >
                            {REPORT_MODULE_LABELS[normalizeModule(report.module)]}
                          </span>
                          <span className="text-[0.7rem] text-muted-foreground">
                            {report.params.length > 0
                              ? `${report.params.length} ${report.params.length === 1 ? "parameter" : "parameters"}`
                              : "No parameters"}
                          </span>
                        </div>
                      </div>
                      <ChevronRight
                        aria-hidden="true"
                        className="mt-3 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
                      />
                    </Link>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </RequirePermission>
  );
}