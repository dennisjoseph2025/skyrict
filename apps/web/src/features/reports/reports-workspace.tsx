"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  ChevronRight,
  Loader2,
  Save,
  Search,
  Send,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { EmptyState } from "@/components/dashboard/erp/empty-state";
import { ErrorState } from "@/components/dashboard/erp/error-state";
import { RequirePermission } from "@/components/dashboard/shared/require-permission";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ListSkeleton } from "@/components/ui/page-skeletons";
import {
  REPORT_MODULES,
  REPORT_MODULE_LABELS,
  generateReport,
  listReportsWithProvenance,
  normalizeModule,
  saveGeneratedReport,
  toReportSlug,
  type GeneratedReportData,
  type ReportDefinition,
  type ReportModule,
} from "@/lib/api/reports-api";
import { ApiError } from "@/lib/api/http";
import { cn } from "@/lib/utils";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; reports: ReportDefinition[]; mockFallback: boolean };

type BuilderState =
  | { status: "idle" }
  | { status: "generating" }
  | { status: "error"; message: string };

/** Example prompts backed verbatim by a seeded, whitelisted template. */
const SUGGESTED_PROMPTS = [
  "AR aging as of last month",
  "Sales orders by day for last quarter",
  "Products below reorder point",
  "Headcount by department",
];

/** Preview caps the generated table; exports/run on the saved report go full-depth. */
const PREVIEW_MAX_ROWS = 25;

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
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const [prompt, setPrompt] = useState("");
  const [builderState, setBuilderState] = useState<BuilderState>({ status: "idle" });
  const [answer, setAnswer] = useState<string | null>(null);
  const [generated, setGenerated] = useState<GeneratedReportData | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const runGenerate = useCallback(async (value: string) => {
    setBuilderState({ status: "generating" });
    setAnswer(null);
    setGenerated(null);
    setSaveState("idle");
    setSaveError(null);
    try {
      const response = await generateReport(value);
      setAnswer(response.answer);
      setGenerated(response.data);
      setBuilderState({ status: "idle" });
    } catch (error) {
      setBuilderState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not generate the report.",
      });
    }
  }, []);

  const handleGenerate = useCallback(() => {
    const value = prompt.trim();
    if (!value || builderState.status === "generating") return;
    void runGenerate(value);
  }, [prompt, builderState.status, runGenerate]);

  const handleSave = useCallback(async () => {
    if (!generated || saveState === "saving") return;
    setSaveState("saving");
    setSaveError(null);
    try {
      const slug = toReportSlug(generated.title);
      await saveGeneratedReport({
        slug,
        title: generated.title,
        description: null,
        template_slug: generated.slug,
        params: generated.params,
      });
      // The saved definition is live in Core; land on its detail page so the
      // user sees the persisted report (and can run/export it) immediately.
      router.push(`/dashboard/erp/reports/${slug}`);
    } catch (error) {
      setSaveState("error");
      setSaveError(error instanceof ApiError ? error.message : "Could not save the report.");
    }
  }, [generated, router, saveState]);

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

        <section
          aria-labelledby="report-builder-heading"
          className="rounded-xl border border-border bg-card p-4"
        >
          <div className="flex items-start gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles aria-hidden="true" className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <h2
                id="report-builder-heading"
                className="font-display text-sm font-semibold text-foreground"
              >
                Ask Skyrict to build a report
              </h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Describe the report you need — Skyrict matches a reviewed
                template, runs it, and can save it to this workspace.
              </p>
            </div>
          </div>

          <div className="mt-3 flex gap-2">
            <Input
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleGenerate();
              }}
              placeholder="e.g. outstanding AR balances by aging bucket"
              aria-label="Describe the report you want"
              className="flex-1"
            />
            <Button
              type="button"
              onClick={handleGenerate}
              disabled={builderState.status === "generating" || !prompt.trim()}
            >
              {builderState.status === "generating" ? (
                <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              ) : (
                <Send aria-hidden="true" className="size-4" />
              )}
              Generate
            </Button>
          </div>

          <div className="mt-2 flex flex-wrap gap-2">
            {SUGGESTED_PROMPTS.map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="outline"
                size="sm"
                disabled={builderState.status === "generating"}
                onClick={() => {
                  setPrompt(suggestion);
                  void runGenerate(suggestion);
                }}
              >
                {suggestion}
              </Button>
            ))}
          </div>

          {builderState.status === "generating" ? (
            <p
              role="status"
              className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"
            >
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              Building your report…
            </p>
          ) : null}

          {builderState.status === "error" ? (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {builderState.message}
            </p>
          ) : null}

          {answer ? (
            <div className="mt-3 space-y-3">
              <p className="text-sm text-foreground">{answer}</p>

              {generated ? (
                <>
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-border bg-muted/40">
                          {generated.columns.map((column) => (
                            <th
                              key={column}
                              scope="col"
                              className="px-3 py-2 font-medium whitespace-nowrap text-muted-foreground"
                            >
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {generated.rows.slice(0, PREVIEW_MAX_ROWS).map((row, index) => (
                          <tr
                            key={index}
                            className="border-b border-border/60 last:border-0"
                          >
                            {generated.columns.map((column) => (
                              <td
                                key={column}
                                className="px-3 py-1.5 whitespace-nowrap text-foreground"
                              >
                                {row[column] ?? ""}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {generated.rows.length > PREVIEW_MAX_ROWS ? (
                    <p className="text-xs text-muted-foreground">
                      Showing the first {PREVIEW_MAX_ROWS} of {generated.rows.length} rows.
                    </p>
                  ) : null}
                  {generated.truncated ? (
                    <p className="text-xs text-muted-foreground">
                      Results are truncated to the workspace preview cap — the
                      saved report exports the full set.
                    </p>
                  ) : null}

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="default"
                      onClick={() => void handleSave()}
                      disabled={saveState === "saving"}
                    >
                      {saveState === "saving" ? (
                        <Loader2 aria-hidden="true" className="size-4 animate-spin" />
                      ) : (
                        <Save aria-hidden="true" className="size-4" />
                      )}
                      Save as report
                    </Button>
                    {saveState === "error" && saveError ? (
                      <p role="alert" className="text-sm text-destructive">
                        {saveError}
                      </p>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
        </section>

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