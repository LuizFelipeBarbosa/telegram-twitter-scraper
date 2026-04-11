import type { ChannelSummary, GraphNodeRow, NodeDetail, SnapshotRelation, ThemeHistoryPoint, WindowKey } from "./types";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchChannels(): Promise<{ channels: ChannelSummary[] }> {
  return request("/api/channels");
}

export async function fetchSnapshot(params: {
  window: WindowKey;
  phase?: string | null;
  kinds?: string[];
}): Promise<{ window: WindowKey; nodes: GraphNodeRow[]; relations: SnapshotRelation[] }> {
  const query = new URLSearchParams({ window: params.window });
  if (params.phase) {
    query.set("phase", params.phase);
  }
  for (const kind of params.kinds ?? []) {
    query.append("kind", kind);
  }
  return request(`/api/graph/snapshot?${query.toString()}`);
}

export async function fetchNodeDetail(kind: string, slug: string): Promise<NodeDetail> {
  return request(`/api/nodes/${kind}/${slug}`);
}

export async function fetchThemeHistory(slug: string): Promise<{
  node_id: string;
  slug: string;
  display_name: string;
  history: ThemeHistoryPoint[];
}> {
  return request(`/api/themes/${slug}/history`);
}
