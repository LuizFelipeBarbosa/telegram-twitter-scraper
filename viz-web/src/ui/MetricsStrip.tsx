import { clsx } from "clsx";
import { Children, type ReactNode } from "react";

interface MetricsStripProps {
  children: ReactNode;
  className?: string;
}

export function MetricsStrip({ children, className }: MetricsStripProps) {
  const count = Children.count(children);
  return (
    <div
      data-testid="metrics-strip"
      className={clsx("grid border-y border-ink divide-x divide-ink/15", className)}
      style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}
