import { clsx } from "clsx";
import type { ReactNode } from "react";

interface EyebrowProps {
  children: ReactNode;
  className?: string;
}

export function Eyebrow({ children, className }: EyebrowProps) {
  return (
    <p className={clsx("uppercase tracking-[0.16em] text-[0.62rem] font-semibold text-muted", className)}>
      {children}
    </p>
  );
}
