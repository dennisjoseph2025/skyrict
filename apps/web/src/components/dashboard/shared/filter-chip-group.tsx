import { cn } from "@/lib/utils";

export interface FilterChipOption {
  value: string;
  label: string;
}

/** A row of mutually-exclusive filter pills (All / High / Medium / Low…). */
export function FilterChipGroup({
  options,
  value,
  onChange,
  ariaLabel,
  className,
}: {
  options: FilterChipOption[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn("flex flex-wrap items-center gap-1.5", className)}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-7 items-center rounded-full border px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              active
                ? "border-primary/50 bg-primary/15 font-semibold text-primary-foreground"
                : "border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}