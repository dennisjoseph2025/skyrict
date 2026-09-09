"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Calculator as CalculatorIcon,
    Database,
    Gauge,
    TrendingUp,
} from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { TableSkeleton } from "@/components/ui/page-skeletons";
import { ApiError } from "@/lib/api/http";
import {
    getRevenueForecast,
    type RevenueForecast,
} from "@/lib/api/finance-api";
import { formatMoney } from "@/lib/finance/format";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; forecast: RevenueForecast };

const panel =
    "rounded-xl border border-border/70 bg-muted/30 p-4 sm:p-5";

function monthOf(value: string): string {
    return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
        month: "short",
        year: "2-digit",
    });
}

function SectionCard({
    icon,
    title,
    children,
}: {
    icon: React.ReactNode;
    title: string;
    children: React.ReactNode;
}) {
    return (
        <section className={panel}>
            <div className="mb-3 flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary [&>svg]:size-4">
                    {icon}
                </span>
                <h2 className="font-display text-sm font-semibold text-foreground">
                    {title}
                </h2>
            </div>
            <div className="space-y-3 text-sm leading-relaxed text-muted-foreground">
                {children}
            </div>
        </section>
    );
}

function MethodCard({ title, body }: { title: string; body: string }) {
    return (
        <div className="flex flex-col gap-0.5 border-b border-border/60 pb-3 last:border-b-0 last:pb-0">
            <dt className="text-sm font-medium text-foreground">{title}</dt>
            <dd className="text-sm text-muted-foreground">{body}</dd>
        </div>
    );
}

function HowItWorks({ forecast }: { forecast: RevenueForecast | null }) {
    return (
        <SectionCard icon={<CalculatorIcon />} title="How it's computed">
            <dl className="space-y-3">
                <MethodCard
                    title="1 · Baseline — damped trend + seasonal echo"
                    body="A least-squares trend is fit to the recognized-revenue history and projected forward with damping (each month's step shrinks by 0.90, so the line curves toward a plateau instead of over-extrapolating). Each already-observed calendar month then brings back its average deviation from the trend — promotion months, quarter-end spikes, seasonal dips repeat in the same calendar months ahead."
                />
                <MethodCard
                    title="2 · Pipeline uplift — weighted open deals"
                    body="Open CRM opportunities contribute probability × amount, bucketed to their expected close month. A $100k deal at 60% probability adds $60k to its close month. Deals without an amount or a close date are ignored — they can't be value-weighted or bucketed honestly."
                />
                <MethodCard
                    title="3 · Combine"
                    body="Predicted per month = baseline + pipeline uplift. Both components are stored and surfaced, so every predicted value can be traced back to how it was built."
                />
                <MethodCard
                    title="4 · Confidence band"
                    body={
                        forecast?.sigma != null
                            ? `Predicted ±1.5σ, where σ = ${formatMoney(forecast.sigma)} is the standard deviation of walk-forward historical errors. The band reflects how accurately the model has predicted past months.`
                            : "A ±1.5σ band is added once walk-forward errors exist (the model needs enough history to score itself)."
                    }
                />
            </dl>
        </SectionCard>
    );
}

function InputsCard({ forecast }: { forecast: RevenueForecast | null }) {
    const pipelineTotal = forecast?.pipeline_value;
    return (
        <SectionCard icon={<Database />} title="Inputs">
            <dl className="space-y-3">
                <MethodCard
                    title="Revenue history"
                    body="Approved invoices, bucketed by invoice month — the same recognition boundary as the rest of finance (revenue only counts when an invoice is approved). The model looks back 24 months. With fewer than 3 months of history it abstains rather than hallucinate."
                />
                <MethodCard
                    title="CRM pipeline"
                    body={
                        pipelineTotal != null
                            ? `${formatMoney(pipelineTotal)} of weighted expected pipeline is currently blended into the horizon (open, non-won/lost opportunities at their conversion probability, bucketed by expected close month).`
                            : "No weighted pipeline is currently blended into the horizon (either the forecast abstained or the run predates pipeline weighting)."
                    }
                />
                <MethodCard
                    title="What pipeline never does"
                    body="Backtest MAPE and σ are computed over historical months only. Pipeline input can move predicted values but can never inflate the model's reported accuracy."
                />
            </dl>
        </SectionCard>
    );
}

function AccuracyCard({ forecast }: { forecast: RevenueForecast | null }) {
    const mape = forecast?.backtest_mape;
    const sigma = forecast?.sigma;
    return (
        <SectionCard icon={<Gauge />} title="Validation (walk-forward)">
            <dl className="space-y-3">
                <MethodCard
                    title="How it's validated"
                    body="For every month t ≥ 4, the model is re-fit on the t−1 prior months and asked to predict month t; the difference (predicted − actual) becomes a walk-forward error. Accuracy grows with history."
                />
                <MethodCard
                    title={
                        mape != null
                            ? `MAPE ${Number(mape).toFixed(1)}%`
                            : "MAPE not yet available"
                    }
                    body="Mean absolute percentage error across the walk-forward sample — the average size of the model's misses relative to actual revenue."
                />
                <MethodCard
                    title={
                        sigma != null
                            ? `σ ±${formatMoney(sigma)}`
                            : "σ not yet available"
                    }
                    body="Spread (standard deviation) of the walk-forward errors. Multiplying by 1.5 gives the confidence band drawn on the forecast chart."
                />
            </dl>
        </SectionCard>
    );
}

