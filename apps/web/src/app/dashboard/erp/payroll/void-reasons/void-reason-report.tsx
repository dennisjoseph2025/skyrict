"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Copy, CalendarX, Wrench } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton } from "@/components/ui/page-skeletons";
import {
  getVoidReasonReport,
  voidCategoryLabel,
  type VoidPatternReport,
  type VoidReasonCategory,
} from "@/lib/api/payroll-api";
import { ApiError } from "@/lib/api/http";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type PageStatus =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; report: VoidPatternReport };

const CATEGORY_ORDER: VoidReasonCategory[] = [
  "duplicate",
  "wrong_period",
  "correction_needed",
  "unclassified",
];

const CATEGORY_META: Record<
  VoidReasonCategory,
  { icon: typeof Copy; tone: string }
> = {
  duplicate: { icon: Copy, tone: "text-foreground" },
  wrong_period: { icon: CalendarX, tone: "text-sky-600 dark:text-sky-400" },
  correction_needed: { icon: Wrench, tone: "text-amber-600 dark:text-amber-400" },
  unclassified: { icon: AlertTriangle, tone: "text-destructive" },
};

export function VoidReasonReportClient() {
  const [status, setStatus] = useState<PageStatus>({ state: "loading" });

  const load = useCallback(async () => {
    setStatus({ state: "loading" });
    try {
      const report = await getVoidReasonReport(6);
      setStatus({ state: "ready", report: report ?? { months: [], totals: { duplicate: 0, wrong_period: 0, correction_needed: 0, unclassified: 0 }, unclassifiedRecent: [] } });
    } catch (error) {
      setStatus({
        state: "error",
        message: error instanceof ApiError ? error.message : "Could not load void reasons.",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (status.state === "loading") {
    return (
      <div className="space-y-4">
        <PageHeader icon={AlertTriangle} title="Void reasons" description="Monthly void-cause patterns across payroll runs." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <CardSkeleton className="h-64" />
      </div>
    );
  }

  if (status.state === "error") {
    return (
      <div className="space-y-6">
        <PageHeader icon={AlertTriangle} title="Void reasons" description="Monthly void-cause patterns across payroll runs." />
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-10 text-center">
          <p className="text-sm font-medium text-destructive">{status.message}</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  const { report } = status;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={AlertTriangle}
        title="Void reasons"
        description="Monthly void-cause patterns across payroll runs - weak signals stay unclassified for review."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CATEGORY_ORDER.map((category) => {
          const meta = CATEGORY_META[category];
          const Icon = meta.icon;
          return (
            <div key={category} className="rounded-xl border border-border bg-card p-4">
              <p
                className={cn(
                  "flex items-center gap-1.5 text-xs font-medium text-muted-foreground",
                )}
              >
                <Icon aria-hidden="true" className={cn("size-4", meta.tone)} />
                {voidCategoryLabel(category)}
              </p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-foreground">
                {report.totals[category] ?? 0}
              </p>
            </div>
          );
        })}
      </div>

      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="font-display text-sm font-semibold tracking-tight text-foreground">
          Voids by month
        </h2>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="pb-2 font-medium">Period</th>
              {CATEGORY_ORDER.map((category) => (
                <th key={category} className="pb-2 text-right font-medium">
                  {voidCategoryLabel(category)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {report.months.map((month) => (
              <tr key={month.month}>
                <td className="py-2 font-medium text-foreground">
                  {formatDate(month.month)}
                </td>
                {CATEGORY_ORDER.map((category) => (
                  <td key={category} className="py-2 text-right tabular-nums text-muted-foreground">
                    {month[category]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {report.unclassifiedRecent.length > 0 ? (
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold tracking-tight text-foreground">
            <AlertTriangle aria-hidden="true" className="size-4 text-destructive" />
            Needs review
            <span className="ml-auto text-xs font-normal text-muted-foreground">
              Raw reasons that did not meet the confidence floor
            </span>
          </h2>
          <ul className="mt-3 divide-y divide-border">
            {report.unclassifiedRecent.map((entry) => (
              <li key={entry.runId} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">
                    {entry.reason || "(no reason supplied)"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {entry.runCode} · {formatDate(entry.periodStart)}
                  </p>
                </div>
                <Badge variant="outline" className="shrink-0 bg-destructive/10 text-destructive">
                  Unclassified
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">
          No unclassified void reasons in the last 6 months.
        </p>
      )}
    </div>
  );
}