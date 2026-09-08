"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, TrendingUp } from "lucide-react";
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
                canRefresh ? (
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
                ) : null
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
                    No monthly revenue history yet. Record approved invoices,
                    then refresh to generate a forecast.
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
                        {forecast?.model_version} · centerline is the 6-month
                        rolling average of approved invoice revenue. Shaded band
                        is ±1.5σ of walk-forward forecast error
                        {forecast?.backtest_mape !== null &&
                        forecast?.backtest_mape !== undefined ? (
                            <>, MAPE {forecast.backtest_mape * 100}%</>
                        ) : (
                            <> (insufficient history to validate)</>
                        )}
                        .
                    </p>
                </>
            )}
        </WidgetCard>
    );
}
