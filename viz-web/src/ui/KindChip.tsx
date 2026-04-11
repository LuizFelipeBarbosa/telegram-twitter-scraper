import { clsx } from "clsx";
import type { NodeKind } from "../lib/types";
import { KIND_LABEL, KIND_STROKE } from "./kindColors";

interface KindChipProps {
  kind: NodeKind;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

export function KindChip({ kind, active = false, onClick, className }: KindChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "inline-flex items-center gap-1.5 px-2 py-1 text-[0.72rem] rounded-sm border transition-colors",
        active ? "bg-ink text-paper border-ink" : "bg-transparent text-ink border-ink/25 hover:border-ink/60",
        className,
      )}
      aria-pressed={active}
    >
      <span
        data-dot="true"
        className="inline-block w-[0.45rem] h-[0.45rem] rounded-full"
        style={{ backgroundColor: KIND_STROKE[kind] }}
      />
      <span>{KIND_LABEL[kind]}</span>
    </button>
  );
}
