from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Protocol, Sequence

from telegram_scraper.kg.models import (
    ChannelProfile,
    ChannelSummary,
    CrossChannelMessageMatch,
    MessageEmbeddingRecord,
    MessageMatch,
    MessageNodeAssignment,
    MessageSemanticExtraction,
    MessageSemanticRecord,
    Node,
    NodeCentroidRecord,
    NodeDetail,
    NodeHeatSnapshot,
    NodeKind,
    NodeListEntry,
    NodeMatch,
    NodeRelation,
    NodeSupportRecord,
    RawMessage,
    ThemeDailyStat,
    ThemeHistoryPoint,
)


class Repository(Protocol):
    def ensure_schema(self) -> None: ...

    def upsert_channel_profile(self, profile: ChannelProfile) -> None: ...

    def get_channel_profile(self, channel_id: int) -> ChannelProfile | None: ...

    def list_channels(self) -> list[ChannelSummary]: ...

    def list_candidate_channel_ids(self) -> list[int]: ...

    def list_node_ids_for_channels(
        self,
        *,
        channel_ids: Sequence[int],
        status: str | None = "active",
    ) -> list[str]: ...

    def upsert_raw_messages(self, messages: Sequence[RawMessage]) -> None: ...

    def list_recent_raw_messages(self, channel_id: int, *, limit: int) -> list[RawMessage]: ...

    def list_raw_messages(self, channel_id: int) -> list[RawMessage]: ...

    def save_raw_message_translations(self, messages: Sequence[RawMessage]) -> None: ...

    def save_nodes(self, nodes: Sequence[Node]) -> None: ...

    def get_nodes(self, node_ids: Sequence[str]) -> list[Node]: ...

    def list_nodes(
        self,
        *,
        kind: NodeKind | None = None,
        status: str | None = "active",
        limit: int | None = None,
    ) -> list[Node]: ...

    def get_node_by_slug(self, *, kind: NodeKind, slug: str, status: str | None = "active") -> Node | None: ...

    def get_node_support_records(self, node_ids: Sequence[str]) -> list[NodeSupportRecord]: ...

    def save_node_relations(self, relations: Sequence[NodeRelation]) -> None: ...

    def replace_node_relations(self, relations: Sequence[NodeRelation]) -> None: ...

    def list_node_relations(self, node_id: str) -> list[NodeRelation]: ...

    def list_relations_for_nodes(self, node_ids: Sequence[str]) -> list[NodeRelation]: ...

    def save_theme_daily_stats(self, stats: Sequence[ThemeDailyStat]) -> None: ...

    def refresh_node_heat_view(self) -> None: ...

    def refresh_theme_heat_view(self) -> None: ...

    def list_node_heat_rows(self, *, kind: str) -> list[NodeHeatSnapshot]: ...

    def delete_nodes(self, node_ids: Sequence[str]) -> None: ...

    def clear_semantic_state(
        self,
        *,
        channel_id: int | None = None,
    ) -> tuple[list[str], list[str], list[str]]: ...

    def run_with_advisory_lock(self, lock_name: str, callback: Callable[[], None]) -> bool: ...

    def list_theme_heat(self, *, phase: str | None = None, limit: int | None = None) -> list[NodeHeatSnapshot]: ...

    def get_theme_history(self, *, slug: str) -> list[ThemeHistoryPoint]: ...

    def list_node_entries(
        self,
        *,
        kind: NodeKind,
        limit: int | None = None,
    ) -> list[NodeListEntry]: ...

    def get_node_detail(self, *, kind: NodeKind, slug: str) -> NodeDetail | None: ...

    # ── Message-atomic pipeline methods ──────────────────────────────────────

    def upsert_message_semantics(self, records: Sequence[MessageSemanticRecord]) -> None: ...

    def get_message_semantic_record(
        self, *, channel_id: int, message_id: int
    ) -> MessageSemanticRecord | None: ...

    def save_message_node_assignments(
        self, assignments: Sequence[MessageNodeAssignment]
    ) -> None: ...

    def list_message_node_assignments(
        self,
        *,
        message_keys: Sequence[tuple[int, int]] | None = None,
        node_ids: Sequence[str] | None = None,
    ) -> list[MessageNodeAssignment]: ...

    def list_message_keys_for_node(self, node_id: str) -> list[tuple[int, int]]: ...

    def save_cross_channel_message_matches(
        self, matches: Sequence[CrossChannelMessageMatch]
    ) -> None: ...

    def list_cross_channel_message_matches(
        self, *, channel_id: int | None = None, message_id: int | None = None
    ) -> list[CrossChannelMessageMatch]: ...

    def mark_message_embedded(self, *, channel_id: int, message_id: int, version: str) -> None: ...

    def mark_messages_extracted(self, keys: Sequence[tuple[int, int]]) -> None: ...

    def list_messages_without_embeddings(
        self, *, channel_id: int | None = None, limit: int | None = None
    ) -> list[RawMessage]: ...

    def list_messages_without_semantics(
        self, *, channel_id: int | None = None, limit: int | None = None
    ) -> list[RawMessage]: ...

    def list_message_keys_for_node_on_date(
        self, node_id: str, day: date
    ) -> list[tuple[int, int]]: ...

    def get_raw_message(
        self, *, channel_id: int, message_id: int
    ) -> RawMessage | None: ...

    def list_raw_messages_by_keys(
        self, keys: Sequence[tuple[int, int]]
    ) -> list[RawMessage]: ...