function DecompositionTable({
    forecast,
}: {
    forecast: RevenueForecast;
}) {
    const rows = forecast.points.filter(
        (point) => point.baseline != null && point.pipeline != null,
    );
    return (
        <section className={panel}>
            <div className="mb-3 flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary [&>svg]:size-4">
                    <TrendingUp />
                </span>
                <h2 className="font-display text-sm font-semibold text-foreground">
                    Month-by-month breakdown
                </h2>
            </div>
            <p className="mb-3 text-sm text-muted-foreground">
                Every forecast month, peeled back into its two components. A
                month with a pipeline uplift is highlighted — this is what
                makes the forecast jump above the trend + seasonal baseline.
            </p>
            <div className="overflow-x-auto">
                <table className="w-full text-right text-sm tabular-nums">
                    <thead className="text-xs text-muted-foreground uppercase">
                        <tr className="border-b border-border/70">
                            <th className="px-3 py-2 text-left font-medium">
                                Month
                            </th>
                            <th className="px-3 py-2 font-medium">
                                Baseline ($)
                            </th>
                            <th className="px-3 py-2 font-medium">
                                Pipeline ($)
                            </th>
                            <th className="px-3 py-2 font-medium">
                                Predicted ($)
                            </th>
                            <th className="px-3 py-2 font-medium">
                                ±1.5σ range ($)
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((point) => {
                            const uplifted = point.pipeline! > 0;
                            const lower = point.lower_bound;
                            const upper = point.upper_bound;
                            return (
                                <tr
                                    key={point.month}
                                    className={
                                        uplifted
                                            ? "border-b border-border/50 bg-sky-500/[0.05]"
                                            : "border-b border-border/50"
                                    }
                                >
                                    <td className="px-3 py-2 text-left font-medium text-foreground">
                                        {monthOf(point.month)}
                                        {uplifted ? (
                                            <span className="ml-2 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600 uppercase dark:text-sky-400">
                                                pipeline
                                            </span>
                                        ) : null}
                                    </td>
                                    <td className="px-3 py-2 text-muted-foreground">
                                        {formatMoney(point.baseline!)}
                                    </td>
                                    <td
                                        className={
                                            uplifted
                                                ? "px-3 py-2 font-semibold text-foreground"
                                                : "px-3 py-2 text-muted-foreground"
                                        }
                                    >
                                        {uplifted
                                            ? `+${formatMoney(point.pipeline!)}`
                                            : "—"}
                                    </td>
                                    <td className="px-3 py-2 font-semibold text-foreground">
                                        {formatMoney(point.predicted)}
                                    </td>
                                    <td className="px-3 py-2 text-muted-foreground">
                                        {lower != null && upper != null
                                            ? `${formatMoney(lower)} – ${formatMoney(upper)}`
                                            : "—"}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
                The largest single driver of the near-term shape is usually the
                pipeline row: a big deal expected to close in one month lifts
                that month well above the baseline and pulls the line back down
                once its month passes. Breakdown is captured at refresh time —
                a deal that slips or loses changes the next refreshed forecast.
            </p>
        </section>
    );
}

export function ForecastModel() {
    const [status, setStatus] = useState<Status>({ state: "loading" });

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
                        : "Could not load the forecast model.",
            });
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const forecast = status.state === "ready" ? status.forecast : null;

    return (
        <div className="space-y-6">
            <PageHeader
                title="Forecast model"
                description="How the 12-month revenue forecast is computed, decomposed, and validated."
                icon={TrendingUp}
            />

            {status.state === "loading" ? (
                <TableSkeleton rows={6} />
            ) : status.state === "error" ? (
                <p className="text-sm text-destructive">{status.message}</p>
            ) : (
                <>
                    <div className="grid gap-4 lg:grid-cols-2">
                        <HowItWorks forecast={forecast} />
                        <div className="grid gap-4">
                            <InputsCard forecast={forecast} />
                            <AccuracyCard forecast={forecast} />
                        </div>
                    </div>
                    {forecast && forecast.points.length > 0 ? (
                        <DecompositionTable forecast={forecast} />
                    ) : (
                        <p className="text-sm text-muted-foreground">
                            No forecast exists yet — the model needs at least 3
                            months of approved invoices before it will predict.
                        </p>
                    )}
                </>
            )}
        </div>
    );
}