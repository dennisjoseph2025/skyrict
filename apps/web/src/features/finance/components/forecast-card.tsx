"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Info, Loader2, RefreshCw, TrendingUp } from "lucide-react";
import {
    Area,
    Bar,
    BarChart,
    CartesianGrid,
    ComposedChart,
    Line,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/http";
import {
    getRevenueForecast,
    refreshRevenueForecast,
    type RevenueForecast,
} from "@/lib/api/finance-api";
import { formatMoney } from "@/lib/finance/format";
import { WidgetCard } from "@/features/finance/components/automation-widgets";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; forecast: RevenueForecast };

const PREDICTED_COLOR = "#0ea5e9";
const BAND_COLOR = "#0ea5e9";
const BASELINE_COLOR = "#64748b";
const ACTUAL_COLOR = "#f59e0b";

const chartPanel =
    "rounded-xl border border-border/70 bg-muted/30 p-3 sm:p-4";

function monthLabel(value: string): string {
    const date = new Date(`${value}T00:00:00`);
    return date.toLocaleDateString(undefined, {
        month: "short",
        year: "2-digit",
    });
}

const axisTick = {
    fontSize: 11,
    fill: "var(--muted-foreground)",
    fontFamily: "var(--font-sans)",
};

const compactMoneyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
});

function compactMoney(value: number): string {
    return compactMoneyFormatter.format(value);
}

function LegendChip({
    swatch,
    color,
    label,
}: {
    swatch: "dot" | "dash" | "band";
    color: string;
    label: string;
}) {
    return (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            {swatch === "dot" ? (
                <span
                    aria-hidden="true"
                    className="size-2 rounded-full"
                    style={{ background: color }}
                />
            ) : swatch === "dash" ? (
                <span
                    aria-hidden="true"
                    className="h-0.5 w-3.5"
                    style={{
                        background: `repeating-linear-gradient(90deg, ${color} 0 3px, transparent 3px 5px)`,
                    }}
                />
            ) : (
                <span
                    aria-hidden="true"
                    className="h-2 w-3.5 rounded-[2px]"
                    style={{ background: color }}
                />
            )}
            {label}
        </span>
    );
}

function ChartTooltipContent({
    active,
    payload,
    label,
}: {
    active: boolean;
    payload?: ReadonlyArray<{
        name?: string;
        value?: number | [number, number];
        color?: string;
        payload?: { baseline?: number | null; pipeline?: number | null };
    }>;
    label?: string;
}) {
    if (!active || !payload || payload.length === 0) return null;
    const datum = payload[0]?.payload;
    const hasBreakdown =
        datum?.baseline != null && datum?.pipeline != null;
    const predictedEntry = payload.find((entry) => entry.name === "Predicted");
    return (
        <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
            {label ? (
                <p className="mb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    {label}
                </p>
            ) : null}
            <ul className="space-y-1">
                {payload.map((entry, index) => (
                    <li key={index} className="flex items-center gap-2 text-sm">
                        <span
                            aria-hidden="true"
                            className="size-2 shrink-0 rounded-full"
                            style={{
                                backgroundColor:
                                    entry.color ?? "var(--chart-1)",
                            }}
                        />
                        <span className="text-muted-foreground">
                            {entry.name}
                        </span>
                        <span className="ml-auto pl-3 font-semibold tabular-nums text-foreground">
                            {Array.isArray(entry.value)
                                ? `${formatMoney(entry.value[0])} – ${formatMoney(entry.value[1])}`
                                : formatMoney(entry.value ?? 0)}
                        </span>
                    </li>
                ))}
            </ul>
            {hasBreakdown ? (
                <p className="mt-2 border-t border-border/60 pt-1.5 text-xs tabular-nums text-muted-foreground">
                    {formatMoney(datum!.baseline!)} trend+seasonal
                    {datum!.pipeline! > 0 ? (
                        <>
                            {" "}
                            + {formatMoney(datum!.pipeline!)} pipeline
                        </>
                    ) : null}{" "}
                    = {formatMoney((predictedEntry?.value as number) ?? 0)}
                </p>
            ) : null}
        </div>
    );
}

