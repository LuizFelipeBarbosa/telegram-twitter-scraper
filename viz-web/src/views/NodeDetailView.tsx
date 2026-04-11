import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { PhaseBadge } from "../components/PhaseBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { fetchNodeDetail, fetchThemeHistory } from "../lib/api";
import type { NodeDetail, RelatedNodeRow } from "../lib/types";

const sectionLabels: Array<{ key: keyof Pick<NodeDetail, "events" | "people" | "nations" | "orgs" | "places" | "themes">; label: string }> = [
  { key: "events", label: "Events" },
  { key: "people", label: "People" },
  { key: "nations", label: "Nations" },
  { key: "orgs", label: "Organizations" },
  { key: "places", label: "Places" },
  { key: "themes", label: "Themes" },
];

export function NodeDetailView() {
  const { kind, slug } = useParams<{ kind: string; slug: string }>();
  const [expandedStoryIds, setExpandedStoryIds] = useState<Set<string>>(new Set());

  const detailState = useAsyncResource(() => fetchNodeDetail(kind ?? "", slug ?? ""), [kind, slug]);
  const historyState = useAsyncResource(
    () => (kind === "theme" && slug ? fetchThemeHistory(slug) : Promise.resolve(null)),
    [kind, slug],
  );

  const chartData = useMemo(
    () =>
      (historyState.data?.history ?? []).map((point) => ({
        ...point,
        dateLabel: new Date(point.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      })),
    [historyState.data?.history],
  );

  if (!kind || !slug) {
    return <EmptyState title="Node not found" message="Choose a node from the landscape to inspect it in detail." />;
  }

  if (detailState.loading || historyState.loading) {
    return <LoadingState />;
  }

  if (detailState.error || !detailState.data) {
    return <EmptyState title="Node detail unavailable" message="This node could not be loaded from the visualization API." />;
  }

  const detail = detailState.data;

  return (
    <section className="topic-detail-view">
      <div className="detail-header-card">
        <div className="detail-header-main">
          <p className="eyebrow">Node Detail</p>
          <h1>{detail.display_name}</h1>
          <div className="detail-meta-row">
            <span>{detail.kind}</span>
            <span>{detail.article_count} stories</span>
            {detail.kind === "theme" ? <PhaseBadge phase="steady" /> : null}
          </div>
          {detail.summary ? <p className="muted">{detail.summary}</p> : null}
        </div>
      </div>

      <div className="detail-grid">
        {detail.kind === "theme" ? (
          <section className="chart-card">
            <div className="section-header">
              <div>
                <p className="eyebrow">Theme History</p>
                <h2>Heat context over time</h2>
              </div>
            </div>

            {chartData.length === 0 ? (
              <EmptyState title="No history yet" message="This theme does not have daily stats populated yet." />
            ) : (
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={chartData}>
                  <XAxis dataKey="dateLabel" tickLine={false} axisLine={false} />
                  <YAxis yAxisId="left" tickLine={false} axisLine={false} />
                  <YAxis yAxisId="right" orientation="right" tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar yAxisId="left" dataKey="article_count" fill="#0d7c66" radius={[6, 6, 0, 0]} />
                  <Line yAxisId="right" dataKey="centroid_drift" stroke="#ef8354" strokeWidth={3} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </section>
        ) : null}

        <section className="stories-card">
          <div className="section-header">
            <div>
              <p className="eyebrow">Related Sections</p>
              <h2>Connected semantic nodes</h2>
            </div>
          </div>

          <div className="stories-list">
            {sectionLabels.map(({ key, label }) => (
              <NodeSection key={key} label={label} rows={detail[key]} />
            ))}
          </div>
        </section>
      </div>

      <section className="stories-card">
        <div className="section-header">
          <div>
            <p className="eyebrow">Stories</p>
            <h2>Latest supporting stories</h2>
          </div>
        </div>

        {detail.stories.length === 0 ? (
          <EmptyState title="No stories" message="No story assignments are available for this node yet." />
        ) : (
          <div className="stories-list">
            {detail.stories.map((story) => {
              const expanded = expandedStoryIds.has(story.story_id);
              return (
                <article key={story.story_id} className="story-row">
                  <button
                    type="button"
                    className="story-summary"
                    onClick={() =>
                      setExpandedStoryIds((previous) => {
                        const next = new Set(previous);
                        if (next.has(story.story_id)) {
                          next.delete(story.story_id);
                        } else {
                          next.add(story.story_id);
                        }
                        return next;
                      })
                    }
                  >
                    <div>
                      <time>{new Date(story.timestamp_start).toLocaleString()}</time>
                      <h3>{story.preview_text || "(media-only story)"}</h3>
                    </div>
                    <div className="story-summary-meta">
                      <span>{story.channel_title}</span>
                      <span>{story.confidence.toFixed(2)}</span>
                    </div>
                  </button>
                  {expanded ? (
                    <div className="story-expanded">
                      <p>{story.combined_text || "(media-only story)"}</p>
                      {story.media_refs.length > 0 ? (
                        <ul className="media-list">
                          {story.media_refs.map((media, index) => (
                            <li key={`${story.story_id}-media-${index}`}>
                              {media.file_name ?? media.storage_path ?? media.media_type}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </section>
  );
}

function NodeSection({ label, rows }: { label: string; rows: RelatedNodeRow[] }) {
  if (rows.length === 0) {
    return (
      <article className="story-row">
        <div className="story-expanded">
          <strong>{label}</strong>
          <p className="muted">No related {label.toLowerCase()} for this node.</p>
        </div>
      </article>
    );
  }

  return (
    <article className="story-row">
      <div className="story-expanded">
        <strong>{label}</strong>
        <div className="stories-list">
          {rows.slice(0, 6).map((row) => (
            <Link key={row.node_id} className="related-topic-card" to={`/node/${row.kind}/${row.slug}`}>
              <div>
                <strong>{row.display_name}</strong>
                <p>{row.shared_story_count} shared stories</p>
              </div>
              <div className="related-topic-meta">
                <span>{row.kind}</span>
                <span>{row.score.toFixed(2)}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </article>
  );
}
