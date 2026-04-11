import { clsx } from "clsx";
import { Pill } from "./Pill";

interface PhaseBadgeProps {
  phase: string;
  className?: string;
}

const LABEL: Record<string, string> = {
  emerging: "Emerging",
  flash_event: "Flash Event",
  sustained: "Sustained",
  fading: "Fading",
  steady: "Steady",
};

const TINT: Record<string, string> = {
  emerging: "bg-phase-emerging/15 text-phase-emerging border-phase-emerging/30",
  flash_event: "bg-phase-flash/15 text-phase-flash border-phase-flash/30",
  sustained: "bg-phase-sustained/15 text-phase-sustained border-phase-sustained/30",
  fading: "bg-phase-fading/15 text-phase-fading border-phase-fading/30",
  steady: "bg-ink/8 text-muted border-ink/15",
};

export function PhaseBadge({ phase, className }: PhaseBadgeProps) {
  return <Pill className={clsx(TINT[phase] ?? "bg-ink/5 text-muted border-ink/10", className)}>{LABEL[phase] ?? phase}</Pill>;
}
