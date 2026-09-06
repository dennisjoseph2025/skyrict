"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartPlan } from "@/lib/reports/chartability";
import { formatNumber } from "@/lib/erp/money";

const SERIES_COLORS = ["var(--primary)", "#38bdf8", "#f59e0b", "#a78bfa", "#34d399"];

interface ReportChartProps {
  plan: ChartPlan;
  rows: Record<string, string>[];
}

export function ReportChart({ plan, rows }: ReportChartProps) {
  const data = rows
    .map((row) => {
      const point: Record<string, string | number> = {
        [plan.category]: row[plan.category] ?? "",
      };
      for (const value of plan.values) {
        const parsed = Number(row[value]);
        if (!Number.isFinite(parsed)) return null;
        point[value] = parsed;
      }
      return point;
    })
    .filter((point): point is Record<string, string | number> => point !== null);

  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
      <XAxis
        dataKey={plan.category}
        tick={{ fontSize: 12 }}
        stroke="var(--muted-foreground)"
      />
      <YAxis
        tick={{ fontSize: 12 }}
        stroke="var(--muted-foreground)"
        tickFormatter={(value: number) => formatNumber(value)}
      />
      <Tooltip formatter={(value) => formatNumber(Number(value))} />
      <Legend />
    </>
  );

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="font-display text-sm font-semibold text-foreground">Chart</h2>
      <div className="mt-4 h-72">
        <ResponsiveContainer width="100%" height="100%">
          {plan.kind === "line" ? (
            <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              {axes}
              {plan.values.map((value, index) => (
                <Line
                  key={value}
                  type="monotone"
                  dataKey={value}
                  stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              {axes}
              {plan.values.map((value, index) => (
                <Bar
                  key={value}
                  dataKey={value}
                  fill={SERIES_COLORS[index % SERIES_COLORS.length]}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}