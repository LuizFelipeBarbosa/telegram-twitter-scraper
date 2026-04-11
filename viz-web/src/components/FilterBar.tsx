import { clsx } from "clsx";
import { KindChip, PhaseBadge, NODE_KINDS } from "../ui";
import type { NodeKind, PhaseKey } from "../lib/types";

const PHASES: PhaseKey[] = ["emerging", "flash_event", "sustained", "fading", "steady"];

const PHASE_ARIA_LABEL: Record<PhaseKey, string> = {
  emerging: "emerging phase filter",
  flash_event: "flash phase filter",
  sustained: "sustained phase filter",
  fading: "fading phase filter",
  steady: "steady phase filter",
};

interface FilterBarProps {
  kinds: Set<NodeKind>;
  phases: Set<string>;
  onKindToggle: (kind: NodeKind) => void;
  onPhaseToggle: (phase: PhaseKey) => void;
  className?: string;
}

export function FilterBar({ kinds, phases, onKindToggle, onPhaseToggle, className }: FilterBarProps) {
  const themeActive = kinds.has("theme");
  return (
    <div className={clsx("px-5 py-3 flex items-center justify-between gap-6 border-b border-ink/15 flex-wrap", className)}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[0.56rem] uppercase tracking-[0.16em] font-semibold text-muted mr-1">Kinds</span>
        {NODE_KINDS.map((kind) => (
          <KindChip
            key={kind}
            kind={kind}
            active={kinds.has(kind)}
            onClick={() => onKindToggle(kind)}
          />
        ))}
      </div>
      <div
        data-testid="phase-group"
        className={clsx("flex items-center gap-2 flex-wrap transition-opacity", !themeActive && "opacity-40")}
      >
        <span className="text-[0.56rem] uppercase tracking-[0.16em] font-semibold text-muted mr-1">
          Phases
          <span className="ml-1 text-muted font-normal normal-case tracking-normal">themes only</span>
        </span>
        {PHASES.map((phase) => (
          <button
            key={phase}
            type="button"
            onClick={() => onPhaseToggle(phase)}
            className={clsx(
              "rounded-sm transition-opacity",
              !phases.has(phase) && "opacity-40",
            )}
            aria-pressed={phases.has(phase)}
            aria-label={PHASE_ARIA_LABEL[phase]}
          >
            <PhaseBadge phase={phase} />
          </button>
        ))}
      </div>
    </div>
  );
}
