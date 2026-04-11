import { clsx } from "clsx";
import type { WindowKey } from "../lib/types";

const WINDOWS: WindowKey[] = ["1d", "3d", "5d", "7d", "14d", "31d"];

interface WindowSelectorProps {
  value: WindowKey;
  onChange: (value: WindowKey) => void;
  className?: string;
}

export function WindowSelector({ value, onChange, className }: WindowSelectorProps) {
  return (
    <div role="tablist" aria-label="Time window selector" className={clsx("inline-flex gap-1", className)}>
      {WINDOWS.map((key) => {
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-pressed={active}
            onClick={() => onChange(key)}
            className={clsx(
              "px-2.5 py-1.5 text-[0.7rem] font-medium rounded-sm border transition-colors",
              active
                ? "bg-ink text-paper border-ink"
                : "bg-transparent text-ink border-ink/25 hover:border-ink/60",
            )}
          >
            {key}
          </button>
        );
      })}
    </div>
  );
}
