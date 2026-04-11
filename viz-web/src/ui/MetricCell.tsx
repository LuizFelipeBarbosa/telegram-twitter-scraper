import { clsx } from "clsx";
import type { ReactNode } from "react";

interface MetricCellProps {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  className?: string;
}

export function MetricCell({ label, value, caption, className }: MetricCellProps) {
  return (
    <div className={clsx("px-3 py-2.5", className)}>
      <div className="text-[0.56rem] tracking-[0.16em] uppercase font-semibold text-muted">{label}</div>
      <div className="font-mono text-[1.15rem] font-medium text-ink mt-0.5 leading-none">{value}</div>
      {caption ? <div className="text-[0.68rem] text-muted mt-1">{caption}</div> : null}
    </div>
  );
}
