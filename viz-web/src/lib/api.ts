import type { ChannelSummary, GraphNodeRow, NodeDetail, SnapshotRelation, ThemeHistoryPoint, WindowKey } from "./types";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function normalizeEventHierarchyRef(value: unknown) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const ref = value as Record<string, unknown>;
  return {
    node_id: typeof ref.node_id === "string" ? ref.node_id : "",
    slug: typeof ref.slug === "string" ? ref.slug : "",
    display_name: typeof ref.display_name === "string" ? ref.display_name : "",
    summary: typeof ref.summary === "string" ? ref.summary : null,
    article_count: typeof ref.article_count === "number" ? ref.article_count : 0,
    child_count: typeof ref.child_count === "number" ? ref.child_count : 0,
    last_updated: typeof ref.last_updated === "string" ? ref.last_updated : null,
  };
}

function normalizeEventChildSummary(value: unknown) {
  const ref = normalizeEventHierarchyRef(value);
  if (!ref || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  return {
    ...ref,
    event_start_at: typeof row.event_start_at === "string" ? row.event_start_at : null,
    primary_location: typeof row.primary_location === "string" ? row.primary_location : null,
    location_labels: Array.isArray(row.location_labels)
      ? row.location_labels.filter((item): item is string => typeof item === "string")
      : [],
    organization_labels: Array.isArray(row.organization_labels)
      ? row.organization_labels.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function normalizeGraphNodeRow(row: GraphNodeRow): GraphNodeRow {
  return {
    ...row,
    child_count: typeof row.child_count === "number" ? row.child_count : 0,
    parent_event: normalizeEventHierarchyRef(row.parent_event),
  };
}

function normalizeNodeDetail(detail: NodeDetail): NodeDetail {
  return {
    ...detail,
    parent_event: normalizeEventHierarchyRef(detail.parent_event),
    child_events: Array.isArray(detail.child_events)
      ? detail.child_events.map((child) => normalizeEventChildSummary(child)).filter((child) => child !== null)
      : [],
    events: Array.isArray(detail.events) ? detail.events : [],
    people: Array.isArray(detail.people) ? detail.people : [],
    nations: Array.isArray(detail.nations) ? detail.nations : [],
    orgs: Array.isArray(detail.orgs) ? detail.orgs : [],
    places: Array.isArray(detail.places) ? detail.places : [],
    themes: Array.isArray(detail.themes) ? detail.themes : [],
    stories: Array.isArray(detail.stories) ? detail.stories : [],
  };
}

export async function fetchChannels(): Promise<{ channels: ChannelSummary[] }> {
  return request("/api/channels");
}

export async function fetchSnapshot(params: {
  window: WindowKey;
  phase?: string | null;
  kinds?: string[];
  includeChildren?: boolean;
}): Promise<{ window: WindowKey; nodes: GraphNodeRow[]; relations: SnapshotRelation[] }> {
  const query = new URLSearchParams({ window: params.window });
  if (params.phase) {
    query.set("phase", params.phase);
  }
  if (params.includeChildren) {
    query.set("include_children", "true");
  }
  for (const kind of params.kinds ?? []) {
    query.append("kind", kind);
  }
  const response = await request<{ window: WindowKey; nodes: GraphNodeRow[]; relations: SnapshotRelation[] }>(
    `/api/graph/snapshot?${query.toString()}`,
  );
  return {
    ...response,
    nodes: Array.isArray(response.nodes) ? response.nodes.map(normalizeGraphNodeRow) : [],
    relations: Array.isArray(response.relations) ? response.relations : [],
  };
}

export async function fetchNodeDetail(kind: string, slug: string): Promise<NodeDetail> {
  const response = await request<NodeDetail>(`/api/nodes/${kind}/${slug}`);
  return normalizeNodeDetail(response);
}

export async function fetchThemeHistory(slug: string): Promise<{
  node_id: string;
  slug: string;
  display_name: string;
  history: ThemeHistoryPoint[];
}> {
  return request(`/api/themes/${slug}/history`);
}
