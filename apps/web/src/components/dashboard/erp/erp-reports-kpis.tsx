"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

import { StatCardSkeleton } from "@/components/ui/page-skeletons";
import { apiFetch } from "@/lib/api/http";
import type { Kpi } from "@/lib/mock/erp";
import { cn } from "@/lib/utils";

interface ReportDefinition {
  slug: string;
  title: string;
  module: string;
  description: string | null;
  version: number;
}

type ReportsPayload =
  | { kind: "definitions"; items: ReportDefinition[] }
  | { kind: "kpis"; items: Kpi[] };

function isDefinitionArray(data: unknown): data is ReportDefinition[] {
  return Array.isArray(data);
}

function isKpisPayload(data: unknown): data is { kpis: Kpi[] } {
  return (
    typeof data === "object" &&
    data !== null &&
    "kpis" in data &&
    Array.isArray((data as { kpis: unknown }).kpis)
  );
}

export function ErpReportsKpis() {
  const [payload, setPayload] = useState<ReportsPayload | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<unknown>("/api/v1/reports")
      .then((data) => {
        if (cancelled) return;
        if (isDefinitionArray(data)) {
          setPayload({ kind: "definitions", items: data });
        } else if (isKpisPayload(data)) {
          setPayload({ kind: "kpis", items: data.kpis });
        } else {
          setError(true);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
        <AlertCircle aria-hidden="true" className="size-4 shrink-0 text-destructive" />
        Couldn&apos;t load report data.
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
    );
  }

  if (payload.kind === "kpis") {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {payload.items.map((kpi) => (
          <div key={kpi.label} className="rounded-xl border border-border bg-card p-5">
            <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
              {kpi.label}
            </p>
            <p className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground">
              {kpi.value}
            </p>
            <p
              className={cn(
                "mt-1 text-sm font-medium",
                kpi.positive
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400",
              )}
            >
              {kpi.delta}
            </p>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {payload.items.map((report) => (
        <div key={report.slug} className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
              {report.title}
            </p>
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground uppercase">
              {report.module}
            </span>
          </div>
          <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
            {report.description ?? "No description"}
          </p>
        </div>
      ))}
    </div>
  );
}