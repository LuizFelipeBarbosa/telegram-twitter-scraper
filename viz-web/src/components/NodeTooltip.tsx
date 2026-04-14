import type { GraphNodeRow } from "../lib/types";
import { KIND_LABEL, PhaseBadge } from "../ui";

interface NodeTooltipProps {
  x: number;
  y: number;
  node: GraphNodeRow;
}

export function NodeTooltip({ x, y, node }: NodeTooltipProps) {
  return (
    <div
      className="fixed z-30 pointer-events-none rounded-sm border border-ink bg-ink text-paper p-3 shadow-lg w-[18rem] max-w-[calc(100vw-2rem)]"
      style={{ left: `${x}px`, top: `${y}px` }}
    >
      <div className="flex items-center justify-between gap-2">
        <strong className="font-display text-[0.95rem] leading-tight">{node.display_name}</strong>
        {node.kind === "theme" && node.phase ? <PhaseBadge phase={String(node.phase)} /> : null}
      </div>
      <div className="mt-1 text-[0.72rem] text-paper/70">{KIND_LABEL[node.kind]}</div>
      <div className="mt-2 flex justify-between gap-2 text-[0.72rem] font-mono text-paper/85">
        <span>score {node.score.toFixed(2)}</span>
        <span>{node.article_count} messages</span>
        {node.heat != null ? <span>heat {node.heat.toFixed(3)}</span> : null}
      </div>
      {node.summary ? <p className="mt-2 text-[0.72rem] text-paper/70">{node.summary}</p> : null}
    </div>
  );
}
