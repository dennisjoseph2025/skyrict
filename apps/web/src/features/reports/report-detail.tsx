"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, BarChart3, SlidersHorizontal } from "lucide-react";

import { EmptyState } from "@/components/dashboard/erp/empty-state";
import { ErrorState } from "@/components/dashboard/erp/error-state";
import { RequirePermission } from "@/components/dashboard/shared/require-permission";
import { ListPageSkeleton } from "@/components/ui/page-skeletons";
import {
  REPORT_MODULE_LABELS,
  getReport,
  normalizeModule,
  type ReportDefinition,
} from "@/lib/api/reports-api";
import { ApiError } from "@/lib/api/http";
import { formatDateTime } from "@/lib/format";
import { setPageTitle } from "@/lib/topbar-title";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; report: ReportDefinition };

export function ReportsDetail({
  slug,
}: {
  slug: string;
  initialParams: Record<string, string>;
}) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const report = await getReport(slug);
      setState({ status: "ready", report });
    } catch (error) {
      setState({
        status: "error",
        message:
          error instanceof ApiError ? error.message : "Could not load this report.",
      });
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state.status === "ready") setPageTitle(state.report.title);
    return () => setPageTitle(null);
  }, [state]);

  if (state.status === "loading") {
    return <ListPageSkeleton />;
  }

  if (state.status === "error") {
    return <ErrorState message={state.message} onRetry={() => void load()} />;
  }

  const { report } = state;

  return (
    <RequirePermission permission={report.permission_key}>
      <div className="space-y-6">
        <Link
          href="/dashboard/erp/reports"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          All reports
        </Link>

        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-primary">
            <BarChart3 aria-hidden="true" className="size-5" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {REPORT_MODULE_LABELS[normalizeModule(report.module)]}
              </span>
              <span className="text-xs text-muted-foreground">
                Updated {formatDateTime(report.updated_at)}
              </span>
            </div>
            <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">
              {report.title}
            </h1>
            <p className="text-sm text-muted-foreground">
              {report.description ?? "No description"}
            </p>
          </div>
        </div>

        <EmptyState
          icon={SlidersHorizontal}
          title="Configure this run"
          description="Set the report parameters and press Run to generate live results."
        />
      </div>
    </RequirePermission>
  );
}