from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Window = Literal["1d", "3d", "5d", "7d", "14d", "31d"]
Phase = Literal["emerging", "fading", "sustained", "flash_event", "steady"]
NodeKind = Literal["person", "nation", "org", "place", "event", "theme"]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ChannelSummary(BaseModel):
    channel_id: int
    channel_title: str
    channel_slug: Optional[str] = None
    channel_username: Optional[str] = None
    message_count: int


class ChannelsResponse(BaseModel):
    channels: List[ChannelSummary]


class ThemeHeatRow(BaseModel):
    node_id: str
    slug: str
    display_name: str
    article_count: int
    heat: float
    phase: str


class ThemesHeatResponse(BaseModel):
    window: Window
    total: int
    themes: List[ThemeHeatRow]
    topics: Optional[List[ThemeHeatRow]] = None


class NodeHeatRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    article_count: int
    heat: float
    phase: Optional[str] = None


class NodesHeatResponse(BaseModel):
    window: Window
    kind: NodeKind
    total: int
    nodes: List[NodeHeatRow]


class EventHierarchyRefRow(BaseModel):
    node_id: str
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    child_count: int = 0
    last_updated: Optional[datetime] = None


class EventChildSummaryRow(EventHierarchyRefRow):
    event_start_at: Optional[datetime] = None
    primary_location: Optional[str] = None
    location_labels: List[str] = Field(default_factory=list)
    organization_labels: List[str] = Field(default_factory=list)


class GraphNodeRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    score: float
    heat: Optional[float] = None
    phase: Optional[str] = None
    child_count: int = 0
    parent_event: Optional["EventHierarchyRefRow"] = None


class SnapshotRelation(BaseModel):
    source: str
    target: str
    type: str
    score: float


class GraphSnapshotResponse(BaseModel):
    window: Window
    nodes: List[GraphNodeRow]
    relations: List[SnapshotRelation]


class ThemeHistoryPointRow(BaseModel):
    date: date
    article_count: int
    centroid_drift: float


class ThemeHistoryResponse(BaseModel):
    node_id: str
    slug: str
    display_name: str
    history: List[ThemeHistoryPointRow]


class MessageMediaRef(BaseModel):
    media_type: str
    storage_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None


class NodeMessageRow(BaseModel):
    channel_id: int
    message_id: int
    channel_title: str
    timestamp: datetime
    confidence: float
    text: str
    english_text: Optional[str] = None
    media_refs: List[MessageMediaRef] = Field(default_factory=list)


class RelatedNodeRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    score: float
    shared_message_count: int
    latest_message_at: Optional[datetime] = None


class NodeDetailResponse(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    parent_event: Optional[EventHierarchyRefRow] = None
    child_events: List[EventChildSummaryRow] = Field(default_factory=list)
    events: List[RelatedNodeRow] = Field(default_factory=list)
    people: List[RelatedNodeRow] = Field(default_factory=list)
    nations: List[RelatedNodeRow] = Field(default_factory=list)
    orgs: List[RelatedNodeRow] = Field(default_factory=list)
    places: List[RelatedNodeRow] = Field(default_factory=list)
    themes: List[RelatedNodeRow] = Field(default_factory=list)
    messages: List[NodeMessageRow] = Field(default_factory=list)


class MessageGroupResponse(BaseModel):
    group_id: str
    dominant_node_id: str
    messages: List[NodeMessageRow]
    timestamp_start: datetime
    timestamp_end: datetime


class GroupedMessagesResponse(BaseModel):
    groups: List[MessageGroupResponse]


class NodeListRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    last_updated: Optional[datetime] = None
    child_count: int = 0
    parent_event: Optional[EventHierarchyRefRow] = None


class NodeListResponse(BaseModel):
    kind: NodeKind
    nodes: List[NodeListRow]
