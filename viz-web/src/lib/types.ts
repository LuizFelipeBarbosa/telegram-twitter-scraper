export type WindowKey = "1d" | "3d" | "5d" | "7d" | "14d" | "31d";
export type PhaseKey = "emerging" | "fading" | "sustained" | "flash_event" | "steady";
export type NodeKind = "person" | "nation" | "org" | "place" | "event" | "theme";

export interface ChannelSummary {
  channel_id: number;
  channel_title: string;
  channel_slug?: string | null;
  channel_username?: string | null;
  story_count: number;
}

export interface GraphNodeRow {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  score: number;
  heat?: number | null;
  phase?: PhaseKey | string | null;
}

export interface SnapshotRelation {
  source: string;
  target: string;
  type: string;
  score: number;
}

export interface ThemeHistoryPoint {
  date: string;
  article_count: number;
  centroid_drift: number;
}

export interface NodeStoryRow {
  story_id: string;
  channel_id: number;
  channel_title: string;
  timestamp_start: string;
  timestamp_end: string;
  confidence: number;
  preview_text: string;
  combined_text: string;
  media_refs: Array<{
    media_type: string;
    storage_path?: string | null;
    mime_type?: string | null;
    file_name?: string | null;
  }>;
}

export interface RelatedNodeRow {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  score: number;
  shared_story_count: number;
  latest_story_at?: string | null;
}

export interface NodeDetail {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  events: RelatedNodeRow[];
  people: RelatedNodeRow[];
  nations: RelatedNodeRow[];
  orgs: RelatedNodeRow[];
  places: RelatedNodeRow[];
  themes: RelatedNodeRow[];
  stories: NodeStoryRow[];
}

export interface NodeListRow {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  last_updated?: string | null;
}
