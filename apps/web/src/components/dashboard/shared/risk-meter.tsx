import { cn } from "@/lib/utils";

function toneClasses(value: number) {
  if (value >= 0.7) return "bg-destructive/80";
  if (value >= 0.4) return "bg-amber-500";
  return "bg-emerald-500";
}

/** A labelled horizontal gauge: a filled track plus the percentage readout. */
export function RiskMeter({
  value,
  className,
  showLabel = true,
}: {
  /** 0..1 — the probability or proportion being gauged. */
  value: number;
  className?: string;
  showLabel?: boolean;
}) {
  const clamped = Math.min(Math.max(value, 0), 1);
  const pct = Math.round(clamped * 100);
  return (
    <span className={cn("flex min-w-28 items-center gap-2", className)}>
      <span className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full transition-all", toneClasses(clamped))}
          style={{ width: `${pct}%` }}
        />
      </span>
      {showLabel ? (
        <span className="w-9 shrink-0 tabular-nums text-xs font-semibold text-foreground">
          {pct}%
        </span>
      ) : null}
    </span>
  );
}