import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const TONE_VALUE: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-foreground",
  destructive: "text-destructive",
  warning: "text-amber-600 dark:text-amber-400",
  info: "text-sky-600 dark:text-sky-400",
  success: "text-emerald-600 dark:text-emerald-400",
};

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  /** Tints the value figure to flag the mood of the metric. */
  tone?: "default" | "destructive" | "warning" | "info" | "success";
  /** When set, the whole card becomes a link. */
  href?: string;
}

/** A compact KPI card: label, value, and an optional note with an icon tile. */
export function StatCard({ icon: Icon, label, value, hint, tone = "default", href }: StatCardProps) {
  const cardClass = cn(
    "block rounded-xl border border-border bg-card p-5",
    href && "transition-colors hover:border-primary/40 hover:bg-muted/40",
  );

  const content = (
    <>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
          {label}
        </p>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon aria-hidden="true" className="size-4" />
        </span>
      </div>
      <p className={cn("mt-2 font-display text-2xl font-semibold tracking-tight", TONE_VALUE[tone])}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-sm text-muted-foreground">{hint}</p> : null}
    </>
  );

  if (href) {
    return (
      <Link href={href} className={cardClass}>
        {content}
      </Link>
    );
  }

  return <div className={cardClass}>{content}</div>;
}
