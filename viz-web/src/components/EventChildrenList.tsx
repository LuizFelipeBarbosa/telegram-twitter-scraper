import { Link, useSearchParams, type SetURLSearchParams } from "react-router-dom";
import type { EventChildSummary } from "../lib/types";
import { Eyebrow, Pill } from "../ui";

const LOCATION_PARAM = "subevent_location";
const ORGANIZATION_PARAM = "subevent_organization";
const SORT_PARAM = "subevent_sort";
const GRAPH_PREVIEW_LIMIT = 18;
const GRAPH_WIDTH = 720;
const GRAPH_PARENT_LEFT = 24;
const GRAPH_CHILD_LEFT = 336;
const GRAPH_NODE_WIDTH = 240;
const GRAPH_NODE_HEIGHT = 56;
const GRAPH_ROW_GAP = 18;
const GRAPH_PADDING = 24;
const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

type SortKey = "newest" | "stories" | "location" | "organization";

interface EventChildrenListProps {
  parentDisplayName: string;
  childEvents?: EventChildSummary[] | null;
}

function firstLocation(child: EventChildSummary): string {
  return child.primary_location ?? child.location_labels[0] ?? "";
}

function firstOrganization(child: EventChildSummary): string {
  return child.organization_labels[0] ?? "";
}