function AssumptionsDrawer({ forecast }: { forecast: RevenueForecast | null }) {
    const rows = [
        [
            "Input source",
            "Approved invoices (recognized revenue), bucketed by month",
        ],
        [
            "Model",
            "Damped trend + monthly seasonal echo (repeats the observed ups/downs of each calendar month)",
        ],
        ["Horizon", "12 months"],
        ["History window", "Last 24 months of revenue lookback"],
        [
            "Abstention",
            "No forecast when there are fewer than 3 months of history",
        ],
        [
            "Formula",
            "Predicted = baseline (trend + seasonal echo) + pipeline uplift (weighted open CRM deals). Each forecast comes back with both components shown per month.",
        ],
        [
            "Confidence band",
            forecast?.sigma != null
                ? `Predicted ±1.5σ of walk-forward error (σ ${formatMoney(Math.abs(forecast.sigma))})`
                : "Omitted until walk-forward errors are available",
        ],
        [
            "Backtest",
            forecast?.backtest_mape != null
                ? `Walk-forward MAPE ${Number(forecast.backtest_mape).toFixed(1)}%`
                : "Insufficient history to validate yet",
        ],
        [
            "Pipeline weighting",
            forecast?.pipeline_value != null
                ? `Open CRM deals weighted by conversion probability (probability × amount, bucketed by expected close month) are added to each affected forecast month. Weighted pipeline in the horizon: ${formatMoney(forecast.pipeline_value)}.`
                : "Open CRM deals weighted by conversion probability (probability × amount, bucketed by expected close month) are added to forecast months. Not fed when the forecast abstains.",
        ],
    ];
    const decomposition =
        forecast?.points?.filter(
            (point) => point.baseline != null && point.pipeline != null,
        ) ?? [];
    const hasDecomposition = decomposition.length > 0;
    const monthOf = (value: string) =>
        new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
            month: "short",
            year: "2-digit",
        });
    return (
        <Dialog>
            <DialogTrigger asChild>
                <Button
                    variant="ghost"
                    size="sm"
                    aria-label="View forecast assumptions"
                >
                    <Info aria-hidden="true" className="mr-1.5 size-3.5" />
                    Assumptions
                </Button>
            </DialogTrigger>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Revenue forecast assumptions</DialogTitle>
                    <DialogDescription>
                        Model inputs and weights used for the 12-month revenue
                        forecast.
                    </DialogDescription>
                </DialogHeader>
                <dl className="space-y-3 pt-1">
                    {rows.map(([term, detail]) => (
                        <div
                            key={term}
                            className="flex flex-col gap-0.5 border-b border-border/60 pb-3 last:border-b-0 last:pb-0"
                        >
                            <dt className="text-sm font-medium text-foreground">
                                {term}
                            </dt>
                            <dd className="text-sm text-muted-foreground">
                                {detail}
                            </dd>
                        </div>
                    ))}
                </dl>
                {hasDecomposition ? (
                    <div className="mt-2">
                        <h4 className="mb-2 text-sm font-semibold text-foreground">
                            Month-by-month breakdown
                        </h4>
                        <div className="max-h-64 overflow-y-auto rounded-lg border border-border/70">
                            <table className="w-full text-right text-sm tabular-nums">
                                <thead className="sticky top-0 bg-muted text-xs text-muted-foreground uppercase">
                                    <tr>
                                        <th className="px-3 py-2 text-left font-medium">
                                            Month
                                        </th>
                                        <th className="px-3 py-2 font-medium">
                                            Baseline
                                        </th>
                                        <th className="px-3 py-2 font-medium">
                                            Pipeline
                                        </th>
                                        <th className="px-3 py-2 font-medium">
                                            Predicted
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {decomposition.map((point) => (
                                        <tr
                                            key={point.month}
                                            className="border-t border-border/50"
                                        >
                                            <td className="px-3 py-1.5 text-left font-medium text-foreground">
                                                {monthOf(point.month)}
                                            </td>
                                            <td className="px-3 py-1.5 text-muted-foreground">
                                                {formatMoney(point.baseline!)}
                                            </td>
                                            <td
                                                className={
                                                    point.pipeline! > 0
                                                        ? "px-3 py-1.5 font-semibold text-foreground"
                                                        : "px-3 py-1.5 text-muted-foreground"
                                                }
                                            >
                                                {point.pipeline! > 0
                                                    ? `+${formatMoney(point.pipeline!)}`
                                                    : "—"}
                                            </td>
                                            <td className="px-3 py-1.5 font-semibold text-foreground">
                                                {formatMoney(point.predicted)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}

function AccuracySummary({ forecast }: { forecast: RevenueForecast | null }) {
    const mape = forecast?.backtest_mape != null ? Number(forecast.backtest_mape) : null;
    const sigma = forecast?.sigma != null ? Number(forecast.sigma) : null;
    if (mape === null || sigma === null) {
        return (
            <p className="text-xs text-muted-foreground">
                Accuracy not yet known — the backtest needs at least 4 months of
                history to score the model.
            </p>
        );
    }
    return (
        <div className="mb-4 flex flex-wrap items-center gap-x-8 gap-y-1 border-y border-border/60 py-2">
            <div>
                <div className="text-xs text-muted-foreground">
                    Forecast accuracy
                </div>
                <div className="text-sm font-semibold text-foreground">
                    MAPE {mape.toFixed(1)}%
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                        avg error vs history
                    </span>
                </div>
            </div>
            <div>
                <div className="text-xs text-muted-foreground">Typical error</div>
                <div className="text-sm font-semibold text-foreground">
                    ±{formatMoney(sigma)}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                        1σ of walk-forward error
                    </span>
                </div>
            </div>
            {forecast?.pipeline_value != null ? (
                <div>
                    <div className="text-xs text-muted-foreground">
                        Pipeline input
                    </div>
                    <div className="text-sm font-semibold text-foreground">
                        +{formatMoney(forecast.pipeline_value)}
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                            weighted open deals in horizon
                        </span>
                    </div>
                </div>
            ) : null}
        </div>
    );
}

export function RevenueForecastCard({ canRefresh }: { canRefresh: boolean }) {
    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const forecast = await getRevenueForecast();
            setStatus({ state: "ready", forecast });
        } catch (error) {
            setStatus({
                state: "error",
                message:
                    error instanceof ApiError
                        ? error.message
                        : "Could not load the revenue forecast.",
            });
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const refresh = useCallback(async () => {
        if (refreshing) return;
        setRefreshing(true);
        try {
            const forecast = await refreshRevenueForecast();
            setStatus({ state: "ready", forecast });
        } catch (error) {
            setStatus({
                state: "error",
                message:
                    error instanceof ApiError
                        ? error.message
                        : "Could not refresh the forecast.",
            });
        } finally {
            setRefreshing(false);
        }
    }, [refreshing]);

    const forecast = status.state === "ready" ? status.forecast : null;
    const data = (forecast?.points ?? []).map((point) => ({
        label: monthLabel(point.month),
        predicted: point.predicted,
        baseline: point.baseline,
        pipeline: point.pipeline,
        band:
            point.lower_bound !== null && point.upper_bound !== null
                ? ([point.lower_bound, point.upper_bound] as [number, number])
                : null,
    }));
    const hasDecomposition = data.some((point) => point.baseline != null);
    const historyData = (forecast?.history ?? []).map((point) => ({
        label: monthLabel(point.month),
        actual: point.actual,
    }));

    return (
        <WidgetCard
            title="Revenue forecast"
            icon={<TrendingUp aria-hidden="true" className="size-4" />}
            hint={
                forecast
                    ? `${forecast.model_version} · next ${forecast.points.length} month${forecast.points.length === 1 ? "" : "s"}`
                    : "Forecast from approved invoice history"
            }
            action={
                <div className="flex items-center gap-1">
                    <AssumptionsDrawer forecast={forecast} />
                    {canRefresh ? (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void refresh()}
                            disabled={refreshing}
                            aria-label="Refresh revenue forecast"
                        >
                            {refreshing ? (
                                <Loader2
                                    aria-hidden="true"
                                    className="mr-1.5 size-3.5 animate-spin"
                                />
                            ) : (
                                <RefreshCw
                                    aria-hidden="true"
                                    className="mr-1.5 size-3.5"
                                />
                            )}
                            Refresh
                        </Button>
                    ) : null}
                </div>
            }
        >
            {status.state === "error" ? (
                <p className="text-sm text-destructive">{status.message}</p>
            ) : status.state === "loading" ? (
                <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                    Loading forecast…
                </div>
            ) : data.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    Not enough history to forecast yet — the model needs
                    at least 3 months of approved invoices. Record invoices, then
                    refresh to generate a forecast.
                </p>
            ) : (
                <>
                    <AccuracySummary forecast={forecast} />
                    <div className={chartPanel}>
                        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                            <LegendChip
                                swatch="dot"
                                color={PREDICTED_COLOR}
                                label="Predicted"
                            />
                            {hasDecomposition ? (
                                <LegendChip
                                    swatch="dash"
                                    color={BASELINE_COLOR}
                                    label="Baseline (trend + seasonal)"
                                />
                            ) : null}
                            <LegendChip
                                swatch="band"
                                color="color-mix(in srgb, #0ea5e9 22%, transparent)"
                                label="±1.5σ range"
                            />
                        </div>
                        <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart
                                    data={data}
                                    margin={{
                                        top: 4,
                                        right: 4,
                                        left: 0,
                                        bottom: 0,
                                    }}
                                >
                                    <defs>
                                        <linearGradient
                                            id="forecastBand"
                                            x1="0"
                                            y1="0"
                                            x2="0"
                                            y2="1"
                                        >
                                            <stop
                                                offset="0%"
                                                stopColor={BAND_COLOR}
                                                stopOpacity={0.24}
                                            />
                                            <stop
                                                offset="100%"
                                                stopColor={BAND_COLOR}
                                                stopOpacity={0.04}
                                            />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid
                                        stroke="var(--border)"
                                        strokeOpacity={0.6}
                                        vertical={false}
                                    />
                                    <XAxis
                                        dataKey="label"
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickMargin={8}
                                        interval="preserveStartEnd"
                                    />
                                    <YAxis
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickFormatter={compactMoney}
                                        domain={[0, "auto"]}
                                        width={52}
                                    />
                                    <Tooltip
                                        cursor={{
                                            stroke: "var(--border)",
                                            strokeOpacity: 0.9,
                                        }}
                                        content={({ active, payload, label }) => (
                                            <ChartTooltipContent
                                                active={Boolean(active)}
                                                payload={
                                                    payload as ReadonlyArray<{
                                                        name?: string;
                                                        value?: number | [number, number];
                                                        color?: string;
                                                    }>
                                                }
                                                label={label as string | undefined}
                                            />
                                        )}
                                    />
                                    <Area
                                        dataKey="band"
                                        name="±1.5σ range"
                                        stroke="none"
                                        fill="url(#forecastBand)"
                                        activeDot={false}
                                        legendType="none"
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="predicted"
                                        name="Predicted"
                                        stroke={PREDICTED_COLOR}
                                        strokeWidth={2.5}
                                        dot={false}
                                        activeDot={{
                                            r: 4,
                                            strokeWidth: 2,
                                            stroke: "var(--card)",
                                        }}
                                        legendType="none"
                                    />
                                    {hasDecomposition ? (
                                        <Line
                                            type="monotone"
                                            dataKey="baseline"
                                            name="Baseline"
                                            stroke={BASELINE_COLOR}
                                            strokeWidth={1.5}
                                            strokeDasharray="4 4"
                                            dot={false}
                                            activeDot={false}
                                            legendType="none"
                                        />
                                    ) : null}
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                        {forecast?.model_version} · 12-month forecast, band =
                        ±1.5σ of walk-forward error. Model inputs and weights are
                        listed in Assumptions.{" "}
                        <Link
                            href="/dashboard/erp/finance/model"
                            className="font-medium text-primary hover:underline"
                        >
                            See how this is computed →
                        </Link>
                    </p>
                </>
            )}
            {historyData.length > 0 ? (
                <div className="mt-6">
                    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                        <h4 className="font-display text-sm font-semibold text-foreground">
                            Revenue history
                        </h4>
                        <p className="text-xs text-muted-foreground">
                            Actual recognized revenue by month (approved
                            invoices) — the input to the forecast above
                        </p>
                    </div>
                    <div className={chartPanel}>
                        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                            <LegendChip
                                swatch="dot"
                                color={ACTUAL_COLOR}
                                label="Actual revenue"
                            />
                        </div>
                        <div className="h-48">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={historyData}
                                    margin={{
                                        top: 4,
                                        right: 4,
                                        left: 0,
                                        bottom: 0,
                                    }}
                                >
                                    <CartesianGrid
                                        stroke="var(--border)"
                                        strokeOpacity={0.6}
                                        vertical={false}
                                    />
                                    <XAxis
                                        dataKey="label"
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickMargin={8}
                                        interval="preserveStartEnd"
                                    />
                                    <YAxis
                                        tick={axisTick}
                                        axisLine={false}
                                        tickLine={false}
                                        tickFormatter={compactMoney}
                                        domain={[0, "auto"]}
                                        width={52}
                                    />
                                    <Tooltip
                                        cursor={{
                                            fill: "var(--card)",
                                            fillOpacity: 0.55,
                                        }}
                                        content={({ active, payload, label }) => (
                                            <ChartTooltipContent
                                                active={Boolean(active)}
                                                payload={
                                                    payload as ReadonlyArray<{
                                                        name?: string;
                                                        value?: number | [number, number];
                                                        color?: string;
                                                    }>
                                                }
                                                label={label as string | undefined}
                                            />
                                        )}
                                    />
                                    <Bar
                                        dataKey="actual"
                                        name="Actual"
                                        fill={ACTUAL_COLOR}
                                        fillOpacity={0.9}
                                        radius={[4, 4, 0, 0]}
                                        maxBarSize={36}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            ) : null}
        </WidgetCard>
    );
}
