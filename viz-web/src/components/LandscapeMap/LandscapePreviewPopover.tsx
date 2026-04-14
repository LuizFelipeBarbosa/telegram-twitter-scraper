import { useEffect } from "react";
import type { GraphNodeRow } from "../../lib/types";
import { Eyebrow, KIND_LABEL } from "../../ui";

interface LandscapePreviewPopoverProps {
  node: GraphNodeRow;
  x: number;
  y: number;
  onClose: () => void;
  onNavigate: (node: GraphNodeRow) => void;
}

export function LandscapePreviewPopover({ node, x, y, onClose, onNavigate }: LandscapePreviewPopoverProps) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed z-30 bg-card border border-ink rounded-sm shadow-lg p-3 w-[18rem] max-w-[calc(100vw-2rem)]"
      style={{ left: `${x + 12}px`, top: `${y + 12}px` }}
      role="dialog"
      aria-label="Node preview"
    >
      <Eyebrow>Pinned</Eyebrow>
      <h3 className="text-[1.05rem] leading-tight mt-1">{node.display_name}</h3>
      <div className="font-mono text-[0.64rem] text-muted mt-1">
        {KIND_LABEL[node.kind]} · score {node.score.toFixed(2)} · {node.article_count} messages
      </div>
      {node.summary ? (
        <p className="mt-2 text-[0.76rem] text-ink/85 leading-snug">{node.summary}</p>
      ) : null}
      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onNavigate(node)}
          className="font-mono text-[0.68rem] text-ink underline underline-offset-2 decoration-ink/25 hover:decoration-ink/60 bg-transparent border-0 cursor-pointer p-0"
        >
          Open detail →
        </button>
        <button
          type="button"
          onClick={onClose}
          className="font-mono text-[0.62rem] text-muted bg-transparent border border-ink/25 rounded-sm px-1.5 py-0.5 cursor-pointer hover:border-ink/60"
        >
          Dismiss (Esc)
        </button>
      </div>
    </div>
  );
}
