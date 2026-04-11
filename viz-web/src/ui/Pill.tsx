import { clsx } from "clsx";
import type { ReactNode } from "react";

interface PillProps {
  children: ReactNode;
  className?: string;
}

export function Pill({ children, className }: PillProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center uppercase tracking-[0.08em] text-[0.62rem] font-semibold px-2 py-[0.18rem] rounded-sm border border-transparent",
        className,
      )}
    >
      {children}
    </span>
  );
}
