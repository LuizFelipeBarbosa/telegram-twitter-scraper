import type { NodeDetail } from "../lib/types";
import { Link } from "react-router-dom";
import { Eyebrow, PhaseBadge } from "../ui";

interface NodeHeaderBandProps {
  detail: NodeDetail;
  phase?: string | null;
}

export function NodeHeaderBand({ detail, phase }: NodeHeaderBandProps) {
  const showPhase = detail.kind === "theme" && phase != null;
  const showParent = detail.kind === "event" && detail.parent_event != null;
  const childEvents = detail.child_events ?? [];
  return (
    <div className="px-5 pt-3 pb-5 grid grid-cols-[minmax(0,1fr)_auto] gap-4 items-end">
      <div>
        <Eyebrow>{`NODE DETAIL · ${detail.kind.toUpperCase()}`}</Eyebrow>
        <h1 className="text-[clamp(1.8rem,4vw,2.4rem)] leading-[0.98] tracking-[-0.03em] mt-1">
          {detail.display_name}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[0.76rem] text-muted">
          <span className="font-mono">{detail.slug}</span>
          <span>·</span>
          <span>{detail.article_count} messages</span>
          {detail.kind === "event" && childEvents.length > 0 ? (
            <>
              <span>·</span>
              <span>{childEvents.length} sub-events</span>
            </>
          ) : null}
        </div>
        {showParent ? (
          <div className="mt-2 text-[0.76rem] text-muted">
            Part of{" "}
            <Link
              to={`/node/event/${detail.parent_event?.slug}`}
              className="text-ink underline underline-offset-[3px] decoration-ink/25 hover:decoration-ink/60"
            >
              {detail.parent_event?.display_name}
            </Link>
          </div>
        ) : null}
        {detail.summary ? (
          <p className="mt-3 text-[0.88rem] text-ink/85 max-w-prose leading-relaxed">{detail.summary}</p>
        ) : null}
      </div>
      {showPhase ? <PhaseBadge phase={String(phase)} /> : null}
    </div>
  );
}
