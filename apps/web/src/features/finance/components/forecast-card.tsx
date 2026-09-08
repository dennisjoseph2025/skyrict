"use client";

import { useCallback, useEffect, useState } from "react";
import { Info, Loader2, RefreshCw, TrendingUp } from "lucide-react";
import {
    Area,
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
import { formatNumber } from "@/lib/erp/money";
import { formatMoney } from "@/lib/finance/format";
import { WidgetCard } from "@/features/finance/components/automation-widgets";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; forecast: RevenueForecast };

function monthLabel(value: string): string {
    const date = new Date(`${value}T00:00:00`);
    return date.toLocaleDateString(undefined, {
        month: "short",
        year: "2-digit",
    });
}

function tooltipMoney(value: number | [number, number]): string {
    if (Array.isArray(value)) {
        return `${formatMoney(value[0])} – ${formatMoney(value[1])}`;
    }
    return formatMoney(value);
}

function AssumptionsDrawer({ forecast }: { forecast: RevenueForecast | null }) {
    const rows = [
        [
            "Input source",
            "Approved invoices (recognized revenue), bucketed by month",
        ],
        [
            "Model",
            "SMA-6: trailing 6-month simple moving average, flat across the horizon",
        ],
        ["Horizon", "12 months"],
        ["History window", "Last 24 months of revenue lookback"],
        [
            "Abstention",
            "No forecast when there are fewer than 6 months of history",
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
                ? `Walk-forward MAPE ${forecast.backtest_mape * 100}%`
                : "Insufficient history to validate yet",
        ],
        [
            "Pipeline weighting",
            "CRM deal-health conversion weighting is a cross-module (CRM) dependency; not yet fed into the model",
        ],
    ];
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
            </DialogContent>
        </Dialog>
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
        band:
            point.lower_bound !== null && point.upper_bound !== null
                ? ([point.lower_bound, point.upper_bound] as [number, number])
                : null,
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
                    Not enough history to forecast yet — the model needs at
                    least 6 months of approved invoices. Record invoices, then
                    refresh to generate a forecast.
                </p>
            ) : (
                <>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart
                                data={data}
                                margin={{
                                    top: 4,
                                    right: 8,
                                    left: 0,
                                    bottom: 0,
                                }}
                            >
                                <CartesianGrid
                                    strokeDasharray="3 3"
                                    stroke="var(--border)"
                                />
                                <XAxis
                                    dataKey="label"
                                    tick={{ fontSize: 12 }}
                                    stroke="var(--muted-foreground)"
                                />
                                <YAxis
                                    tick={{ fontSize: 12 }}
                                    stroke="var(--muted-foreground)"
                                    tickFormatter={(value: number) =>
                                        formatNumber(value)
                                    }
                                />
                                <Tooltip
                                    formatter={(value) =>
                                        tooltipMoney(
                                            value as number | [number, number],
                                        )
                                    }
                                />
                                <Area
                                    dataKey="band"
                                    name="±1.5σ range"
                                    stroke="none"
                                    fill="var(--primary)"
                                    fillOpacity={0.12}
                                    activeDot={false}
                                    legendType="none"
                                />
                                <Line
                                    type="monotone"
                                    dataKey="predicted"
                                    name="Predicted"
                                    stroke="var(--primary)"
                                    strokeWidth={2}
                                    dot={false}
                                    legendType="none"
                                />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                        {forecast?.model_version} · 12-month SMA-6 forecast,
                        band = ±1.5σ of walk-forward error
                        {forecast?.backtest_mape !== null &&
                        forecast?.backtest_mape !== undefined ? (
                            <> · MAPE {forecast.backtest_mape * 100}%</>
                        ) : (
                            <> · not yet validated</>
                        )}
                        . Model inputs and weights are listed in Assumptions.
                    </p>
                </>
            )}
        </WidgetCard>
    );
}
