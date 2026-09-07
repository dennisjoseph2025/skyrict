"use client";

import { Table2 } from "lucide-react";

import { EmptyState } from "@/components/dashboard/erp/empty-state";
import { formatDateTime } from "@/lib/format";
import type { ReportRunResult } from "@/lib/api/reports-api";
import { cn } from "@/lib/utils";

function isNumericColumn(column: string, rows: Record<string, string>[]): boolean {
  if (rows.length === 0) return false;
  return rows.every((row) => {
    const value = row[column];
    return value !== undefined && value !== "" && Number.isFinite(Number(value));
  });
}

export function ReportResultsTable({ result }: { result: ReportRunResult }) {
  if (result.rows.length === 0) {
    return (
      <EmptyState
        icon={Table2}
        title="No rows"
        description="This report returned no rows for the current parameters. Adjust the parameters and run again."
      />
    );
  }

  const numericColumns = new Set(
    result.columns.filter((column) => isNumericColumn(column, result.rows)),
  );

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground">
        <span>
          {result.rows.length} {result.rows.length === 1 ? "row" : "rows"}
        </span>
        <span aria-hidden="true">·</span>
        <span>Period {result.period}</span>
        <span aria-hidden="true">·</span>
        <span>Generated {formatDateTime(result.generated_at)}</span>
        {result.truncated ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-200">
            Truncated to {result.rows.length} rows — narrow the period for the full set
          </span>
        ) : null}
      </div>

      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card">
            <tr>
              {result.columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className={cn(
                    "px-4 py-2.5 font-medium whitespace-nowrap text-muted-foreground",
                    numericColumns.has(column) && "text-right",
                  )}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-t border-border/60">
                {result.columns.map((column) => (
                  <td
                    key={column}
                    className={cn(
                      "px-4 py-2.5 whitespace-nowrap text-foreground",
                      numericColumns.has(column) && "text-right tabular-nums",
                    )}
                  >
                    {row[column] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}