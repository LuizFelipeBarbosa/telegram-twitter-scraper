from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal


NodeKind = Literal["person", "nation", "org", "place", "event", "theme"]
ThemePhase = Literal["emerging", "fading", "sustained", "flash_event", "steady"]


@dataclass(frozen=True)
class DelimiterPattern:
    kind: str
    pattern: str
    case_sensitive: bool = False


@dataclass(frozen=True)
class ChannelProfile:
    channel_id: int
    delimiter_patterns: tuple[DelimiterPattern, ...] = ()
    media_group_window_seconds: int = 60
    time_gap_minutes: int = 10
    similarity_merge_threshold: float = 0.7
    lookback_story_count: int = 5
    notes: str | None = None
    channel_title: str | None = None
    channel_slug: str | None = None
    channel_username: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class MediaRef:
    media_type: str
    storage_path: str | None
    mime_type: str | None = None
    file_name: str | None = None


@dataclass(frozen=True)
class RawMessage:
    channel_id: int
    message_id: int
    timestamp: datetime
    sender_id: int | None
    sender_name: str | None
    text: str | None
    media_refs: tuple[MediaRef, ...] = ()
    forwarded_from: int | None = None
    reply_to_message_id: int | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)
    english_text: str | None = None
    source_language: str | None = None
    translated_at: datetime | None = None

    @property
    def is_media_only(self) -> bool:
        return not (self.text or "").strip() and bool(self.media_refs)


@dataclass(frozen=True)
class ExtractedSemanticNode:
    name: str
    summary: str | None = None
    aliases: tuple[str, ...] = ()
    start_at: datetime | None = None
    end_at: datetime | None = None


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    canonical_name: str
    normalized_name: str
    summary: str | None = None
    aliases: tuple[str, ...] = ()
    status: str = "active"
    label_source: str = "semantic_extract"
    article_count: int = 0
    created_at: datetime | None = None
    last_updated: datetime | None = None
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    parent_node_id: str | None = None


@dataclass(frozen=True)
class NodeRelation:
    source_node_id: str
    target_node_id: str
    relation_type: str
    score: float
    shared_message_count: int
    latest_message_at: datetime | None = None


@dataclass(frozen=True)
class ThemeDailyStat:
    node_id: str
    date: date
    article_count: int
    centroid_drift: float


@dataclass(frozen=True)
class NodeHeatSnapshot:
    node_id: str
    kind: str
    slug: str
    display_name: str
    article_count: int
    heat_1d: float
    heat_3d: float
    heat_5d: float
    heat_7d: float
    heat_14d: float
    heat_31d: float
    phase: str | None = None


@dataclass(frozen=True)
class ThemeHistoryPoint:
    node_id: str
    slug: str
    display_name: str
    date: date
    article_count: int
    centroid_drift: float


@dataclass(frozen=True)
class ChannelSummary:
    channel_id: int
    channel_title: str
    channel_slug: str | None = None
    channel_username: str | None = None
    message_count: int = 0


@dataclass(frozen=True)
class NodeCentroidRecord:
    node_id: str
    kind: NodeKind
    embedding: list[float]
    display_name: str
    normalized_name: str
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None


@dataclass(frozen=True)
class NodeSupportRecord:
    node_id: str
    message_count: int
    channel_count: int
    has_cross_channel_match: bool
    channel_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class NodeMatch:
    node_id: str
    similarity_score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class NodeListEntry:
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: str | None
    article_count: int
    last_updated: datetime | None = None
    child_count: int = 0
    parent_event: "EventHierarchyRef | None" = None


@dataclass(frozen=True)
class EventHierarchyRef:
    node_id: str
    slug: str
    display_name: str
    summary: str | None
    article_count: int
    child_count: int = 0
    last_updated: datetime | None = None


@dataclass(frozen=True)
class EventChildSummary(EventHierarchyRef):
    event_start_at: datetime | None = None
    primary_location: str | None = None
    location_labels: tuple[str, ...] = ()
    organization_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelatedNode:
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: str | None
    article_count: int
    score: float
    shared_message_count: int
    latest_message_at: datetime | None = None


@dataclass(frozen=True)
class NodeDetail:
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: str | None
    article_count: int
    parent_event: EventHierarchyRef | None = None
    child_events: tuple[EventChildSummary, ...] = ()
    events: tuple[RelatedNode, ...] = ()
    people: tuple[RelatedNode, ...] = ()
    nations: tuple[RelatedNode, ...] = ()
    orgs: tuple[RelatedNode, ...] = ()
    places: tuple[RelatedNode, ...] = ()
    themes: tuple[RelatedNode, ...] = ()
    messages: tuple["NodeMessage", ...] = ()


# ============================================================
# Message-atomic pipeline types.
# ============================================================


@dataclass(frozen=True)
class MessageSemanticExtraction:
    """Per-message LLM extraction output (replaces StorySemanticExtraction)."""

    channel_id: int
    message_id: int
    events: tuple[ExtractedSemanticNode, ...] = ()
    people: tuple[ExtractedSemanticNode, ...] = ()
    nations: tuple[ExtractedSemanticNode, ...] = ()
    orgs: tuple[ExtractedSemanticNode, ...] = ()
    places: tuple[ExtractedSemanticNode, ...] = ()
    themes: tuple[ExtractedSemanticNode, ...] = ()
    primary_event: str | None = None


@dataclass(frozen=True)
class MessageSemanticRecord:
    """Persisted extraction payload for a single message."""

    channel_id: int
    message_id: int
    extraction_payload: dict[str, Any] = field(default_factory=dict)
    primary_event_node_id: str | None = None
    extracted_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class MessageEmbeddingRecord:
    """Per-message embedding stored in Pinecone (replaces StoryEmbeddingRecord)."""

    channel_id: int
    message_id: int
    embedding: list[float]
    timestamp: datetime
    node_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MessageNodeAssignment:
    """Links a message to a resolved node (replaces StoryNodeAssignment)."""

    channel_id: int
    message_id: int
    node_id: str
    confidence: float
    assigned_at: datetime | None = None
    is_primary_event: bool = False


@dataclass(frozen=True)
class MessageMatch:
    """Pinecone query result for message embeddings (replaces StoryMatch)."""

    channel_id: int
    message_id: int
    similarity_score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CrossChannelMessageMatch:
    """Cross-channel message similarity match (replaces CrossChannelMatch)."""

    channel_id: int
    message_id: int
    matched_channel_id: int
    matched_message_id: int
    similarity_score: float
    timestamp_delta_seconds: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class NodeMessage:
    """A message linked to a node, for node-detail rendering (replaces NodeStory)."""

    channel_id: int
    message_id: int
    channel_title: str
    timestamp: datetime
    confidence: float
    text: str
    english_text: str | None = None
    media_refs: tuple[MediaRef, ...] = ()


@dataclass(frozen=True)
class MessageGroup:
    """Query-time grouping of messages assigned to the same dominant event-node.

    This replaces the pre-computed StoryUnit abstraction. Produced on-demand
    by KGQueryService.grouped_messages() — not persisted.
    """

    group_id: str  # deterministic: hash(dominant_node_id + time_bucket)
    dominant_node_id: str
    messages: tuple[NodeMessage, ...]
    timestamp_start: datetime
    timestamp_end: datetime
