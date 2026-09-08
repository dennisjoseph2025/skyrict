import { describe, expect, it } from "vitest";

import { CHART_MAX_ROWS, planChart } from "@/lib/reports/chartability";

describe("planChart", () => {
  it("plans a line chart when the category looks date-like", () => {
    const plan = planChart(["date", "total_received"], [
      { date: "2026-09-01", total_received: "120.5" },
      { date: "2026-09-02", total_received: "90" },
    ]);
    expect(plan).toEqual({ kind: "line", category: "date", values: ["total_received"] });
  });

  it("plans a bar chart for categorical categories", () => {
    const plan = planChart(["bucket", "total"], [
      { bucket: "Current", total: "12500" },
      { bucket: "31-60", total: "8200" },
    ]);
    expect(plan).toEqual({ kind: "bar", category: "bucket", values: ["total"] });
  });

  it("supports multiple numeric value columns", () => {
    const plan = planChart(["dept", "headcount", "fte"], [
      { dept: "Engineering", headcount: "12", fte: "11.5" },
      { dept: "Sales", headcount: "8", fte: "8" },
    ]);
    expect(plan).toEqual({ kind: "bar", category: "dept", values: ["headcount", "fte"] });
  });

  it("returns null when every column is numeric (no category)", () => {
    expect(planChart(["balance", "count"], [{ balance: "1", count: "2" }])).toBeNull();
  });

  it("returns null without any numeric value column", () => {
    expect(planChart(["name", "sku"], [{ name: "Widget", sku: "W-1" }])).toBeNull();
  });

  it("returns null for empty results", () => {
    expect(planChart(["name", "total"], [])).toBeNull();
  });

  it("returns null for oversized results", () => {
    const rows = Array.from({ length: CHART_MAX_ROWS + 1 }, (_, index) => ({
      name: `Item ${index}`,
      total: "1",
    }));
    expect(planChart(["name", "total"], rows)).toBeNull();
  });

  it("treats a non-numeric cell as disqualifying a value column", () => {
    const rows = [
      { name: "A", total: "10" },
      { name: "B", total: "n/a" },
    ];
    expect(planChart(["name", "total"], rows)).toBeNull();
  });

  it("requires at least two columns", () => {
    expect(planChart(["total"], [{ total: "1" }])).toBeNull();
  });
});