function timestampValue(value?: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDate(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return DATE_FORMATTER.format(new Date(parsed));
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((left, right) => left.localeCompare(right));
}

function sortChildren(rows: EventChildSummary[], sort: SortKey): EventChildSummary[] {
  const copy = [...rows];
  copy.sort((left, right) => {
    if (sort === "stories") {
      return (
        right.article_count - left.article_count ||
        timestampValue(right.last_updated) - timestampValue(left.last_updated) ||
        left.display_name.localeCompare(right.display_name)
      );
    }
    if (sort === "location") {
      return (
        firstLocation(left).localeCompare(firstLocation(right)) ||
        timestampValue(right.last_updated) - timestampValue(left.last_updated) ||
        left.display_name.localeCompare(right.display_name)
      );
    }
    if (sort === "organization") {
      return (
        firstOrganization(left).localeCompare(firstOrganization(right)) ||
        timestampValue(right.last_updated) - timestampValue(left.last_updated) ||
        left.display_name.localeCompare(right.display_name)
      );
    }
    return (
      timestampValue(right.last_updated) - timestampValue(left.last_updated) ||
      timestampValue(right.event_start_at) - timestampValue(left.event_start_at) ||
      right.article_count - left.article_count ||
      left.display_name.localeCompare(right.display_name)
    );
  });
  return copy;
}

function updateSearchParam(
  searchParams: URLSearchParams,
  setSearchParams: SetURLSearchParams,
  key: string,
  value: string,
) {
  const next = new URLSearchParams(searchParams);
  if (value) {
    next.set(key, value);
  } else {
    next.delete(key);
  }
  setSearchParams(next, { replace: true });
}

interface EventChildrenGraphProps {
  parentDisplayName: string;
  visibleCount: number;
  childEvents: EventChildSummary[];
}

function EventChildrenGraph({ parentDisplayName, visibleCount, childEvents }: EventChildrenGraphProps) {
  const graphRows = childEvents.slice(0, GRAPH_PREVIEW_LIMIT);
  const graphHeight = Math.max(
    160,
    GRAPH_PADDING * 2 + graphRows.length * (GRAPH_NODE_HEIGHT + GRAPH_ROW_GAP) - GRAPH_ROW_GAP,
  );
  const parentTop = Math.max(GRAPH_PADDING, Math.round((graphHeight - GRAPH_NODE_HEIGHT) / 2));

  return (
    <div className="border border-ink/15 rounded-sm bg-card overflow-hidden">
      <div className="relative overflow-auto max-h-[420px]">
        <div className="relative min-w-[720px]" style={{ height: graphHeight }}>
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox={`0 0 ${GRAPH_WIDTH} ${graphHeight}`}
            aria-hidden="true"
          >
            {graphRows.map((child, index) => {
              const childTop = GRAPH_PADDING + index * (GRAPH_NODE_HEIGHT + GRAPH_ROW_GAP);
              const parentX = GRAPH_PARENT_LEFT + GRAPH_NODE_WIDTH;
              const parentY = parentTop + GRAPH_NODE_HEIGHT / 2;
              const childX = GRAPH_CHILD_LEFT;
              const childY = childTop + GRAPH_NODE_HEIGHT / 2;
              const controlX = Math.round((parentX + childX) / 2);
              return (
                <path
                  key={child.node_id}
                  d={`M ${parentX} ${parentY} C ${controlX} ${parentY}, ${controlX} ${childY}, ${childX} ${childY}`}
                  fill="none"
                  stroke="rgba(26, 23, 21, 0.28)"
                  strokeWidth="1.5"
                />
              );
            })}
          </svg>

          <div
            className="absolute border border-ink bg-surface-2 shadow-[4px_4px_0_rgba(26,23,21,0.08)] px-4 py-3"
            style={{
              left: GRAPH_PARENT_LEFT,
              top: parentTop,
              width: GRAPH_NODE_WIDTH,
              minHeight: GRAPH_NODE_HEIGHT,
            }}
          >
            <div className="text-[0.6rem] uppercase tracking-[0.12em] text-muted">Parent event</div>
            <div className="mt-1 text-[0.86rem] font-medium leading-tight">{parentDisplayName}</div>
          </div>

          {graphRows.map((child, index) => {
            const top = GRAPH_PADDING + index * (GRAPH_NODE_HEIGHT + GRAPH_ROW_GAP);
            return (
              <Link
                key={child.node_id}
                aria-label={`Graph node: ${child.display_name}`}
                to={`/node/event/${child.slug}`}
                className="absolute border border-ink/15 bg-paper px-3 py-2 hover:bg-ink/[0.04] focus:outline-none focus:ring-2 focus:ring-ink/30"
                style={{
                  left: GRAPH_CHILD_LEFT,
                  top,
                  width: GRAPH_NODE_WIDTH,
                  minHeight: GRAPH_NODE_HEIGHT,
                }}
              >
                <div className="text-[0.8rem] font-medium leading-tight">{child.display_name}</div>
                <div className="mt-1 text-[0.64rem] uppercase tracking-[0.08em] text-muted">
                  {firstLocation(child) || "Unscoped"} · {child.article_count} stories
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {visibleCount > graphRows.length ? (
        <div className="border-t border-ink/10 px-4 py-2 text-[0.68rem] text-muted">
          Showing the first {graphRows.length} of {visibleCount} visible sub-events in the graph.
        </div>
      ) : null}
    </div>
  );
}

export function EventChildrenList({ parentDisplayName, childEvents }: EventChildrenListProps) {
  const rows = childEvents ?? [];
  const [searchParams, setSearchParams] = useSearchParams();

  if (rows.length === 0) {
    return null;
  }

  const selectedLocation = searchParams.get(LOCATION_PARAM) ?? "";
  const selectedOrganization = searchParams.get(ORGANIZATION_PARAM) ?? "";
  const selectedSort = (searchParams.get(SORT_PARAM) as SortKey | null) ?? "newest";

  const locationOptions = uniqueSorted(
    rows.flatMap((child) => {
      if (child.location_labels.length > 0) {
        return child.location_labels;
      }
      return child.primary_location ? [child.primary_location] : [];
    }),
  );
  const organizationOptions = uniqueSorted(rows.flatMap((child) => child.organization_labels));

  const filteredRows = rows.filter((child) => {
    const matchesLocation =
      !selectedLocation ||
      child.primary_location === selectedLocation ||
      child.location_labels.includes(selectedLocation);
    const matchesOrganization = !selectedOrganization || child.organization_labels.includes(selectedOrganization);
    return matchesLocation && matchesOrganization;
  });
  const sortedRows = sortChildren(filteredRows, selectedSort);

  return (
    <section>
      <div className="border-b border-ink pb-2 mb-4">
        <Eyebrow>Sub-events</Eyebrow>
        <h2 className="text-[1.1rem] mt-0.5">Sub-event explorer</h2>
        <p className="mt-1 text-[0.78rem] text-muted">
          Browse grouped sub-events by location or organization without leaving the parent event.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section aria-label="Sub-event graph">
          <div className="flex items-baseline justify-between mb-2">
            <div>
              <div className="text-[0.62rem] uppercase tracking-[0.14em] text-muted">Graph</div>
              <h3 className="text-[1rem] mt-0.5">Sub-event graph</h3>
            </div>
            <div className="text-[0.68rem] font-mono text-muted">{sortedRows.length} visible sub-events</div>
          </div>

          {sortedRows.length > 0 ? (
            <EventChildrenGraph
              parentDisplayName={parentDisplayName}
              visibleCount={sortedRows.length}
              childEvents={sortedRows}
            />
          ) : (
            <div className="border border-dashed border-ink/20 rounded-sm bg-card px-4 py-6 text-[0.78rem] text-muted">
              No sub-events match the current filters.
            </div>
          )}
        </section>

        <section aria-label="Sub-event browser">
          <div className="flex flex-col gap-3 mb-3">
            <div>
              <div className="text-[0.62rem] uppercase tracking-[0.14em] text-muted">Browser</div>
              <h3 className="text-[1rem] mt-0.5">Sub-event browser</h3>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <label className="flex flex-col gap-1 text-[0.68rem] uppercase tracking-[0.08em] text-muted">
                Location
                <select
                  aria-label="Location filter"
                  className="border border-ink/20 bg-card px-3 py-2 text-[0.8rem] text-ink"
                  value={selectedLocation}
                  onChange={(event) =>
                    updateSearchParam(searchParams, setSearchParams, LOCATION_PARAM, event.target.value)
                  }
                >
                  <option value="">All locations</option>
                  {locationOptions.map((location) => (
                    <option key={location} value={location}>
                      {location}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-[0.68rem] uppercase tracking-[0.08em] text-muted">
                Organization
                <select
                  aria-label="Organization filter"
                  className="border border-ink/20 bg-card px-3 py-2 text-[0.8rem] text-ink"
                  value={selectedOrganization}
                  onChange={(event) =>
                    updateSearchParam(searchParams, setSearchParams, ORGANIZATION_PARAM, event.target.value)
                  }
                >
                  <option value="">All organizations</option>
                  {organizationOptions.map((organization) => (
                    <option key={organization} value={organization}>
                      {organization}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-[0.68rem] uppercase tracking-[0.08em] text-muted">
                Sort
                <select
                  aria-label="Sort sub-events"
                  className="border border-ink/20 bg-card px-3 py-2 text-[0.8rem] text-ink"
                  value={selectedSort}
                  onChange={(event) => updateSearchParam(searchParams, setSearchParams, SORT_PARAM, event.target.value)}
                >
                  <option value="newest">Newest first</option>
                  <option value="stories">Story count</option>
                  <option value="location">Location A-Z</option>
                  <option value="organization">Organization A-Z</option>
                </select>
              </label>
            </div>
          </div>

          {sortedRows.length > 0 ? (
            <ul className="list-none p-0 m-0 border border-ink/10 rounded-sm overflow-hidden">
              {sortedRows.map((child) => {
                const eventDate = formatDate(child.event_start_at ?? child.last_updated);
                return (
                  <li key={child.node_id} className="border-b border-ink/10 last:border-b-0">
                    <Link
                      to={`/node/event/${child.slug}`}
                      className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 hover:bg-ink/[0.04] focus:outline-none focus:bg-ink/[0.04]"
                    >
                      <div className="min-w-0">
                        <div className="text-[0.9rem] font-medium leading-tight">{child.display_name}</div>
                        {child.summary ? (
                          <div className="mt-1 text-[0.75rem] text-muted">
                            {child.summary.length > 132 ? `${child.summary.slice(0, 132)}...` : child.summary}
                          </div>
                        ) : null}
                        <div className="mt-2 flex flex-wrap gap-2">
                          {child.primary_location ? (
                            <Pill className="border-ink/15 bg-surface-2 text-ink normal-case tracking-normal">
                              {child.primary_location}
                            </Pill>
                          ) : null}
                          {child.organization_labels.slice(0, 3).map((organization) => (
                            <Pill
                              key={`${child.node_id}-${organization}`}
                              className="border-ink/15 bg-paper text-muted normal-case tracking-normal"
                            >
                              {organization}
                            </Pill>
                          ))}
                        </div>
                      </div>

                      <div className="text-right flex flex-col items-end gap-1 whitespace-nowrap">
                        <div className="font-mono text-[0.68rem] text-muted">{child.article_count} stories</div>
                        {eventDate ? <div className="text-[0.68rem] text-muted">{eventDate}</div> : null}
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="border border-dashed border-ink/20 rounded-sm bg-card px-4 py-6 text-[0.78rem] text-muted">
              No sub-events match the current filters.
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