class StreamEntry(Protocol):
    entry_id: str
    payload: RawMessage


class RawMessageStream(Protocol):
    def ensure_group(self) -> None: ...

    def add(self, message: RawMessage) -> str: ...

    def read(self, *, consumer_name: str, count: int) -> list[object]: ...

    def ack(self, entry_ids: Sequence[str]) -> None: ...


class Embedder(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class SemanticExtractor(Protocol):
    # New message-atomic API (structured output).
    def extract_message(self, message: RawMessage) -> MessageSemanticExtraction: ...

    def extract_messages(
        self,
        messages: Sequence[RawMessage],
        *,
        max_workers: int | None = None,
    ) -> list[MessageSemanticExtraction]: ...


class MessageTranslator(Protocol):
    def translate_messages(self, messages: Sequence[RawMessage]) -> list[RawMessage]: ...


class VectorStore(Protocol):
    def upsert_theme_centroids(self, records: Sequence[NodeCentroidRecord]) -> None: ...

    def fetch_theme_centroids(self, node_ids: Sequence[str]) -> dict[str, list[float]]: ...

    def query_theme_centroids(self, embedding: list[float], *, top_k: int) -> list[NodeMatch]: ...

    def upsert_event_centroids(self, records: Sequence[NodeCentroidRecord]) -> None: ...

    def fetch_event_centroids(self, node_ids: Sequence[str]) -> dict[str, list[float]]: ...

    def query_event_centroids(self, embedding: list[float], *, top_k: int) -> list[NodeMatch]: ...

    def delete_theme_centroids(self, node_ids: Sequence[str]) -> None: ...

    def delete_event_centroids(self, node_ids: Sequence[str]) -> None: ...

    # ── Message-atomic pipeline methods ──────────────────────────────────────

    def upsert_message_embeddings(self, records: Sequence[MessageEmbeddingRecord]) -> None: ...

    def fetch_message_embeddings(
        self, keys: Sequence[tuple[int, int]]
    ) -> dict[tuple[int, int], list[float]]: ...

    def query_message_embeddings(
        self,
        embedding: list[float],
        *,
        top_k: int,
        exclude_channel_id: int | None = None,
        timestamp_gte: datetime | None = None,
    ) -> list[MessageMatch]: ...

    def delete_message_embeddings(self, keys: Sequence[tuple[int, int]]) -> None: ...

    def update_message_node_ids(
        self, *, channel_id: int, message_id: int, node_ids: Sequence[str]
    ) -> None: ...
