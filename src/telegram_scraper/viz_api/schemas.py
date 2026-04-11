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
    story_count: int


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


class StoryMediaRef(BaseModel):
    media_type: str
    storage_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None


class NodeStoryRow(BaseModel):
    story_id: str
    channel_id: int
    channel_title: str
    timestamp_start: datetime
    timestamp_end: datetime
    confidence: float
    preview_text: str
    combined_text: str
    original_preview_text: str = ""
    original_combined_text: str = ""
    media_refs: List[StoryMediaRef] = Field(default_factory=list)


class RelatedNodeRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    score: float
    shared_story_count: int
    latest_story_at: Optional[datetime] = None


class NodeDetailResponse(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    events: List[RelatedNodeRow] = Field(default_factory=list)
    people: List[RelatedNodeRow] = Field(default_factory=list)
    nations: List[RelatedNodeRow] = Field(default_factory=list)
    orgs: List[RelatedNodeRow] = Field(default_factory=list)
    places: List[RelatedNodeRow] = Field(default_factory=list)
    themes: List[RelatedNodeRow] = Field(default_factory=list)
    stories: List[NodeStoryRow] = Field(default_factory=list)


class NodeListRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    summary: Optional[str] = None
    article_count: int
    last_updated: Optional[datetime] = None


class NodeListResponse(BaseModel):
    kind: NodeKind
    nodes: List[NodeListRow]
