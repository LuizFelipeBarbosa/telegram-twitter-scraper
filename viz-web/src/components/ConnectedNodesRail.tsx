import { Link } from "react-router-dom";
import type { NodeDetail, RelatedNodeRow } from "../lib/types";
import { Eyebrow } from "../ui";

type SectionKey = "events" | "people" | "nations" | "orgs" | "places" | "themes";

const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: "events", label: "Events" },
  { key: "people", label: "People" },
  { key: "nations", label: "Nations" },
  { key: "orgs", label: "Organizations" },
  { key: "places", label: "Places" },
  { key: "themes", label: "Themes" },
];

interface ConnectedNodesRailProps {
  detail: NodeDetail;
}

export function ConnectedNodesRail({ detail }: ConnectedNodesRailProps) {
  return (
    <div className="flex flex-col gap-5">
      {SECTIONS.map(({ key, label }) => {
        const rows = detail[key];
        return <Section key={key} label={label} rows={rows} />;
      })}
    </div>
  );
}

interface SectionProps {
  label: string;
  rows: RelatedNodeRow[];
}

function Section({ label, rows }: SectionProps) {
  const maxScore = rows.length > 0 ? Math.max(...rows.map((row) => row.score)) : 1;
  const visible = rows.slice(0, 6);
  return (
    <div>
      <div className="border-b border-ink pb-1 mb-1 flex items-baseline justify-between">
        <Eyebrow>{`${label.toUpperCase()} · ${rows.length}`}</Eyebrow>
      </div>
      {visible.length === 0 ? (
        <p className="text-[0.74rem] text-muted py-2">No related nodes in this group.</p>
      ) : (
        <ul className="list-none p-0 m-0">
          {visible.map((row) => {
            const barWidth = maxScore > 0 ? Math.max(4, (row.score / maxScore) * 100) : 0;
            return (
              <li key={row.node_id} className="border-b border-ink/10">
                <Link
                  to={`/node/${row.kind}/${row.slug}`}
                  className="grid grid-cols-[1fr_auto] gap-3 py-2 cursor-pointer hover:bg-ink/[0.04]"
                >
                  <div>
                    <div className="text-[0.8rem] font-medium">{row.display_name}</div>
                    <div className="font-mono text-[0.64rem] text-muted mt-0.5">
                      {row.kind} · {row.shared_story_count} shared stories
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-[0.72rem] text-ink">{row.score.toFixed(2)}</div>
                    <div className="mt-1 w-[3rem] h-[3px] bg-ink/8 relative">
                      <div
                        className="absolute left-0 top-0 bottom-0 bg-phase-sustained"
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
