import { clsx } from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "ink" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  active?: boolean;
  children: ReactNode;
}

export function Button({ variant = "ink", active = false, className, children, type, ...rest }: ButtonProps) {
  const base = "inline-flex items-center gap-1.5 px-3 py-2 text-[0.78rem] font-medium rounded-sm transition-transform duration-150 ease-out hover:-translate-y-px disabled:opacity-40 disabled:cursor-not-allowed";
  const ink = "bg-ink text-paper border border-ink";
  const ghost = active
    ? "bg-ink text-paper border border-ink"
    : "bg-transparent text-ink border border-ink/25 hover:border-ink/60";
  return (
    <button type={type ?? "button"} className={clsx(base, variant === "ink" ? ink : ghost, className)} {...rest}>
      {children}
    </button>
  );
}
