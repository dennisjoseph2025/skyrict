"use client";

import { History } from "lucide-react";

import { EmptyState } from "@/components/dashboard/erp/empty-state";
import { ErrorState } from "@/components/dashboard/erp/error-state";
import { formatDateTime } from "@/lib/format";
import type { ReportSnapshot } from "@/lib/api/reports-api";

export type SnapshotsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: ReportSnapshot[] };

export function ReportSnapshots({
  state,
  onRetry,
}: {
  state: SnapshotsState;
  onRetry: () => void;
}) {
  if (state.status === "loading") {
    return (
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground">Loading run history…</p>
      </div>
    );
  }

  if (state.status === "error") {
    return <ErrorState message={state.message} onRetry={onRetry} />;
  }

  if (state.items.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No runs yet"
        description="Results are captured as snapshots whenever you run this report."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border bg-muted/40 px-4 py-2.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Run history
      </div>
      <ul className="divide-y divide-border/60">
        {state.items.map((snapshot) => (
          <li
            key={snapshot.id}
            className="flex items-center justify-between gap-3 px-4 py-2.5"
          >
            <span className="text-sm font-medium text-foreground">{snapshot.period}</span>
            <span className="text-xs text-muted-foreground">
              {formatDateTime(snapshot.generated_at)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}