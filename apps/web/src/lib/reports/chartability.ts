/*
 * Pure heuristics that decide whether a report run's result can be charted
 * and what the chart should look like. The backend does not currently flag
 * chartability, so the UI derives it from the result shape: one non-numeric
 * "category" column plus one or more fully-numeric "value" columns.
 */

export interface ChartPlan {
  kind: "bar" | "line";
  /** The non-numeric column used as the x-axis category. */
  category: string;
  /** The numeric columns plotted as series. */
  values: string[];
}

/** Charts stay useful only for bounded result sizes. */
export const CHART_MAX_ROWS = 200;

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}([T\s]\d{2}:\d{2}(:\d{2})?)?/;

function isNumeric(value: string | undefined): boolean {
  if (value === undefined || value === "") return false;
  return Number.isFinite(Number(value));
}

function isDateLike(value: string | undefined): boolean {
  return value !== undefined && DATE_PATTERN.test(value);
}

export function planChart(
  columns: string[],
  rows: Record<string, string>[],
): ChartPlan | null {
  if (rows.length === 0 || rows.length > CHART_MAX_ROWS) return null;
  if (columns.length < 2) return null;

  const valueColumns = columns.filter((column) =>
    rows.every((row) => isNumeric(row[column])),
  );
  if (valueColumns.length === 0) return null;

  const category = columns.find((column) => !valueColumns.includes(column));
  if (!category) return null;

  return {
    kind: isDateLike(rows[0][category]) ? "line" : "bar",
    category,
    values: valueColumns,
  };
}