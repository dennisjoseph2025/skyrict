"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Clock,
  PackageX,
  TrendingUp,
  TriangleAlert,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/dashboard/shared/stat-card";
import { StatCardSkeleton } from "@/components/ui/page-skeletons";
import { runReport } from "@/lib/api/reports-api";
import { ApiError } from "@/lib/api/http";
import {
  DASHBOARD_KPI_DEFS,
  deriveKpiValue,
  kpiHref,
  type DashboardKpiDef,
  type KpiId,
} from "@/lib/reports/kpis";

type KpiSlot =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; value: string; hint: string };

const KPI_ICONS: Record<KpiId, LucideIcon> = {
  cash_received: Wallet,
  ar_aging: Clock,
  pipeline_value: TrendingUp,
  stock_alerts: PackageX,
  headcount: Users,
};

const emptySlots = (): Record<KpiId, KpiSlot> =>
  Object.fromEntries(
    DASHBOARD_KPI_DEFS.map((def) => [def.id, { status: "loading" }]),
  ) as Record<KpiId, KpiSlot>;

export function ReportKpis() {
  const [slots, setSlots] = useState<Record<KpiId, KpiSlot>>(emptySlots);

  const loadOne = useCallback(async (def: DashboardKpiDef) => {
    setSlots((current) => ({ ...current, [def.id]: { status: "loading" } }));
    try {
      const result = await runReport(def.slug, def.params());
      const { value, hint } = deriveKpiValue(def.id, result);
      setSlots((current) => ({ ...current, [def.id]: { status: "ready", value, hint } }));
    } catch (error) {
      setSlots((current) => ({
        ...current,
        [def.id]: {
          status: "error",
          message:
            error instanceof ApiError ? error.message : "Metric unavailable right now.",
        },
      }));
    }
  }, []);

  const loadAll = useCallback(() => {
    for (const def of DASHBOARD_KPI_DEFS) void loadOne(def);
  }, [loadOne]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const errorCount = Object.values(slots).filter((slot) => slot.status === "error").length;

  return (
    <section aria-label="Report KPIs" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Report KPIs
        </h2>
        {errorCount > 0 ? (
          <Button type="button" variant="outline" size="sm" onClick={loadAll}>
            Retry all
          </Button>
        ) : null}
      </div>

      {errorCount > 0 ? (
        <div
          role="status"
          className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
        >
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p>
            {errorCount} of {DASHBOARD_KPI_DEFS.length} report metrics are
            unavailable right now — live values reappear when the reporting
            service recovers.
          </p>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {DASHBOARD_KPI_DEFS.map((def) => {
          const slot = slots[def.id];
          if (slot.status === "ready") {
            return (
              <StatCard
                key={def.id}
                icon={KPI_ICONS[def.id]}
                label={def.label}
                value={slot.value}
                hint={slot.hint}
                href={kpiHref(def)}
              />
            );
          }
          if (slot.status === "error") {
            return (
              <div
                key={def.id}
                className="rounded-xl border border-border bg-card p-5"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                    {def.label}
                  </p>
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
                    <TriangleAlert aria-hidden="true" className="size-4" />
                  </span>
                </div>
                <p className="mt-2 line-clamp-2 text-xs text-destructive">
                  {slot.message}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => void loadOne(def)}
                >
                  Retry
                </Button>
              </div>
            );
          }
          return <StatCardSkeleton key={def.id} />;
        })}
      </div>
    </section>
  );
}