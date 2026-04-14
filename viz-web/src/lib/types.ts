export type WindowKey = "1d" | "3d" | "5d" | "7d" | "14d" | "31d";
export type PhaseKey = "emerging" | "fading" | "sustained" | "flash_event" | "steady";
export type NodeKind = "person" | "nation" | "org" | "place" | "event" | "theme";

export interface ChannelSummary {
  channel_id: number;
  channel_title: string;
  channel_slug?: string | null;
  channel_username?: string | null;
  message_count: number;
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
  child_count: number;
  parent_event?: EventHierarchyRef | null;
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

export interface MessageMediaRef {
  media_type: string;
  storage_path?: string | null;
  mime_type?: string | null;
  file_name?: string | null;
}

export interface NodeMessageRow {
  channel_id: number;
  message_id: number;
  channel_title: string;
  timestamp: string;
  confidence: number;
  text: string;
  english_text?: string | null;
  media_refs: MessageMediaRef[];
}

export interface MessageGroup {
  group_id: string;
  dominant_node_id: string;
  messages: NodeMessageRow[];
  timestamp_start: string;
  timestamp_end: string;
}

export interface GroupedMessagesResponse {
  groups: MessageGroup[];
}

export interface RelatedNodeRow {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  score: number;
  shared_message_count: number;
  latest_message_at?: string | null;
}

export interface EventHierarchyRef {
  node_id: string;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  child_count: number;
  last_updated?: string | null;
}

export interface EventChildSummary extends EventHierarchyRef {
  event_start_at?: string | null;
  primary_location?: string | null;
  location_labels: string[];
  organization_labels: string[];
}

export interface NodeDetail {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  parent_event?: EventHierarchyRef | null;
  child_events: EventChildSummary[];
  events: RelatedNodeRow[];
  people: RelatedNodeRow[];
  nations: RelatedNodeRow[];
  orgs: RelatedNodeRow[];
  places: RelatedNodeRow[];
  themes: RelatedNodeRow[];
  messages: NodeMessageRow[];
}

export interface NodeListRow {
  node_id: string;
  kind: NodeKind;
  slug: string;
  display_name: string;
  summary?: string | null;
  article_count: number;
  last_updated?: string | null;
  child_count: number;
  parent_event?: EventHierarchyRef | null;
}
