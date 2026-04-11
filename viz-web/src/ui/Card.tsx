import { clsx } from "clsx";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div className={clsx("bg-card border border-ink/15 rounded-sm px-4 py-3", className)}>{children}</div>
  );
}
