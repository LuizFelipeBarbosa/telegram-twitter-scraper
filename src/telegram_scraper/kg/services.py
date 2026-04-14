from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import time
import re
from typing import Callable, Literal, Sequence

from telegram_scraper.chat_discovery import discover_chats, filter_chats, resolve_chat
from telegram_scraper.config import Settings
from telegram_scraper.models import ChatRecord, ChatType
from telegram_scraper.telegram_client import TelegramAccountClient, TelegramMessageEnvelope

from telegram_scraper.kg.extraction import preferred_message_text, preferred_story_text, safe_message_text, safe_story_text
from telegram_scraper.kg.event_hierarchy import (
    ACTOR_ADJECTIVES,
    KGEventHierarchyService,
    _detect_generic_family,
    _extract_label_actor,
    _extract_operation_parent_display,
    _family_display,
    _normalize_place_scope,
    _parse_launch_scope,
    _parse_place_scope,
    _titleish,
    build_event_hierarchy_snapshot,
)
from telegram_scraper.kg.interfaces import Embedder, MessageTranslator, RawMessageStream, SemanticExtractor, StoryRepository, VectorStore
from telegram_scraper.kg.math_utils import average_vectors, cosine_similarity
from telegram_scraper.kg.models import (
    ChannelProfile,
    CrossChannelMatch,
    CrossChannelMessageMatch,
    EventChildSummary,
    ExtractedSemanticNode,
    MessageEmbeddingRecord,
    MessageGroup,
    MessageNodeAssignment,
    MessageSemanticExtraction,
    MessageSemanticRecord,
    Node,
    NodeCentroidRecord,
    NodeDetail,
    NodeKind,
    NodeListEntry,
    NodeMessage,
    NodeRelation,
    NodeSupportRecord,
    NodeStory,
    RawMessage,
    RelatedNode,
    StoryEmbeddingRecord,
    StoryNodeAssignment,
    StorySemanticExtraction,
    StorySemanticRecord,
    StoryUnit,
    ThemeDailyStat,
    NodeHeatSnapshot,
    ThemeHistoryPoint,
)
from telegram_scraper.kg.node_resolver import (
    NODE_KINDS,
    NodeResolver,
    iter_extraction_candidates,
    serialize_extraction,
)
from telegram_scraper.kg.normalization import normalize_message_record
from telegram_scraper.kg.segmentation import StorySegmenter, default_channel_profile
from telegram_scraper.utils import ensure_utc

from telegram_scraper.kg.config import KGSettings


ProjectionPolicy = Literal["per_batch", "end_of_run", "manual"]
REPAIR_RAW_MESSAGE_FLUSH_SIZE = 500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _messages_text(messages) -> str:
    return "\n".join((message.english_text or message.text or "").strip() for message in messages if (message.english_text or message.text or "").strip())


def _story_text(story: StoryUnit) -> str:
    return preferred_story_text(story)


def _embedding_text(text: str, *, max_chars: int) -> str:
    cleaned = safe_story_text(text.strip() or "(media only telegram story)", max_chars=max_chars)
    return cleaned or "(media only telegram story)"


def _safe_embed_texts(embedder: Embedder, texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        embeddings = list(embedder.embed_texts(texts))
        if len(embeddings) == len(texts):
            return embeddings
    except Exception:
        pass
    fallback: list[list[float]] = []
    for text in texts:
        try:
            fallback.append(embedder.embed_texts([text])[0])
        except Exception:
            fallback.append([])
    return fallback


def _channel_selection(settings: Settings, chats: Sequence[ChatRecord]) -> list[ChatRecord]:
    return filter_chats(
        list(chats),
        chat_types=(ChatType.CHANNEL,),
        include_chats=settings.include_chats,
        exclude_chats=settings.exclude_chats,
    )


def _profile_with_chat_metadata(profile: ChannelProfile, chat: ChatRecord) -> ChannelProfile:
    return replace(
        profile,
        channel_title=chat.title or profile.channel_title,
        channel_slug=chat.slug or profile.channel_slug,
        channel_username=chat.username or profile.channel_username,
    )


def _normalize_name(value: str) -> str:
    lowered = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", normalized).strip()


def _dedupe_aliases(*values: str) -> tuple[str, ...]:
    seen: set[str] = set()
    aliases: list[str] = []
    for value in values:
        stripped = value.strip()
        normalized = _normalize_name(stripped)
        if not stripped or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(stripped)
    return tuple(aliases)


def _clean_candidate(candidate: ExtractedSemanticNode) -> ExtractedSemanticNode:
    summary = candidate.summary.strip() if candidate.summary else None
    return ExtractedSemanticNode(
        name=candidate.name.strip(),
        summary=summary or None,
        aliases=_dedupe_aliases(*candidate.aliases),
        start_at=candidate.start_at,
        end_at=candidate.end_at,
    )


def _candidate_embedding_text(candidate: ExtractedSemanticNode, *, story: StoryUnit, max_chars: int) -> str:
    context = _story_text(story).strip()
    if len(context) > 800:
        context = context[-800:]
    parts = [candidate.name.strip()]
    if candidate.summary:
        parts.append(candidate.summary.strip())
    if context:
        parts.append(f"Context: {context}")
    return _embedding_text("\n".join(part for part in parts if part), max_chars=max_chars)


def _event_actor_from_extraction(
    extraction: StorySemanticExtraction,
    *,
    normalized_label: str,
) -> tuple[str, str] | None:
    for item in extraction.nations:
        for value in (item.name, *item.aliases):
            normalized = _normalize_name(value)
            if normalized and normalized in normalized_label:
                return normalized, ACTOR_ADJECTIVES.get(normalized, value.strip())
    for item in extraction.orgs:
        for value in (item.name, *item.aliases):
            normalized = _normalize_name(value)
            if normalized and normalized in normalized_label:
                return normalized, value.strip()
    return None


def _event_place_from_extraction(
    extraction: StorySemanticExtraction,
    *,
    normalized_label: str,
) -> tuple[str, str] | None:
    for item in extraction.places:
        for value in (item.name, *item.aliases):
            normalized = _normalize_name(value)
            if not normalized or normalized not in normalized_label:
                continue
            place_scope = _normalize_place_scope(value)
            if place_scope is not None:
                return place_scope
    return None


def _canonicalize_event_candidate(
    candidate: ExtractedSemanticNode,
    *,
    extraction: StorySemanticExtraction,
) -> tuple[ExtractedSemanticNode, bool]:
    cleaned = _clean_candidate(candidate)
    normalized_name = _normalize_name(cleaned.name)
    if not normalized_name:
        return cleaned, False

    operation_display = _extract_operation_parent_display(cleaned.name)
    if operation_display:
        return (
            ExtractedSemanticNode(
                name=operation_display,
                summary=cleaned.summary if _normalize_name(operation_display) == normalized_name else None,
                aliases=_dedupe_aliases(*cleaned.aliases, cleaned.name if _normalize_name(operation_display) != normalized_name else ""),
                start_at=cleaned.start_at,
                end_at=cleaned.end_at,
            ),
            True,
        )

    family = _detect_generic_family(cleaned.name)
    if family is None:
        return cleaned, False

    actor = _extract_label_actor(cleaned.name) or _event_actor_from_extraction(extraction, normalized_label=normalized_name)
    if family in {"airstrike", "strike"} and actor is None:
        return cleaned, False

    source_label: str | None = None
    place_scope: tuple[str, str] | None = None
    if family == "launch":
        source_scope, target_scope = _parse_launch_scope(cleaned.name)
        if source_scope:
            source_label = _titleish(source_scope)
        if target_scope:
            place_scope = _normalize_place_scope(target_scope)
    if place_scope is None:
        parsed_place = _parse_place_scope(cleaned.name)
        if parsed_place:
            place_scope = _normalize_place_scope(parsed_place)
    if place_scope is None:
        place_scope = _event_place_from_extraction(extraction, normalized_label=normalized_name)

    display_name = _family_display(
        family=family,
        actor_label=actor[1] if actor is not None else None,
        place_label=place_scope[1] if place_scope is not None else None,
        source_label=source_label,
    )
    if not display_name:
        return cleaned, False

    return (
        ExtractedSemanticNode(
            name=display_name,
            summary=None,
            aliases=_dedupe_aliases(*cleaned.aliases, cleaned.name if _normalize_name(display_name) != normalized_name else ""),
            start_at=cleaned.start_at,
            end_at=cleaned.end_at,
        ),
        True,
    )


def _channel_title_for_story(channel_id: int, profile: ChannelProfile | None) -> str:
    if profile is not None:
        for value in (profile.channel_title, profile.channel_slug, profile.channel_username):
            if value:
                return value
    return str(channel_id)


def _preview_text(text: str, *, limit: int = 200) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def _sort_related(nodes: list[RelatedNode]) -> list[RelatedNode]:
    return sorted(
        nodes,
        key=lambda item: (
            -item.score,
            -(item.latest_story_at.timestamp() if item.latest_story_at is not None else 0.0),
            item.display_name.lower(),
        ),
    )


def _ordered_counter_labels(counter: Counter[str]) -> tuple[str, ...]:
    return tuple(
        label
        for label, _count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
    )


def _implicit_parent_actor_keys(node: Node) -> set[str]:
    if _detect_generic_family(node.display_name) not in {"strike", "airstrike"}:
        return set()
    actor = _extract_label_actor(node.display_name)
    if actor is None:
        return set()
    return {actor[0]}


def _child_event_location_labels(
    *,
    child: Node,
    child_story_ids: set[str],
    assignments_by_story: dict[str, list[StoryNodeAssignment]],
    related_nodes: dict[str, Node],
) -> tuple[str, ...]:
    labels: Counter[str] = Counter()
    for story_id in child_story_ids:
        seen_labels: set[str] = set()
        for assignment in assignments_by_story.get(story_id, []):
            related = related_nodes.get(assignment.node_id)
            if related is None or related.node_id == child.node_id or related.status != "active" or related.kind != "place":
                continue
            normalized = _normalize_place_scope(related.display_name)
            if normalized is None:
                continue
            place_label = normalized[1]
            if place_label in seen_labels:
                continue
            labels[place_label] += 1
            seen_labels.add(place_label)

    parsed_place = _parse_place_scope(child.display_name)
    if parsed_place is not None:
        normalized = _normalize_place_scope(parsed_place)
        if normalized is not None and normalized[1] not in labels:
            labels[normalized[1]] = 1

    return _ordered_counter_labels(labels)


def _child_event_organization_labels(
    *,
    child: Node,
    child_story_ids: set[str],
    assignments_by_story: dict[str, list[StoryNodeAssignment]],
    related_nodes: dict[str, Node],
    excluded_actor_keys: set[str],
) -> tuple[str, ...]:
    labels: Counter[str] = Counter()
    seen_keys_per_story: dict[str, set[str]] = defaultdict(set)
    for story_id in child_story_ids:
        for assignment in assignments_by_story.get(story_id, []):
            related = related_nodes.get(assignment.node_id)
            if (
                related is None
                or related.node_id == child.node_id
                or related.status != "active"
                or related.kind not in {"nation", "org"}
            ):
                continue
            actor_key = related.normalized_name
            if actor_key in excluded_actor_keys or actor_key in seen_keys_per_story[story_id]:
                continue
            labels[related.display_name] += 1
            seen_keys_per_story[story_id].add(actor_key)

    parsed_actor = _extract_label_actor(child.display_name)
    if parsed_actor is not None and parsed_actor[0] not in excluded_actor_keys and parsed_actor[1] not in labels:
        labels[parsed_actor[1]] = 1

    return _ordered_counter_labels(labels)


def _build_event_child_summary(
    *,
    child: Node,
    child_story_ids: set[str],
    assignments_by_story: dict[str, list[StoryNodeAssignment]],
    related_nodes: dict[str, Node],
    excluded_actor_keys: set[str],
) -> EventChildSummary:
    location_labels = _child_event_location_labels(
        child=child,
        child_story_ids=child_story_ids,
        assignments_by_story=assignments_by_story,
        related_nodes=related_nodes,
    )
    organization_labels = _child_event_organization_labels(
        child=child,
        child_story_ids=child_story_ids,
        assignments_by_story=assignments_by_story,
        related_nodes=related_nodes,
        excluded_actor_keys=excluded_actor_keys,
    )
    return EventChildSummary(
        node_id=child.node_id,
        slug=child.slug,
        display_name=child.display_name,
        summary=child.summary,
        article_count=len(child_story_ids),
        child_count=0,
        last_updated=child.last_updated,
        event_start_at=child.event_start_at,
        primary_location=location_labels[0] if location_labels else None,
        location_labels=location_labels,
        organization_labels=organization_labels,
    )


def _canonical_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _chunked(items: Sequence[StoryUnit], size: int) -> list[list[StoryUnit]]:
    return [list(items[index : index + size]) for index in range(0, len(items), max(size, 1))]


def _ensure_translated_messages(
    repository: StoryRepository,
    translator: MessageTranslator | None,
    messages: Sequence[RawMessage],
) -> list[RawMessage]:
    if not messages or translator is None:
        return list(messages)
    translated = list(translator.translate_messages(messages))
    repository.save_raw_message_translations(translated)
    return translated


@dataclass(frozen=True)
class KGBackfillResult:
    chats_processed: int
    messages_streamed: int


@dataclass(frozen=True)
class KGSegmentResult:
    messages_processed: int
    stories_saved: int
    assignments_created: int
    nodes_created: int
    cross_channel_matches: int
    relations_created: int
    theme_stats_written: int


@dataclass(frozen=True)
class KGNodeProcessResult:
    assignments_created: int
    nodes_created: int
    cross_channel_matches: int
    relations_created: int
    theme_stats_written: int


@dataclass(frozen=True)
class KGSegmentPreviewResult:
    profile: ChannelProfile
    stories: tuple[StoryUnit, ...]


@dataclass(frozen=True)
class KGChannelResetResult:
    stories_preserved: int
    nodes_deleted: int


@dataclass(frozen=True)
class KGChannelRebuildResult:
    stories_processed: int
    assignments_created: int
    nodes_created: int
    relations_created: int
    theme_stats_written: int


@dataclass(frozen=True)
class KGProjectionRefreshResult:
    relations_created: int
    theme_stats_written: int


@dataclass(frozen=True)
class KGProcessingOptions:
    extraction_batch_size: int
    extraction_workers: int
    enable_cross_channel_matching: bool
    projection_policy: ProjectionPolicy
    flush_size: int


@dataclass(frozen=True)
class KGProcessingProgress:
    stories_processed: int
    stories_total: int
    assignments_created: int
    nodes_created: int
    cross_channel_matches: int
    failures: int
    rate_per_sec: float


@dataclass(frozen=True)
class KGHistoricalRebuildProgress:
    channel_id: int
    channel_story_total: int
    channel_story_processed: int
    assignments_created: int
    nodes_created: int
    failures: int
    rate_per_sec: float


@dataclass(frozen=True)
class KGHistoricalRebuildResult:
    channels_processed: int
    stories_processed: int
    assignments_created: int
    nodes_created: int
    relations_created: int
    theme_stats_written: int


@dataclass(frozen=True)
class KGChannelRepairResult:
    channels_processed: int
    messages_upserted: int
    stories_rebuilt: int
    assignments_created: int
    nodes_created: int
    relations_created: int
    theme_stats_written: int


@dataclass(frozen=True)
class KGChannelSyncStatus:
    channel_id: int
    channel_title: str
    telegram_latest_at: datetime | None
    ingested_latest_at: datetime | None
    rebuilt_latest_at: datetime | None
    raw_message_count: int
    story_count: int


@dataclass(frozen=True)
class KGProcessingResult:
    messages_processed: int
    messages_embedded: int
    assignments_created: int
    nodes_created: int
    cross_channel_matches: int
    relations_created: int
    theme_stats_written: int


@dataclass
class _ProcessingState:
    story_embeddings: dict[str, list[float]]
    node_cache: dict[NodeKind, dict[str, Node]]
    theme_centroids: dict[str, list[float]]
    event_centroids: dict[str, list[float]]
    support_records: dict[str, NodeSupportRecord]
    pending_nodes: dict[str, Node]
    pending_assignments: list[StoryNodeAssignment]
    pending_semantics: list[StorySemanticRecord]
    pending_cross_channel_matches: list[CrossChannelMatch]
    pending_story_embeddings: dict[str, StoryEmbeddingRecord]
    pending_theme_centroids: dict[str, NodeCentroidRecord]
    pending_event_centroids: dict[str, NodeCentroidRecord]
    assignments_created: int = 0
    nodes_created: int = 0
    cross_channel_matches: int = 0
    relations_created: int = 0
    theme_stats_written: int = 0


@dataclass
class _MessageProcessingState:
    """Per-batch state for the message-atomic processing pipeline."""
    message_embeddings: dict[tuple[int, int], list[float]]
    node_cache: dict[NodeKind, dict[str, Node]]
    theme_centroids: dict[str, list[float]]
    event_centroids: dict[str, list[float]]
    support_records: dict[str, NodeSupportRecord]
    pending_nodes: dict[str, Node]
    pending_assignments: list[MessageNodeAssignment]
    pending_semantics: list[MessageSemanticRecord]
    pending_cross_channel_matches: list[CrossChannelMessageMatch]
    pending_message_embeddings: dict[tuple[int, int], MessageEmbeddingRecord]
    pending_theme_centroids: dict[str, NodeCentroidRecord]
    pending_event_centroids: dict[str, NodeCentroidRecord]
    assignments_created: int = 0
    nodes_created: int = 0
    cross_channel_matches: int = 0
    relations_created: int = 0
    theme_stats_written: int = 0


@dataclass(frozen=True)
class _PreparedCandidate:
    kind: NodeKind
    source_name: str
    candidate: ExtractedSemanticNode
    embedding: list[float]
    activate_immediately: bool


class KGBackfillService:
    def __init__(
        self,
        settings: Settings,
        telegram_client: TelegramAccountClient,
        stream: RawMessageStream,
        repository: StoryRepository | None = None,
    ):
        self.settings = settings
        self.telegram_client = telegram_client
        self.stream = stream
        self.repository = repository

    async def _target_channels(self) -> list[ChatRecord]:
        dialogs = await self.telegram_client.get_dialogs()
        chats = _channel_selection(self.settings, discover_chats(dialogs))
        self._sync_channel_profiles(chats)
        return chats

    def _sync_channel_profiles(self, chats: Sequence[ChatRecord]) -> None:
        if self.repository is None:
            return
        self.repository.ensure_schema()
        for chat in chats:
            existing = self.repository.get_channel_profile(chat.chat_id) or default_channel_profile(chat.chat_id)
            self.repository.upsert_channel_profile(_profile_with_chat_metadata(existing, chat))

    async def backfill(self, *, limit_per_chat: int | None = None) -> KGBackfillResult:
        chats = await self._target_channels()
        streamed = 0
        newest_first = self.settings.since_date is not None
        for chat in chats:
            async for envelope in self.telegram_client.iter_message_envelopes(
                chat,
                limit=limit_per_chat,
                reverse=not newest_first,
            ):
                posted_at = envelope.record.posted_at
                if self.settings.since_date is not None and posted_at is not None and posted_at < self.settings.since_date:
                    if newest_first:
                        break
                    continue
                self.stream.add(normalize_message_record(envelope.record, raw_json=envelope.raw_json))
                streamed += 1
        return KGBackfillResult(chats_processed=len(chats), messages_streamed=streamed)


class KGListenerService:
    def __init__(
        self,
        settings: Settings,
        telegram_client: TelegramAccountClient,
        stream: RawMessageStream,
        repository: StoryRepository | None = None,
    ):
        self.settings = settings
        self.telegram_client = telegram_client
        self.stream = stream
        self.repository = repository

    async def _target_channels(self) -> list[ChatRecord]:
        dialogs = await self.telegram_client.get_dialogs()
        chats = _channel_selection(self.settings, discover_chats(dialogs))
        self._sync_channel_profiles(chats)
        return chats

    def _sync_channel_profiles(self, chats: Sequence[ChatRecord]) -> None:
        if self.repository is None:
            return
        self.repository.ensure_schema()
        for chat in chats:
            existing = self.repository.get_channel_profile(chat.chat_id) or default_channel_profile(chat.chat_id)
            self.repository.upsert_channel_profile(_profile_with_chat_metadata(existing, chat))

    async def listen(self) -> None:
        chats = await self._target_channels()

        async def _handle(envelope: TelegramMessageEnvelope) -> None:
            self.stream.add(normalize_message_record(envelope.record, raw_json=envelope.raw_json))

        await self.telegram_client.listen_channel_messages(chats, _handle)


class KGProfileService:
    def __init__(self, repository: StoryRepository):
        self.repository = repository

    def show(self, channel_id: int) -> ChannelProfile:
        self.repository.ensure_schema()
        return self.repository.get_channel_profile(channel_id) or default_channel_profile(channel_id)

    def upsert(self, profile: ChannelProfile) -> ChannelProfile:
        self.repository.ensure_schema()
        self.repository.upsert_channel_profile(profile)
        return self.show(profile.channel_id)

    def sync_chat_metadata(self, chats: Sequence[ChatRecord]) -> int:
        self.repository.ensure_schema()
        updated = 0
        for chat in chats:
            existing = self.repository.get_channel_profile(chat.chat_id) or default_channel_profile(chat.chat_id)
            enriched = _profile_with_chat_metadata(existing, chat)
            if enriched != existing:
                self.repository.upsert_channel_profile(enriched)
                updated += 1
        return updated


class KGSegmentationPreviewService:
    def __init__(self, repository: StoryRepository, embedder: Embedder, *, segmenter: StorySegmenter | None = None):
        self.repository = repository
        self.embedder = embedder
        self.segmenter = segmenter or StorySegmenter()

    def preview_channel(self, channel_id: int, *, limit: int = 50) -> KGSegmentPreviewResult:
        self.repository.ensure_schema()
        profile = self.repository.get_channel_profile(channel_id) or default_channel_profile(channel_id)
        messages = self.repository.list_recent_raw_messages(channel_id, limit=limit)
        candidates = self.segmenter.build_candidates(messages, profile)
        candidate_embeddings = self.embedder.embed_texts([_embedding_text(_messages_text(candidate), max_chars=12000) for candidate in candidates])
        merged_groups = self.segmenter.merge_candidates(candidates, candidate_embeddings, profile)
        stories = tuple(self.segmenter.create_story(group, profile=profile) for group in merged_groups)
        return KGSegmentPreviewResult(profile=profile, stories=stories)


class KGNodeProjectionService:
    def __init__(self, repository: StoryRepository, vector_store: VectorStore):
        self.repository = repository
        self.vector_store = vector_store

    def rebuild_node_relations(self) -> int:
        story_nodes: dict[str, list[StoryNodeAssignment]] = {}
        story_units = {story.story_id: story for story in self.repository.list_story_units()}
        active_node_ids = {node.node_id for node in self.repository.list_nodes(status="active")}
        for story_id in story_units:
            assignments = [
                assignment
                for assignment in self.repository.get_story_node_assignments(story_id)
                if assignment.node_id in active_node_ids
            ]
            if assignments:
                story_nodes[story_id] = assignments

        shared_counts: dict[tuple[str, str], int] = defaultdict(int)
        latest_story_at: dict[tuple[str, str], datetime] = {}
        primary_event_by_story: dict[str, str] = {}

        for story_id, assignments in story_nodes.items():
            story = story_units[story_id]
            unique_node_ids = sorted({assignment.node_id for assignment in assignments})
            for assignment in assignments:
                if assignment.is_primary_event:
                    primary_event_by_story[story_id] = assignment.node_id
                    break
            for index, left_id in enumerate(unique_node_ids):
                for right_id in unique_node_ids[index + 1 :]:
                    pair = _canonical_pair(left_id, right_id)
                    shared_counts[pair] += 1
                    current_latest = latest_story_at.get(pair)
                    if current_latest is None or story.timestamp_end > current_latest:
                        latest_story_at[pair] = story.timestamp_end

        cross_bonus: dict[tuple[str, str], int] = defaultdict(int)
        for match in self.repository.list_cross_channel_matches():
            left_event = primary_event_by_story.get(match.story_id)
            right_event = primary_event_by_story.get(match.matched_story_id)
            if left_event is None or right_event is None or left_event == right_event:
                continue
            pair = _canonical_pair(left_event, right_event)
            cross_bonus[pair] += 1
            left_story = story_units.get(match.story_id)
            right_story = story_units.get(match.matched_story_id)
            match_latest = max(
                [story.timestamp_end for story in (left_story, right_story) if story is not None],
                default=None,
            )
            if match_latest is not None:
                current_latest = latest_story_at.get(pair)
                if current_latest is None or match_latest > current_latest:
                    latest_story_at[pair] = match_latest

        relations: list[NodeRelation] = []
        all_pairs = sorted(set(shared_counts) | set(cross_bonus))
        for pair in all_pairs:
            shared_story_count = shared_counts.get(pair, 0)
            score = float(shared_story_count) + (0.5 * cross_bonus.get(pair, 0))
            if score <= 0:
                continue
            relations.append(
                NodeRelation(
                    source_node_id=pair[0],
                    target_node_id=pair[1],
                    relation_type="related",
                    score=score,
                    shared_story_count=shared_story_count,
                    latest_story_at=latest_story_at.get(pair),
                )
            )

        self.repository.replace_node_relations(relations)
        return len(relations)

    def refresh_theme_stats(self, *, days: int = 31) -> int:
        themes = self.repository.list_nodes(kind="theme")
        today = _utc_now().date()
        start = today - timedelta(days=max(days - 1, 0))
        stats: list[ThemeDailyStat] = []

        for offset in range(days):
            day = start + timedelta(days=offset)
            previous_day = day - timedelta(days=1)
            for theme in themes:
                current_story_ids = self.repository.list_story_ids_for_node_on_date(theme.node_id, day)
                previous_story_ids = self.repository.list_story_ids_for_node_on_date(theme.node_id, previous_day)
                current_centroid = average_vectors(self.vector_store.fetch_story_embeddings(current_story_ids).values())
                previous_centroid = average_vectors(self.vector_store.fetch_story_embeddings(previous_story_ids).values())
                drift = 0.0
                if current_centroid and previous_centroid:
                    drift = 1.0 - cosine_similarity(current_centroid, previous_centroid)
                stats.append(
                    ThemeDailyStat(
                        node_id=theme.node_id,
                        date=day,
                        article_count=len(current_story_ids),
                        centroid_drift=drift,
                    )
                )

        self.repository.save_theme_daily_stats(stats)
        self.repository.refresh_node_heat_view()
        return len(stats)

    def refresh_all(self, *, days: int = 31) -> KGProjectionRefreshResult:
        relations_created = self.rebuild_node_relations()
        theme_stats_written = self.refresh_theme_stats(days=days)
        return KGProjectionRefreshResult(relations_created=relations_created, theme_stats_written=theme_stats_written)

    # ── Message-atomic variants ───────────────────────────────────────────────

    def rebuild_node_relations_from_messages(self) -> int:
        """Same semantics as rebuild_node_relations but aggregates over message_nodes
        joined to raw_messages.timestamp instead of story_units/story_nodes.
        """
        active_node_ids = {node.node_id for node in self.repository.list_nodes(status="active")}

        # Collect all message keys per node (only active nodes).
        node_to_message_keys: dict[str, list[tuple[int, int]]] = {}
        for node_id in active_node_ids:
            keys = self.repository.list_message_keys_for_node(node_id)
            if keys:
                node_to_message_keys[node_id] = keys

        # Build inverse: message key → list of node_ids
        message_to_nodes: dict[tuple[int, int], list[str]] = defaultdict(list)
        for node_id, keys in node_to_message_keys.items():
            for key in keys:
                message_to_nodes[key].append(node_id)

        # For each message, compute co-occurrence pairs.
        # We also need message timestamps for latest_at.
        # Batch-fetch all messages that have at least 2 nodes assigned.
        multi_node_keys = [key for key, nids in message_to_nodes.items() if len(nids) >= 2]
        messages_by_key: dict[tuple[int, int], RawMessage] = {}
        if multi_node_keys:
            for msg in self.repository.list_raw_messages_by_keys(multi_node_keys):
                messages_by_key[(msg.channel_id, msg.message_id)] = msg

        shared_counts: dict[tuple[str, str], int] = defaultdict(int)
        latest_at: dict[tuple[str, str], datetime] = {}

        for key, node_ids in message_to_nodes.items():
            unique_node_ids = sorted(set(node_id for node_id in node_ids if node_id in active_node_ids))
            if len(unique_node_ids) < 2:
                continue
            msg = messages_by_key.get(key)
            for index, left_id in enumerate(unique_node_ids):
                for right_id in unique_node_ids[index + 1:]:
                    pair = _canonical_pair(left_id, right_id)
                    shared_counts[pair] += 1
                    if msg is not None:
                        current_latest = latest_at.get(pair)
                        if current_latest is None or msg.timestamp > current_latest:
                            latest_at[pair] = msg.timestamp

        # Cross-channel bonus: look up primary_event_node_id for each message side.
        primary_event_by_message: dict[tuple[int, int], str] = {}
        cross_bonus: dict[tuple[str, str], float] = defaultdict(float)
        for match in self.repository.list_cross_channel_message_matches():
            left_key = (match.channel_id, match.message_id)
            right_key = (match.matched_channel_id, match.matched_message_id)
            # Lazy-load primary_event_node_id from message_semantics.
            for key in (left_key, right_key):
                if key not in primary_event_by_message:
                    record = self.repository.get_message_semantic_record(
                        channel_id=key[0], message_id=key[1]
                    )
                    primary_event_by_message[key] = record.primary_event_node_id if record and record.primary_event_node_id else ""
            left_event = primary_event_by_message.get(left_key, "")
            right_event = primary_event_by_message.get(right_key, "")
            if not left_event or not right_event or left_event == right_event:
                continue
            pair = _canonical_pair(left_event, right_event)
            cross_bonus[pair] += 0.5

        relations: list[NodeRelation] = []
        all_pairs = sorted(set(shared_counts) | set(cross_bonus))
        for pair in all_pairs:
            shared_count = shared_counts.get(pair, 0)
            score = float(shared_count) + cross_bonus.get(pair, 0.0)
            if score <= 0:
                continue
            relations.append(
                NodeRelation(
                    source_node_id=pair[0],
                    target_node_id=pair[1],
                    relation_type="related",
                    score=score,
                    shared_story_count=shared_count,
                    latest_story_at=latest_at.get(pair),
                )
            )

        self.repository.replace_node_relations(relations)
        return len(relations)

    def refresh_theme_stats_from_messages(self, *, days: int = 31) -> int:
        """Per-theme-per-day article_count (message_count) and centroid_drift,
        computed from message_nodes joined to raw_messages.timestamp.
        """
        themes = self.repository.list_nodes(kind="theme")
        today = _utc_now().date()
        start = today - timedelta(days=max(days - 1, 0))
        stats: list[ThemeDailyStat] = []

        for offset in range(days):
            day = start + timedelta(days=offset)
            previous_day = day - timedelta(days=1)
            for theme in themes:
                current_keys = self.repository.list_message_keys_for_node_on_date(theme.node_id, day)
                previous_keys = self.repository.list_message_keys_for_node_on_date(theme.node_id, previous_day)
                current_centroid = average_vectors(self.vector_store.fetch_message_embeddings(current_keys).values())
                previous_centroid = average_vectors(self.vector_store.fetch_message_embeddings(previous_keys).values())
                drift = 0.0
                if current_centroid and previous_centroid:
                    drift = 1.0 - cosine_similarity(current_centroid, previous_centroid)
                stats.append(
                    ThemeDailyStat(
                        node_id=theme.node_id,
                        date=day,
                        article_count=len(current_keys),
                        centroid_drift=drift,
                    )
                )

        self.repository.save_theme_daily_stats(stats)
        self.repository.refresh_message_heat_view()
        return len(stats)

    def refresh_all_from_messages(self, *, days: int = 31) -> KGProjectionRefreshResult:
        """Message-atomic parallel of refresh_all."""
        relations_created = self.rebuild_node_relations_from_messages()
        theme_stats_written = self.refresh_theme_stats_from_messages(days=days)
        return KGProjectionRefreshResult(relations_created=relations_created, theme_stats_written=theme_stats_written)


class KGNodeProcessingService:
    def __init__(
        self,
        repository: StoryRepository,
        vector_store: VectorStore,
        embedder: Embedder,
        extractor: SemanticExtractor,
        settings: KGSettings,
        *,
        projection_service: KGNodeProjectionService | None = None,
        hierarchy_service: KGEventHierarchyService | None = None,
    ):
        self.repository = repository
        self.vector_store = vector_store
        self.embedder = embedder
        self.extractor = extractor
        self.settings = settings
        self.projection_service = projection_service or KGNodeProjectionService(repository=repository, vector_store=vector_store)
        self.hierarchy_service = hierarchy_service or KGEventHierarchyService(repository)

    def process_unassigned(
        self,
        *,
        channel_id: int | None = None,
        limit: int | None = None,
        options: KGProcessingOptions | None = None,
        progress_callback: Callable[[KGProcessingProgress], None] | None = None,
    ) -> KGNodeProcessResult:
        stories = self.repository.list_stories_without_semantics(channel_id=channel_id, limit=limit)
        return self.process_stories(stories, options=options, progress_callback=progress_callback)

    def process_stories(
        self,
        stories: Sequence[StoryUnit],
        *,
        options: KGProcessingOptions | None = None,
        progress_callback: Callable[[KGProcessingProgress], None] | None = None,
    ) -> KGNodeProcessResult:
        if not stories:
            return KGNodeProcessResult(0, 0, 0, 0, 0)

        options = options or self.default_processing_options()
        ordered_stories = list(stories)
        started_at = time.monotonic()
        failures = 0
        processed = 0
        state = self._initialize_processing_state(ordered_stories)
        resolver = NodeResolver(
            settings=self.settings,
            node_cache=state.node_cache,
            support_records=state.support_records,
            theme_centroids=state.theme_centroids,
            event_centroids=state.event_centroids,
            pending_theme_centroids=state.pending_theme_centroids,
            pending_event_centroids=state.pending_event_centroids,
            utc_now=_utc_now,
        )
        for extraction_batch in _chunked(
            ordered_stories,
            max(options.extraction_batch_size * max(options.extraction_workers, 1), 1),
        ):
            extractions, batch_failures = self._extract_stories(extraction_batch, options=options)
            failures += batch_failures
            for story, extraction in zip(extraction_batch, extractions):
                self._process_story(
                    story=story,
                    extraction=extraction,
                    state=state,
                    resolver=resolver,
                    enable_cross_channel_matching=options.enable_cross_channel_matching,
                )
                processed += 1
            if len(state.pending_semantics) >= options.flush_size:
                self._flush_processing_state(state)
                self._emit_progress(
                    processed=processed,
                    total=len(ordered_stories),
                    failures=failures,
                    started_at=started_at,
                    state=state,
                    callback=progress_callback,
                )

        self._flush_processing_state(state)
        self._emit_progress(
            processed=processed,
            total=len(ordered_stories),
            failures=failures,
            started_at=started_at,
            state=state,
            callback=progress_callback,
        )
        self.hierarchy_service.rebuild()

        projection_result = (
            self.projection_service.refresh_all(days=31)
            if options.projection_policy == "per_batch"
            else KGProjectionRefreshResult(relations_created=0, theme_stats_written=0)
        )
        return KGNodeProcessResult(
            assignments_created=state.assignments_created,
            nodes_created=state.nodes_created,
            cross_channel_matches=state.cross_channel_matches,
            relations_created=projection_result.relations_created,
            theme_stats_written=projection_result.theme_stats_written,
        )

    def default_processing_options(self) -> KGProcessingOptions:
        batch_size = max(self.settings.semantic_batch_size, 1)
        return KGProcessingOptions(
            extraction_batch_size=batch_size,
            extraction_workers=1,
            enable_cross_channel_matching=True,
            projection_policy="per_batch",
            flush_size=max(batch_size * 4, batch_size),
        )

    def _load_node_cache(self) -> dict[NodeKind, dict[str, Node]]:
        cache: dict[NodeKind, dict[str, Node]] = {kind: {} for kind in NODE_KINDS}
        for node in self.repository.list_nodes(status=None):
            cache[node.kind][node.node_id] = node
        return cache

    def _initialize_processing_state(self, stories: Sequence[StoryUnit]) -> _ProcessingState:
        story_embeddings = self.vector_store.fetch_story_embeddings([story.story_id for story in stories])
        missing_stories = [story for story in stories if story.story_id not in story_embeddings]
        pending_story_embeddings: dict[str, StoryEmbeddingRecord] = {}
        if missing_stories:
            embeddings = _safe_embed_texts(
                self.embedder,
                [_embedding_text(_story_text(story), max_chars=self.settings.semantic_max_chars) for story in missing_stories]
            )
            for story, embedding in zip(missing_stories, embeddings):
                story_embeddings[story.story_id] = embedding
                pending_story_embeddings[story.story_id] = StoryEmbeddingRecord(
                    story_id=story.story_id,
                    embedding=embedding,
                    channel_id=story.channel_id,
                    timestamp_start=story.timestamp_start,
                    node_ids=tuple(self.repository.list_story_node_ids(story.story_id)),
                )

        node_cache = self._load_node_cache()
        theme_ids = tuple(node.node_id for node in node_cache["theme"].values())
        event_ids = tuple(node.node_id for node in node_cache["event"].values())
        support_records = {
            record.node_id: record
            for record in self.repository.get_node_support_records(theme_ids + event_ids)
        }
        return _ProcessingState(
            story_embeddings=story_embeddings,
            node_cache=node_cache,
            theme_centroids=self.vector_store.fetch_theme_centroids(theme_ids),
            event_centroids=self.vector_store.fetch_event_centroids(event_ids),
            pending_nodes={},
            pending_assignments=[],
            pending_semantics=[],
            pending_cross_channel_matches=[],
            pending_story_embeddings=pending_story_embeddings,
            pending_theme_centroids={},
            pending_event_centroids={},
            support_records=support_records,
        )

    def _extract_stories(
        self,
        stories: Sequence[StoryUnit],
        *,
        options: KGProcessingOptions,
    ) -> tuple[list[StorySemanticExtraction], int]:
        batches = _chunked(stories, options.extraction_batch_size)
        if not batches:
            return [], 0
        if options.extraction_workers <= 1 or len(batches) == 1:
            extracted = [self._extract_story_batch(batch) for batch in batches]
        else:
            with ThreadPoolExecutor(max_workers=options.extraction_workers) as executor:
                extracted = list(executor.map(self._extract_story_batch, batches))
        results: list[StorySemanticExtraction] = []
        failures = 0
        for batch_results, batch_failures in extracted:
            results.extend(batch_results)
            failures += batch_failures
        return results, failures

    def _extract_story_batch(self, stories: Sequence[StoryUnit]) -> tuple[list[StorySemanticExtraction], int]:
        try:
            extracted = list(self.extractor.extract_stories(stories))
            if len(extracted) != len(stories):
                raise ValueError("extract_stories returned a mismatched result count")
            return extracted, 0
        except Exception:
            results: list[StorySemanticExtraction] = []
            failures = 0
            for story in stories:
                extraction, failed = self._safe_extract_story(story)
                results.append(extraction)
                failures += 1 if failed else 0
            return results, failures

    def _safe_extract_story(self, story: StoryUnit) -> tuple[StorySemanticExtraction, bool]:
        try:
            return self.extractor.extract_story(story), False
        except Exception:
            return StorySemanticExtraction(story_id=story.story_id), True

    def _prepare_story_candidates(
        self,
        *,
        story: StoryUnit,
        extraction: StorySemanticExtraction,
    ) -> list[_PreparedCandidate]:
        prepared: list[_PreparedCandidate] = []
        embedding_texts: list[str] = []
        embedding_indexes: list[int] = []

        for kind, source_candidate in iter_extraction_candidates(extraction):
            candidate = _clean_candidate(source_candidate)
            activate_immediately = kind not in {"event", "theme"}
            if kind == "event":
                candidate, activate_immediately = _canonicalize_event_candidate(candidate, extraction=extraction)
            elif kind == "theme":
                activate_immediately = False

            prepared.append(
                _PreparedCandidate(
                    kind=kind,
                    source_name=source_candidate.name,
                    candidate=candidate,
                    embedding=[],
                    activate_immediately=activate_immediately,
                )
            )
            if kind in {"event", "theme"}:
                embedding_indexes.append(len(prepared) - 1)
                embedding_texts.append(
                    _candidate_embedding_text(
                        candidate,
                        story=story,
                        max_chars=self.settings.semantic_max_chars,
                    )
                )

        embeddings = _safe_embed_texts(self.embedder, embedding_texts)
        for index, embedding in zip(embedding_indexes, embeddings):
            prepared[index] = replace(prepared[index], embedding=embedding)
        return prepared

    def _story_node_ids_for_support(self, *, story_id: str, state: _ProcessingState) -> list[str]:
        pending = state.pending_story_embeddings.get(story_id)
        if pending is not None and pending.node_ids:
            return list(pending.node_ids)
        return self.repository.list_story_node_ids(story_id)

    def _process_story(
        self,
        *,
        story: StoryUnit,
        extraction: StorySemanticExtraction,
        state: _ProcessingState,
        resolver: NodeResolver,
        enable_cross_channel_matching: bool,
    ) -> None:
        embedding = state.story_embeddings.get(story.story_id, [])
        primary_event_key = _normalize_name(extraction.primary_event or "")
        if extraction.events and not primary_event_key:
            primary_event_key = _normalize_name(extraction.events[0].name)
        prepared_candidates = self._prepare_story_candidates(story=story, extraction=extraction)

        assigned_node_ids: set[str] = set()
        assignments: list[StoryNodeAssignment] = []
        updated_nodes: list[Node] = []
        primary_event_node_id: str | None = None

        for prepared in prepared_candidates:
            kind = prepared.kind
            candidate = prepared.candidate
            resolved = resolver.resolve(
                kind=kind,
                candidate=candidate,
                embedding=prepared.embedding,
                story_id=story.story_id,
                channel_id=story.channel_id,
                story_timestamp=story.timestamp_end,
                activate_immediately=prepared.activate_immediately,
            )
            node = resolved.node
            if node.node_id in assigned_node_ids:
                if kind == "event" and _normalize_name(prepared.source_name) == primary_event_key:
                    primary_event_node_id = node.node_id
                continue
            assigned_node_ids.add(node.node_id)
            updated_nodes.append(node)
            is_primary_event = kind == "event" and _normalize_name(prepared.source_name) == primary_event_key
            if is_primary_event:
                primary_event_node_id = node.node_id
            assignments.append(
                StoryNodeAssignment(
                    story_id=story.story_id,
                    node_id=node.node_id,
                    confidence=resolved.confidence,
                    assigned_at=_utc_now(),
                    is_primary_event=is_primary_event,
                )
            )
            if resolved.created:
                state.nodes_created += 1

        if not primary_event_node_id and extraction.events and assignments:
            node_lookup = {node.node_id: node for node in updated_nodes}
            for index, assignment in enumerate(assignments):
                node = node_lookup.get(assignment.node_id)
                if node is not None and node.kind == "event":
                    assignments[index] = replace(assignment, is_primary_event=True)
                    primary_event_node_id = assignment.node_id
                    break

        for node in updated_nodes:
            state.pending_nodes[node.node_id] = node
        state.pending_assignments.extend(assignments)
        state.pending_semantics.append(
            StorySemanticRecord(
                story_id=story.story_id,
                extraction_payload=serialize_extraction(extraction),
                primary_event_node_id=primary_event_node_id,
                processed_at=_utc_now(),
                updated_at=_utc_now(),
            )
        )
        state.assignments_created += len(assignments)

        if embedding:
            state.pending_story_embeddings[story.story_id] = StoryEmbeddingRecord(
                story_id=story.story_id,
                embedding=embedding,
                channel_id=story.channel_id,
                timestamp_start=story.timestamp_start,
                node_ids=tuple(sorted(assigned_node_ids)),
            )
            if enable_cross_channel_matching:
                matches = self._build_cross_channel_matches(story=story, embedding=embedding)
                state.pending_cross_channel_matches.extend(matches)
                state.cross_channel_matches += len(matches)
                if matches:
                    support_node_ids = set(assigned_node_ids)
                    for match in matches:
                        support_node_ids.update(self._story_node_ids_for_support(story_id=match.matched_story_id, state=state))
                    for node in resolver.register_cross_channel_support(node_ids=sorted(support_node_ids)):
                        state.pending_nodes[node.node_id] = node

    def _build_cross_channel_matches(self, *, story: StoryUnit, embedding: list[float]) -> list[CrossChannelMatch]:
        matches = self.vector_store.query_story_embeddings(
            embedding,
            top_k=5,
            exclude_channel_id=story.channel_id,
            timestamp_gte=story.timestamp_start - timedelta(days=3),
        )
        accepted: list[CrossChannelMatch] = []
        for match in matches:
            if match.similarity_score <= self.settings.cross_channel_threshold:
                continue
            matched_story = self.repository.get_story_unit(match.story_id)
            timestamp_delta_seconds = None
            if matched_story is not None:
                timestamp_delta_seconds = int((story.timestamp_start - matched_story.timestamp_start).total_seconds())
            accepted.append(
                CrossChannelMatch(
                    story_id=story.story_id,
                    matched_story_id=match.story_id,
                    similarity_score=match.similarity_score,
                    timestamp_delta_seconds=timestamp_delta_seconds,
                    created_at=_utc_now(),
                )
            )
        return accepted

    def _flush_processing_state(self, state: _ProcessingState) -> None:
        if not (
            state.pending_nodes
            or state.pending_assignments
            or state.pending_semantics
            or state.pending_cross_channel_matches
            or state.pending_story_embeddings
            or state.pending_theme_centroids
            or state.pending_event_centroids
        ):
            return
        self.repository.save_semantic_results(
            nodes=list(state.pending_nodes.values()),
            assignments=state.pending_assignments,
            semantics=state.pending_semantics,
            cross_channel_matches=state.pending_cross_channel_matches,
        )
        if state.pending_story_embeddings:
            self.vector_store.upsert_story_embeddings(list(state.pending_story_embeddings.values()))
        if state.pending_theme_centroids:
            self.vector_store.upsert_theme_centroids(list(state.pending_theme_centroids.values()))
        if state.pending_event_centroids:
            self.vector_store.upsert_event_centroids(list(state.pending_event_centroids.values()))
        state.pending_nodes.clear()
        state.pending_assignments.clear()
        state.pending_semantics.clear()
        state.pending_cross_channel_matches.clear()
        state.pending_story_embeddings.clear()
        state.pending_theme_centroids.clear()
        state.pending_event_centroids.clear()

    def _emit_progress(
        self,
        *,
        processed: int,
        total: int,
        failures: int,
        started_at: float,
        state: _ProcessingState,
        callback: Callable[[KGProcessingProgress], None] | None,
    ) -> None:
        if callback is None:
            return
        elapsed = max(time.monotonic() - started_at, 0.001)
        callback(
            KGProcessingProgress(
                stories_processed=processed,
                stories_total=total,
                assignments_created=state.assignments_created,
                nodes_created=state.nodes_created,
                cross_channel_matches=state.cross_channel_matches,
                failures=failures,
                rate_per_sec=processed / elapsed,
            )
        )


    # ── Message-atomic pipeline ──────────────────────────────────────────────

    def process_messages(
        self,
        messages: Sequence[RawMessage],
        *,
        options: KGProcessingOptions | None = None,
        progress_callback: Callable[[KGProcessingProgress], None] | None = None,
    ) -> KGNodeProcessResult:
        """Run extraction + node resolution + assignment on a batch of messages.

        Skips messages that already have a MessageSemanticRecord (idempotent).
        For each new message: extracts via extractor.extract_message(), iterates
        candidates, embeds event/theme candidates, calls resolver.resolve_message(),
        and writes a MessageNodeAssignment.  Cross-channel matching queries
        vector_store.query_message_embeddings to find similar messages from other
        channels and creates CrossChannelMessageMatch records.
        """
        if not messages:
            return KGNodeProcessResult(0, 0, 0, 0, 0)

        options = options or self.default_processing_options()
        # Filter to messages that don't already have semantics (idempotent).
        new_messages = [
            msg for msg in messages
            if self.repository.get_message_semantic_record(channel_id=msg.channel_id, message_id=msg.message_id) is None
        ]
        if not new_messages:
            return KGNodeProcessResult(0, 0, 0, 0, 0)

        started_at = time.monotonic()
        failures = 0
        processed = 0
        state = self._initialize_message_processing_state(new_messages)
        resolver = NodeResolver(
            settings=self.settings,
            node_cache=state.node_cache,
            support_records=state.support_records,
            theme_centroids=state.theme_centroids,
            event_centroids=state.event_centroids,
            pending_theme_centroids=state.pending_theme_centroids,
            pending_event_centroids=state.pending_event_centroids,
            utc_now=_utc_now,
        )

        for msg in new_messages:
            try:
                extraction = self.extractor.extract_message(msg)
            except Exception:
                extraction = MessageSemanticExtraction(
                    channel_id=msg.channel_id,
                    message_id=msg.message_id,
                )
                failures += 1
            self._process_message(
                message=msg,
                extraction=extraction,
                state=state,
                resolver=resolver,
                enable_cross_channel_matching=options.enable_cross_channel_matching,
            )
            processed += 1
            if len(state.pending_semantics) >= options.flush_size:
                self._flush_message_processing_state(state)
                self._emit_message_progress(
                    processed=processed,
                    total=len(new_messages),
                    failures=failures,
                    started_at=started_at,
                    state=state,
                    callback=progress_callback,
                )

        self._flush_message_processing_state(state)
        self._emit_message_progress(
            processed=processed,
            total=len(new_messages),
            failures=failures,
            started_at=started_at,
            state=state,
            callback=progress_callback,
        )

        projection_result = (
            self.projection_service.refresh_all(days=31)
            if options.projection_policy == "per_batch"
            else KGProjectionRefreshResult(relations_created=0, theme_stats_written=0)
        )
        return KGNodeProcessResult(
            assignments_created=state.assignments_created,
            nodes_created=state.nodes_created,
            cross_channel_matches=state.cross_channel_matches,
            relations_created=projection_result.relations_created,
            theme_stats_written=projection_result.theme_stats_written,
        )

    def _initialize_message_processing_state(self, messages: Sequence[RawMessage]) -> _MessageProcessingState:
        msg_keys = [(msg.channel_id, msg.message_id) for msg in messages]
        message_embeddings = self.vector_store.fetch_message_embeddings(msg_keys)

        node_cache = self._load_node_cache()
        theme_ids = tuple(node.node_id for node in node_cache["theme"].values())
        event_ids = tuple(node.node_id for node in node_cache["event"].values())
        support_records = {
            record.node_id: record
            for record in self.repository.get_node_support_records(theme_ids + event_ids)
        }
        return _MessageProcessingState(
            message_embeddings=message_embeddings,
            node_cache=node_cache,
            theme_centroids=self.vector_store.fetch_theme_centroids(theme_ids),
            event_centroids=self.vector_store.fetch_event_centroids(event_ids),
            support_records=support_records,
            pending_nodes={},
            pending_assignments=[],
            pending_semantics=[],
            pending_cross_channel_matches=[],
            pending_message_embeddings={},
            pending_theme_centroids={},
            pending_event_centroids={},
        )

    def _prepare_message_candidates(
        self,
        *,
        message: RawMessage,
        extraction: MessageSemanticExtraction,
    ) -> list[_PreparedCandidate]:
        prepared: list[_PreparedCandidate] = []
        embedding_texts: list[str] = []
        embedding_indexes: list[int] = []

        for kind, source_candidate in iter_extraction_candidates(extraction):  # type: ignore[arg-type]
            candidate = _clean_candidate(source_candidate)
            activate_immediately = kind not in {"event", "theme"}
            if kind == "event":
                candidate, activate_immediately = _canonicalize_event_candidate(candidate, extraction=extraction)  # type: ignore[arg-type]
            elif kind == "theme":
                activate_immediately = False

            prepared.append(
                _PreparedCandidate(
                    kind=kind,
                    source_name=source_candidate.name,
                    candidate=candidate,
                    embedding=[],
                    activate_immediately=activate_immediately,
                )
            )
            if kind in {"event", "theme"}:
                embedding_indexes.append(len(prepared) - 1)
                embedding_texts.append(
                    self._message_candidate_embedding_text(
                        candidate,
                        message=message,
                    )
                )

        embeddings = _safe_embed_texts(self.embedder, embedding_texts)
        for index, embedding in zip(embedding_indexes, embeddings):
            prepared[index] = replace(prepared[index], embedding=embedding)
        return prepared

    def _message_candidate_embedding_text(
        self,
        candidate: ExtractedSemanticNode,
        *,
        message: RawMessage,
    ) -> str:
        context = preferred_message_text(message).strip()
        if len(context) > 800:
            context = context[-800:]
        parts = [candidate.name.strip()]
        if candidate.summary:
            parts.append(candidate.summary.strip())
        if context:
            parts.append(f"Context: {context}")
        return _embedding_text("\n".join(part for part in parts if part), max_chars=self.settings.semantic_max_chars)

    def _process_message(
        self,
        *,
        message: RawMessage,
        extraction: MessageSemanticExtraction,
        state: _MessageProcessingState,
        resolver: NodeResolver,
        enable_cross_channel_matching: bool,
    ) -> None:
        msg_key = (message.channel_id, message.message_id)
        embedding = state.message_embeddings.get(msg_key, [])
        primary_event_key = _normalize_name(extraction.primary_event or "")
        if extraction.events and not primary_event_key:
            primary_event_key = _normalize_name(extraction.events[0].name)
        prepared_candidates = self._prepare_message_candidates(message=message, extraction=extraction)

        assigned_node_ids: set[str] = set()
        assignments: list[MessageNodeAssignment] = []
        updated_nodes: list[Node] = []
        primary_event_node_id: str | None = None

        for prepared in prepared_candidates:
            kind = prepared.kind
            candidate = prepared.candidate
            resolved = resolver.resolve_message(
                kind=kind,
                candidate=candidate,
                embedding=prepared.embedding,
                channel_id=message.channel_id,
                message_id=message.message_id,
                message_timestamp=message.timestamp,
                activate_immediately=prepared.activate_immediately,
            )
            node = resolved.node
            if node.node_id in assigned_node_ids:
                if kind == "event" and _normalize_name(prepared.source_name) == primary_event_key:
                    primary_event_node_id = node.node_id
                continue
            assigned_node_ids.add(node.node_id)
            updated_nodes.append(node)
            is_primary_event = kind == "event" and _normalize_name(prepared.source_name) == primary_event_key
            if is_primary_event:
                primary_event_node_id = node.node_id
            assignments.append(
                MessageNodeAssignment(
                    channel_id=message.channel_id,
                    message_id=message.message_id,
                    node_id=node.node_id,
                    confidence=resolved.confidence,
                    assigned_at=_utc_now(),
                    is_primary_event=is_primary_event,
                )
            )
            if resolved.created:
                state.nodes_created += 1

        if not primary_event_node_id and extraction.events and assignments:
            node_lookup = {node.node_id: node for node in updated_nodes}
            for index, assignment in enumerate(assignments):
                node = node_lookup.get(assignment.node_id)
                if node is not None and node.kind == "event":
                    assignments[index] = replace(assignment, is_primary_event=True)
                    primary_event_node_id = assignment.node_id
                    break

        for node in updated_nodes:
            state.pending_nodes[node.node_id] = node
        state.pending_assignments.extend(assignments)
        state.pending_semantics.append(
            MessageSemanticRecord(
                channel_id=message.channel_id,
                message_id=message.message_id,
                extraction_payload=serialize_extraction(extraction),  # type: ignore[arg-type]
                primary_event_node_id=primary_event_node_id,
                extracted_at=_utc_now(),
                updated_at=_utc_now(),
            )
        )
        state.assignments_created += len(assignments)

        # Embed the message if we don't already have an embedding for it.
        if not embedding:
            msg_text = preferred_message_text(message)
            emb_texts = _safe_embed_texts(
                self.embedder,
                [safe_message_text(msg_text or "(media only telegram message)", max_chars=self.settings.semantic_max_chars)]
            )
            embedding = emb_texts[0] if emb_texts else []
            if embedding:
                state.message_embeddings[msg_key] = embedding

        if embedding:
            state.pending_message_embeddings[msg_key] = MessageEmbeddingRecord(
                channel_id=message.channel_id,
                message_id=message.message_id,
                embedding=embedding,
                timestamp=message.timestamp,
                node_ids=tuple(sorted(assigned_node_ids)),
            )
            if enable_cross_channel_matching:
                matches = self._build_cross_channel_message_matches(message=message, embedding=embedding)
                state.pending_cross_channel_matches.extend(matches)
                state.cross_channel_matches += len(matches)
                if matches:
                    support_node_ids = set(assigned_node_ids)
                    for match in matches:
                        match_key = (match.matched_channel_id, match.matched_message_id)
                        matched_assignments = self.repository.list_message_node_assignments(
                            message_keys=[match_key]
                        )
                        for ma in matched_assignments:
                            support_node_ids.add(ma.node_id)
                        # Also check pending assignments for the matched message.
                        for pa in state.pending_assignments:
                            if pa.channel_id == match.matched_channel_id and pa.message_id == match.matched_message_id:
                                support_node_ids.add(pa.node_id)
                    for node in resolver.register_cross_channel_support(node_ids=sorted(support_node_ids)):
                        state.pending_nodes[node.node_id] = node

    def _build_cross_channel_message_matches(
        self,
        *,
        message: RawMessage,
        embedding: list[float],
    ) -> list[CrossChannelMessageMatch]:
        matches = self.vector_store.query_message_embeddings(
            embedding,
            top_k=5,
            exclude_channel_id=message.channel_id,
            timestamp_gte=message.timestamp - timedelta(days=self.settings.event_match_window_days),
        )
        accepted: list[CrossChannelMessageMatch] = []
        for match in matches:
            if match.similarity_score <= self.settings.cross_channel_threshold:
                continue
            timestamp_delta_seconds = None
            # `match` is a MessageMatch with channel_id, message_id, similarity_score
            # Look up the matched message timestamp if possible.
            accepted.append(
                CrossChannelMessageMatch(
                    channel_id=message.channel_id,
                    message_id=message.message_id,
                    matched_channel_id=match.channel_id,
                    matched_message_id=match.message_id,
                    similarity_score=match.similarity_score,
                    timestamp_delta_seconds=timestamp_delta_seconds,
                    created_at=_utc_now(),
                )
            )
        return accepted

    def _flush_message_processing_state(self, state: _MessageProcessingState) -> None:
        if not (
            state.pending_nodes
            or state.pending_assignments
            or state.pending_semantics
            or state.pending_cross_channel_matches
            or state.pending_message_embeddings
            or state.pending_theme_centroids
            or state.pending_event_centroids
        ):
            return
        self.repository.save_nodes(list(state.pending_nodes.values()))
        self.repository.save_message_node_assignments(state.pending_assignments)
        self.repository.upsert_message_semantics(state.pending_semantics)
        if state.pending_cross_channel_matches:
            self.repository.save_cross_channel_message_matches(state.pending_cross_channel_matches)
        if state.pending_message_embeddings:
            self.vector_store.upsert_message_embeddings(list(state.pending_message_embeddings.values()))
        if state.pending_theme_centroids:
            self.vector_store.upsert_theme_centroids(list(state.pending_theme_centroids.values()))
        if state.pending_event_centroids:
            self.vector_store.upsert_event_centroids(list(state.pending_event_centroids.values()))
        state.pending_nodes.clear()
        state.pending_assignments.clear()
        state.pending_semantics.clear()
        state.pending_cross_channel_matches.clear()
        state.pending_message_embeddings.clear()
        state.pending_theme_centroids.clear()
        state.pending_event_centroids.clear()

    def _emit_message_progress(
        self,
        *,
        processed: int,
        total: int,
        failures: int,
        started_at: float,
        state: _MessageProcessingState,
        callback: Callable[[KGProcessingProgress], None] | None,
    ) -> None:
        if callback is None:
            return
        elapsed = max(time.monotonic() - started_at, 0.001)
        callback(
            KGProcessingProgress(
                stories_processed=processed,
                stories_total=total,
                assignments_created=state.assignments_created,
                nodes_created=state.nodes_created,
                cross_channel_matches=state.cross_channel_matches,
                failures=failures,
                rate_per_sec=processed / elapsed,
            )
        )


class KGSegmentWorker:
    def __init__(
        self,
        repository: StoryRepository,
        stream: RawMessageStream,
        embedder: Embedder,
        vector_store: VectorStore,
        settings: KGSettings,
        *,
        extractor: SemanticExtractor,
        translator: MessageTranslator | None = None,
        segmenter: StorySegmenter | None = None,
        node_service: KGNodeProcessingService | None = None,
    ):
        self.repository = repository
        self.stream = stream
        self.embedder = embedder
        self.vector_store = vector_store
        self.settings = settings
        self.translator = translator
        self.segmenter = segmenter or StorySegmenter()
        self.node_service = node_service or KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        )

    def process_batch(self, *, consumer_name: str, batch_size: int) -> KGSegmentResult:
        self.repository.ensure_schema()
        self.stream.ensure_group()
        entries = self.stream.read(consumer_name=consumer_name, count=batch_size)
        if not entries:
            return KGSegmentResult(0, 0, 0, 0, 0, 0, 0)

        messages = [entry.payload for entry in entries]
        self.repository.upsert_raw_messages(messages)

        grouped: dict[int, list] = defaultdict(list)
        for entry in entries:
            grouped[entry.payload.channel_id].append(entry.payload)

        stories_to_save: list[StoryUnit] = []
        for channel_id in grouped:
            stories_to_save.extend(self._segment_channel(channel_id))

        if not stories_to_save:
            self.stream.ack([entry.entry_id for entry in entries])
            return KGSegmentResult(len(messages), 0, 0, 0, 0, 0, 0)

        self.repository.save_story_units(stories_to_save)
        story_embeddings = _safe_embed_texts(
            self.embedder,
            [_embedding_text(_story_text(story), max_chars=self.settings.semantic_max_chars) for story in stories_to_save]
        )
        self.vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(
                    story_id=story.story_id,
                    embedding=embedding,
                    channel_id=story.channel_id,
                    timestamp_start=story.timestamp_start,
                    node_ids=tuple(self.repository.list_story_node_ids(story.story_id)),
                )
                for story, embedding in zip(stories_to_save, story_embeddings)
            ]
        )
        process_result = self.node_service.process_stories(stories_to_save)
        self.stream.ack([entry.entry_id for entry in entries])
        return KGSegmentResult(
            messages_processed=len(messages),
            stories_saved=len(stories_to_save),
            assignments_created=process_result.assignments_created,
            nodes_created=process_result.nodes_created,
            cross_channel_matches=process_result.cross_channel_matches,
            relations_created=process_result.relations_created,
            theme_stats_written=process_result.theme_stats_written,
        )

    def run_loop(
        self,
        *,
        consumer_name: str,
        batch_size: int,
        poll_interval_seconds: float,
        sleep_fn: Callable[[float], None] = time.sleep,
        stop_after_idle_cycles: int | None = None,
    ) -> KGSegmentResult:
        total_messages = 0
        total_stories = 0
        total_assignments = 0
        total_nodes = 0
        total_matches = 0
        total_relations = 0
        total_stats = 0
        idle_cycles = 0

        while True:
            result = self.process_batch(consumer_name=consumer_name, batch_size=batch_size)
            total_messages += result.messages_processed
            total_stories += result.stories_saved
            total_assignments += result.assignments_created
            total_nodes += result.nodes_created
            total_matches += result.cross_channel_matches
            total_relations += result.relations_created
            total_stats += result.theme_stats_written

            if result.messages_processed > 0:
                idle_cycles = 0
                continue

            idle_cycles += 1
            sleep_fn(max(poll_interval_seconds, 0.0))
            if stop_after_idle_cycles is not None and idle_cycles >= stop_after_idle_cycles:
                break

        return KGSegmentResult(
            messages_processed=total_messages,
            stories_saved=total_stories,
            assignments_created=total_assignments,
            nodes_created=total_nodes,
            cross_channel_matches=total_matches,
            relations_created=total_relations,
            theme_stats_written=total_stats,
        )

    def _segment_channel(self, channel_id: int) -> list[StoryUnit]:
        profile = self.repository.get_channel_profile(channel_id) or default_channel_profile(channel_id)
        unsegmented = self.repository.list_unsegmented_raw_messages(channel_id)
        unsegmented = _ensure_translated_messages(self.repository, self.translator, unsegmented)
        if not unsegmented:
            return []

        recent_stories = self.repository.list_recent_story_units(channel_id, limit=max(profile.lookback_story_count, 1))
        existing_story = recent_stories[0] if recent_stories else None
        existing_messages = self.repository.get_story_messages(existing_story.story_id) if existing_story is not None else []
        existing_messages = _ensure_translated_messages(self.repository, self.translator, existing_messages)
        existing_embedding = (
            self.vector_store.fetch_story_embeddings([existing_story.story_id]).get(existing_story.story_id, [])
            if existing_story is not None
            else []
        )

        candidates = self.segmenter.build_candidates(unsegmented, profile)
        candidate_embeddings = _safe_embed_texts(
            self.embedder,
            [_embedding_text(_messages_text(candidate), max_chars=self.settings.semantic_max_chars) for candidate in candidates]
        )
        merged_groups = self.segmenter.merge_candidates(candidates, candidate_embeddings, profile)

        stories: list[StoryUnit] = []
        if existing_story is not None and merged_groups:
            first_group = merged_groups[0]
            first_group_embedding = _safe_embed_texts(
                self.embedder,
                [_embedding_text(_messages_text(first_group), max_chars=self.settings.semantic_max_chars)]
            )[0]
            if self.segmenter.should_append_to_existing(
                existing_story,
                existing_embedding,
                first_group,
                first_group_embedding,
                profile,
            ):
                stories.append(
                    self.segmenter.create_story(
                        existing_messages + list(first_group),
                        existing_story_id=existing_story.story_id,
                        existing_created_at=existing_story.created_at,
                        profile=profile,
                    )
                )
                merged_groups = merged_groups[1:]

        stories.extend(self.segmenter.create_story(group, profile=profile) for group in merged_groups)
        return stories


class KGProcessingWorker:
    """Consumer-loop worker for the message-atomic pipeline.

    Replaces KGSegmentWorker once the CLI/docker switches over (S2-T5).
    Flow per batch:
    1. stream.read(consumer_name, count=batch_size)
    2. upsert_raw_messages
    3. translate any non-English messages
    4. embed each message that isn't already embedded; upsert to vector_store
    5. node_service.process_messages(translated_messages)
    6. stream.ack(entry_ids)
    """

    def __init__(
        self,
        repository: StoryRepository,
        stream: RawMessageStream,
        embedder: Embedder,
        vector_store: VectorStore,
        settings: KGSettings,
        *,
        extractor: SemanticExtractor,
        translator: MessageTranslator | None = None,
        node_service: KGNodeProcessingService | None = None,
    ):
        self.repository = repository
        self.stream = stream
        self.embedder = embedder
        self.vector_store = vector_store
        self.settings = settings
        self.translator = translator
        self.node_service = node_service or KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        )

    def process_batch(self, *, consumer_name: str, batch_size: int) -> KGProcessingResult:
        self.repository.ensure_schema()
        self.stream.ensure_group()
        entries = self.stream.read(consumer_name=consumer_name, count=batch_size)
        if not entries:
            return KGProcessingResult(0, 0, 0, 0, 0, 0, 0)

        raw_messages = [entry.payload for entry in entries]
        self.repository.upsert_raw_messages(raw_messages)

        # Translate messages that aren't already in English.
        if self.translator is not None:
            translated_messages = list(self.translator.translate_messages(raw_messages))
            self.repository.save_raw_message_translations(translated_messages)
        else:
            translated_messages = raw_messages

        # Embed messages that aren't already embedded.
        messages_embedded = 0
        already_embedded_keys = set(
            self.vector_store.fetch_message_embeddings(
                [(msg.channel_id, msg.message_id) for msg in translated_messages]
            ).keys()
        )
        for msg in translated_messages:
            msg_key = (msg.channel_id, msg.message_id)
            if msg_key in already_embedded_keys:
                continue
            msg_text = preferred_message_text(msg)
            emb_texts = _safe_embed_texts(
                self.embedder,
                [safe_message_text(msg_text or "(media only telegram message)", max_chars=self.settings.semantic_max_chars)],
            )
            embedding = emb_texts[0] if emb_texts else []
            if embedding:
                self.vector_store.upsert_message_embeddings(
                    [
                        MessageEmbeddingRecord(
                            channel_id=msg.channel_id,
                            message_id=msg.message_id,
                            embedding=embedding,
                            timestamp=msg.timestamp,
                        )
                    ]
                )
                self.repository.mark_message_embedded(
                    channel_id=msg.channel_id,
                    message_id=msg.message_id,
                    version=self.settings.embedding_model,
                )
                messages_embedded += 1

        process_result = self.node_service.process_messages(translated_messages)
        self.stream.ack([entry.entry_id for entry in entries])
        return KGProcessingResult(
            messages_processed=len(raw_messages),
            messages_embedded=messages_embedded,
            assignments_created=process_result.assignments_created,
            nodes_created=process_result.nodes_created,
            cross_channel_matches=process_result.cross_channel_matches,
            relations_created=process_result.relations_created,
            theme_stats_written=process_result.theme_stats_written,
        )

    def run_loop(
        self,
        *,
        consumer_name: str,
        batch_size: int,
        poll_interval_seconds: float,
        sleep_fn: Callable[[float], None] = time.sleep,
        stop_after_idle_cycles: int | None = None,
    ) -> KGProcessingResult:
        total_messages = 0
        total_embedded = 0
        total_assignments = 0
        total_nodes = 0
        total_matches = 0
        total_relations = 0
        total_stats = 0
        idle_cycles = 0

        while True:
            result = self.process_batch(consumer_name=consumer_name, batch_size=batch_size)
            total_messages += result.messages_processed
            total_embedded += result.messages_embedded
            total_assignments += result.assignments_created
            total_nodes += result.nodes_created
            total_matches += result.cross_channel_matches
            total_relations += result.relations_created
            total_stats += result.theme_stats_written

            if result.messages_processed > 0:
                idle_cycles = 0
                continue

            idle_cycles += 1
            sleep_fn(max(poll_interval_seconds, 0.0))
            if stop_after_idle_cycles is not None and idle_cycles >= stop_after_idle_cycles:
                break

        return KGProcessingResult(
            messages_processed=total_messages,
            messages_embedded=total_embedded,
            assignments_created=total_assignments,
            nodes_created=total_nodes,
            cross_channel_matches=total_matches,
            relations_created=total_relations,
            theme_stats_written=total_stats,
        )


class KGChannelMaintenanceService:
    def __init__(
        self,
        repository: StoryRepository,
        vector_store: VectorStore,
        embedder: Embedder,
        extractor: SemanticExtractor,
        settings: KGSettings,
        *,
        translator: MessageTranslator | None = None,
        segmenter: StorySegmenter | None = None,
        node_service: KGNodeProcessingService | None = None,
        hierarchy_service: KGEventHierarchyService | None = None,
    ):
        self.repository = repository
        self.vector_store = vector_store
        self.embedder = embedder
        self.extractor = extractor
        self.settings = settings
        self.translator = translator
        self.segmenter = segmenter or StorySegmenter()
        self.hierarchy_service = hierarchy_service or KGEventHierarchyService(repository)
        self.node_service = node_service or KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
            hierarchy_service=self.hierarchy_service,
        )

    def reset_channel(self, channel_id: int) -> KGChannelResetResult:
        self.repository.ensure_schema()
        story_ids, theme_ids, event_ids = self.repository.clear_semantic_state(channel_id=channel_id)
        self.vector_store.delete_theme_centroids(theme_ids)
        self.vector_store.delete_event_centroids(event_ids)
        self.hierarchy_service.rebuild()
        return KGChannelResetResult(stories_preserved=len(story_ids), nodes_deleted=len(theme_ids) + len(event_ids))

    def clear_story_state(self, channel_id: int) -> KGChannelResetResult:
        self.repository.ensure_schema()
        story_ids, theme_ids, event_ids = self.repository.clear_story_state(channel_id=channel_id)
        self.vector_store.delete_story_embeddings(story_ids)
        self.vector_store.delete_theme_centroids(theme_ids)
        self.vector_store.delete_event_centroids(event_ids)
        self.hierarchy_service.rebuild()
        return KGChannelResetResult(stories_preserved=0, nodes_deleted=len(theme_ids) + len(event_ids))

    def rebuild_event_hierarchy(self):
        self.repository.ensure_schema()
        return self.hierarchy_service.rebuild()

    def rebuild_story_units(self, channel_id: int) -> list[StoryUnit]:
        profile = self.repository.get_channel_profile(channel_id) or default_channel_profile(channel_id)
        raw_messages = self.repository.list_raw_messages(channel_id)
        raw_messages = _ensure_translated_messages(self.repository, self.translator, raw_messages)
        if not raw_messages:
            return []

        candidates = self.segmenter.build_candidates(raw_messages, profile)
        if not candidates:
            return []
        candidate_embeddings = _safe_embed_texts(
            self.embedder,
            [_embedding_text(_messages_text(candidate), max_chars=self.settings.semantic_max_chars) for candidate in candidates],
        )
        merged_groups = self.segmenter.merge_candidates(candidates, candidate_embeddings, profile)
        stories = [self.segmenter.create_story(group, profile=profile) for group in merged_groups]
        self.repository.save_story_units(stories)
        return stories

    def rebuild_channel(self, channel_id: int) -> KGChannelRebuildResult:
        story_count = len(self.repository.list_story_units(channel_id=channel_id))
        result = self.rebuild_channels((channel_id,))
        return KGChannelRebuildResult(
            stories_processed=story_count,
            assignments_created=result.assignments_created,
            nodes_created=result.nodes_created,
            relations_created=result.relations_created,
            theme_stats_written=result.theme_stats_written,
        )

    def rebuild_channels(
        self,
        channel_ids: Sequence[int],
        *,
        workers: int | None = None,
        progress_callback: Callable[[KGHistoricalRebuildProgress], None] | None = None,
    ) -> KGHistoricalRebuildResult:
        self.repository.ensure_schema()
        unique_channel_ids = tuple(dict.fromkeys(channel_ids))
        if not unique_channel_ids:
            return KGHistoricalRebuildResult(0, 0, 0, 0, 0, 0)

        processing_options = KGProcessingOptions(
            extraction_batch_size=max(self.settings.semantic_batch_size, 1),
            extraction_workers=max(workers or self.settings.historical_extraction_workers, 1),
            enable_cross_channel_matching=False,
            projection_policy="end_of_run",
            flush_size=max(self.settings.semantic_batch_size * 8, self.settings.semantic_batch_size),
        )
        result_holder: dict[str, KGHistoricalRebuildResult] = {}

        def _run() -> None:
            stories_processed = 0
            assignments_created = 0
            nodes_created = 0
            for channel_id in unique_channel_ids:
                self.reset_channel(channel_id)
                stories = self.repository.list_story_units(channel_id=channel_id)
                self._ensure_story_embeddings(stories)

                def _channel_progress(progress: KGProcessingProgress) -> None:
                    if progress_callback is None:
                        return
                    progress_callback(
                        KGHistoricalRebuildProgress(
                            channel_id=channel_id,
                            channel_story_total=len(stories),
                            channel_story_processed=progress.stories_processed,
                            assignments_created=progress.assignments_created,
                            nodes_created=progress.nodes_created,
                            failures=progress.failures,
                            rate_per_sec=progress.rate_per_sec,
                        )
                    )

                channel_result = self.node_service.process_stories(
                    stories,
                    options=processing_options,
                    progress_callback=_channel_progress,
                )
                stories_processed += len(stories)
                assignments_created += channel_result.assignments_created
                nodes_created += channel_result.nodes_created

            projection_result = self.node_service.projection_service.refresh_all(days=31)
            result_holder["value"] = KGHistoricalRebuildResult(
                channels_processed=len(unique_channel_ids),
                stories_processed=stories_processed,
                assignments_created=assignments_created,
                nodes_created=nodes_created,
                relations_created=projection_result.relations_created,
                theme_stats_written=projection_result.theme_stats_written,
            )

        locked = self.repository.run_with_advisory_lock("kg-historical-rebuild", _run)
        if not locked:
            raise RuntimeError("Could not acquire kg-historical-rebuild advisory lock.")
        return result_holder["value"]

    def _ensure_story_embeddings(self, stories: Sequence[StoryUnit]) -> None:
        existing = self.vector_store.fetch_story_embeddings([story.story_id for story in stories])
        missing = [story for story in stories if story.story_id not in existing]
        if not missing:
            return
        embeddings = _safe_embed_texts(
            self.embedder,
            [_embedding_text(_story_text(story), max_chars=self.settings.semantic_max_chars) for story in missing]
        )
        self.vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(
                    story_id=story.story_id,
                    embedding=embedding,
                    channel_id=story.channel_id,
                    timestamp_start=story.timestamp_start,
                    node_ids=tuple(self.repository.list_story_node_ids(story.story_id)),
                )
                for story, embedding in zip(missing, embeddings)
            ]
        )


class KGChannelRepairService:
    def __init__(
        self,
        app_settings: Settings,
        telegram_client: TelegramAccountClient,
        repository: StoryRepository,
        vector_store: VectorStore,
        embedder: Embedder,
        extractor: SemanticExtractor,
        settings: KGSettings,
        *,
        translator: MessageTranslator | None = None,
        maintenance_service: KGChannelMaintenanceService | None = None,
    ):
        self.app_settings = app_settings
        self.telegram_client = telegram_client
        self.repository = repository
        self.vector_store = vector_store
        self.embedder = embedder
        self.extractor = extractor
        self.settings = settings
        self.translator = translator
        self.maintenance_service = maintenance_service or KGChannelMaintenanceService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
            translator=translator,
        )

    async def sync_status(self, channel_ids: Sequence[int]) -> list[KGChannelSyncStatus]:
        chats = await self._resolve_channels(channel_ids)
        statuses: list[KGChannelSyncStatus] = []
        for chat in chats:
            raw_messages = self.repository.list_raw_messages(chat.chat_id)
            stories = self.repository.list_story_units(channel_id=chat.chat_id)
            latest_visible = await self._latest_message_timestamp(chat)
            statuses.append(
                KGChannelSyncStatus(
                    channel_id=chat.chat_id,
                    channel_title=chat.title,
                    telegram_latest_at=latest_visible,
                    ingested_latest_at=raw_messages[-1].timestamp if raw_messages else None,
                    rebuilt_latest_at=stories[-1].timestamp_end if stories else None,
                    raw_message_count=len(raw_messages),
                    story_count=len(stories),
                )
            )
        return statuses

    async def repair_channels(
        self,
        channel_ids: Sequence[int],
        *,
        since: datetime | None = None,
        workers: int | None = None,
        progress_callback: Callable[[KGHistoricalRebuildProgress], None] | None = None,
    ) -> KGChannelRepairResult:
        self.repository.ensure_schema()
        unique_channel_ids = tuple(dict.fromkeys(channel_ids))
        if not unique_channel_ids:
            return KGChannelRepairResult(0, 0, 0, 0, 0, 0, 0)

        chats = await self._resolve_channels(unique_channel_ids)
        effective_since = since or self.app_settings.since_date
        messages_upserted = 0
        stories_rebuilt = 0

        for chat in chats:
            existing_raw_count = len(self.repository.list_raw_messages(chat.chat_id))
            fetched_messages: list[RawMessage] = []
            async for envelope in self.telegram_client.iter_message_envelopes(chat, reverse=False):
                posted_at = envelope.record.posted_at
                if effective_since is not None and posted_at is not None and ensure_utc(posted_at) is not None:
                    if ensure_utc(posted_at) < effective_since:
                        break
                fetched_messages.append(normalize_message_record(envelope.record, raw_json=envelope.raw_json))
                if len(fetched_messages) >= REPAIR_RAW_MESSAGE_FLUSH_SIZE:
                    self.repository.upsert_raw_messages(fetched_messages)
                    fetched_messages.clear()
            if fetched_messages:
                self.repository.upsert_raw_messages(fetched_messages)
            updated_raw_messages = self.repository.list_raw_messages(chat.chat_id)
            messages_upserted += max(len(updated_raw_messages) - existing_raw_count, 0)
            self.maintenance_service.clear_story_state(chat.chat_id)
            stories_rebuilt += len(self.maintenance_service.rebuild_story_units(chat.chat_id))

        rebuild_result = self.maintenance_service.rebuild_channels(
            unique_channel_ids,
            workers=workers,
            progress_callback=progress_callback,
        )
        return KGChannelRepairResult(
            channels_processed=rebuild_result.channels_processed,
            messages_upserted=messages_upserted,
            stories_rebuilt=stories_rebuilt,
            assignments_created=rebuild_result.assignments_created,
            nodes_created=rebuild_result.nodes_created,
            relations_created=rebuild_result.relations_created,
            theme_stats_written=rebuild_result.theme_stats_written,
        )

    async def _resolve_channels(self, channel_ids: Sequence[int]) -> list[ChatRecord]:
        dialogs = await self.telegram_client.get_dialogs()
        chats = discover_chats(dialogs)
        resolved = [resolve_chat(chats, str(channel_id)) for channel_id in channel_ids]
        KGProfileService(self.repository).sync_chat_metadata(resolved)
        return resolved

    async def _latest_message_timestamp(self, chat: ChatRecord) -> datetime | None:
        async for envelope in self.telegram_client.iter_message_envelopes(chat, limit=1, reverse=False):
            return ensure_utc(envelope.record.posted_at) or envelope.record.posted_at
        return None


class KGQueryService:
    def __init__(self, repository: StoryRepository):
        self.repository = repository

    def channels(self):
        return self.repository.list_channels()

    def themes_now(self, *, limit: int = 20) -> list[NodeHeatSnapshot]:
        return self.repository.list_theme_heat(limit=limit)

    def themes_emerging(self, *, limit: int = 20) -> list[NodeHeatSnapshot]:
        return self.repository.list_theme_heat(phase="emerging", limit=limit)

    def themes_fading(self, *, limit: int = 20) -> list[NodeHeatSnapshot]:
        return self.repository.list_theme_heat(phase="fading", limit=limit)

    def theme_history(self, slug: str) -> list[ThemeHistoryPoint]:
        return self.repository.get_theme_history(slug=slug)

    def list_nodes(self, *, kind: NodeKind, limit: int = 50, include_children: bool = False) -> list[NodeListEntry]:
        if kind != "event":
            return self.repository.list_node_entries(kind=kind, limit=limit)
        snapshot = build_event_hierarchy_snapshot(self.repository)
        node_ids = tuple(snapshot.nodes_by_id) if include_children else snapshot.top_level_ids()
        rows = [snapshot.entry_for(node_id) for node_id in node_ids]
        rows.sort(
            key=lambda row: (
                -row.article_count,
                -(row.last_updated.timestamp() if row.last_updated is not None else 0.0),
                row.display_name.lower(),
            ),
        )
        return rows[:limit]

    def node_show(
        self,
        *,
        kind: NodeKind,
        slug: str,
        story_limit: int = 20,
        story_offset: int = 0,
    ) -> NodeDetail | None:
        if kind != "event":
            return self.repository.get_node_detail(kind=kind, slug=slug, story_limit=story_limit, story_offset=story_offset)
        snapshot = build_event_hierarchy_snapshot(self.repository)
        node = next((item for item in snapshot.nodes_by_id.values() if item.slug == slug), None)
        if node is None:
            return None

        node_id = node.node_id
        relevant_story_ids = set(snapshot.rollup_story_ids_by_node.get(node_id, set()))
        if not snapshot.is_parent(node_id):
            relevant_story_ids = set(snapshot.direct_story_ids_by_node.get(node_id, set()))

        assignments = self.repository.list_story_node_assignments(story_ids=tuple(sorted(relevant_story_ids)))
        assignments_by_story: dict[str, list[StoryNodeAssignment]] = defaultdict(list)
        assignment_node_ids: set[str] = set()
        for assignment in assignments:
            assignments_by_story[assignment.story_id].append(assignment)
            assignment_node_ids.add(assignment.node_id)
        related_nodes = {item.node_id: item for item in self.repository.get_nodes(sorted(assignment_node_ids))}
        story_lookup = {
            story.story_id: story
            for story in self.repository.get_story_units_by_ids(sorted(relevant_story_ids))
        }
        descendant_ids = set(snapshot.descendant_ids(node_id))
        excluded_event_ids = set(descendant_ids)
        if node.parent_node_id is not None:
            excluded_event_ids.add(node.parent_node_id)

        shared_counts: dict[str, Counter[str]] = defaultdict(Counter)
        latest_story_at: dict[str, dict[str, datetime | None]] = defaultdict(dict)
        for story_id, story_assignments in assignments_by_story.items():
            story = story_lookup.get(story_id)
            seen_related_ids: set[str] = set()
            for assignment in story_assignments:
                related = related_nodes.get(assignment.node_id)
                if related is None or related.status != "active":
                    continue
                related_id = related.node_id
                related_node = related
                if related.kind == "event" and snapshot.is_parent(node_id):
                    related_id = related.parent_node_id or related_id
                    related_node = snapshot.nodes_by_id.get(related_id, related)
                if related.kind == "event" and related_id in excluded_event_ids:
                    continue
                if related.kind != "event" and related_id == node_id:
                    continue
                if related_id in seen_related_ids:
                    continue
                shared_counts[related_node.kind][related_id] += 1
                current_latest = latest_story_at[related_node.kind].get(related_id)
                if story is not None and (current_latest is None or story.timestamp_end > current_latest):
                    latest_story_at[related_node.kind][related_id] = story.timestamp_end
                seen_related_ids.add(related_id)

        bucketed: dict[str, list[RelatedNode]] = defaultdict(list)
        for bucket_kind, counts in shared_counts.items():
            for related_id, shared_story_count in counts.items():
                related = snapshot.nodes_by_id.get(related_id) or related_nodes.get(related_id)
                if related is None or related.status != "active":
                    continue
                article_count = (
                    len(snapshot.rollup_story_ids_by_node.get(related_id, set()))
                    if related.kind == "event"
                    else related.article_count
                )
                bucketed[bucket_kind].append(
                    RelatedNode(
                        node_id=related.node_id,
                        kind=related.kind,
                        slug=related.slug,
                        display_name=related.display_name,
                        summary=related.summary,
                        article_count=article_count,
                        score=float(shared_story_count),
                        shared_story_count=shared_story_count,
                        latest_story_at=latest_story_at[bucket_kind].get(related_id),
                    )
                )

        sorted_stories = sorted(
            story_lookup.values(),
            key=lambda story: (story.timestamp_start, story.story_id),
            reverse=True,
        )
        paged_stories = sorted_stories[story_offset : story_offset + story_limit]
        relevant_assignment_ids = descendant_ids if snapshot.is_parent(node_id) else {node_id}
        channel_profiles = {
            story.channel_id: self.repository.get_channel_profile(story.channel_id)
            for story in paged_stories
        }
        story_rows = tuple(
            NodeStory(
                story_id=story.story_id,
                channel_id=story.channel_id,
                channel_title=_channel_title_for_story(story.channel_id, channel_profiles.get(story.channel_id)),
                timestamp_start=story.timestamp_start,
                timestamp_end=story.timestamp_end,
                confidence=max(
                    (
                        assignment.confidence
                        for assignment in assignments_by_story.get(story.story_id, [])
                        if assignment.node_id in relevant_assignment_ids
                    ),
                    default=0.0,
                ),
                preview_text=_preview_text(story.english_combined_text or story.combined_text),
                combined_text=story.english_combined_text or story.combined_text,
                original_preview_text=_preview_text(story.combined_text),
                original_combined_text=story.combined_text,
                media_refs=story.media_refs,
            )
            for story in paged_stories
        )
        child_ids = snapshot.children_by_parent.get(node_id, ())
        excluded_actor_keys = _implicit_parent_actor_keys(node)
        child_events = tuple(
            _build_event_child_summary(
                child=snapshot.node(child_id),
                child_story_ids=set(snapshot.direct_story_ids_by_node.get(child_id, set())),
                assignments_by_story=assignments_by_story,
                related_nodes=related_nodes,
                excluded_actor_keys=excluded_actor_keys,
            )
            for child_id in sorted(
                child_ids,
                key=lambda child_id: (
                    -(snapshot.rollup_last_updated_by_node.get(child_id).timestamp() if snapshot.rollup_last_updated_by_node.get(child_id) is not None else 0.0),
                    -(snapshot.node(child_id).event_start_at.timestamp() if snapshot.node(child_id).event_start_at is not None else 0.0),
                    snapshot.node(child_id).display_name.lower(),
                ),
            )
        )
        return NodeDetail(
            node_id=node.node_id,
            kind=node.kind,
            slug=node.slug,
            display_name=node.display_name,
            summary=node.summary,
            article_count=len(snapshot.rollup_story_ids_by_node.get(node_id, set())),
            parent_event=snapshot.ref_for(node.parent_node_id) if node.parent_node_id else None,
            child_events=child_events,
            events=tuple(_sort_related(bucketed["event"])),
            people=tuple(_sort_related(bucketed["person"])),
            nations=tuple(_sort_related(bucketed["nation"])),
            orgs=tuple(_sort_related(bucketed["org"])),
            places=tuple(_sort_related(bucketed["place"])),
            themes=tuple(_sort_related(bucketed["theme"])),
            stories=story_rows,
        )

    def snapshot_relations(
        self,
        *,
        nodes: Sequence[NodeListEntry],
        channel_ids: Sequence[int] | None = None,
    ) -> list[NodeRelation]:
        if not nodes:
            return []
        selected_ids = {node.node_id for node in nodes}
        allowed_channel_ids = set(channel_ids or ())
        owners_by_assignment_node: dict[str, set[str]] = defaultdict(set)
        event_snapshot = build_event_hierarchy_snapshot(self.repository) if any(node.kind == "event" for node in nodes) else None
        bulk_node_ids: set[str] = set()
        for node in nodes:
            if node.kind == "event" and event_snapshot is not None:
                descendants = event_snapshot.descendant_ids(node.node_id)
                bulk_node_ids.update(descendants)
                for descendant_id in descendants:
                    owners_by_assignment_node[descendant_id].add(node.node_id)
            else:
                bulk_node_ids.add(node.node_id)
                owners_by_assignment_node[node.node_id].add(node.node_id)

        assignments = self.repository.list_story_node_assignments(node_ids=tuple(sorted(bulk_node_ids)))
        selected_by_story: dict[str, set[str]] = defaultdict(set)
        for assignment in assignments:
            for owner_id in owners_by_assignment_node.get(assignment.node_id, ()):
                if owner_id in selected_ids:
                    selected_by_story[assignment.story_id].add(owner_id)

        story_lookup = {
            story.story_id: story
            for story in self.repository.get_story_units_by_ids(sorted(selected_by_story))
        }
        shared_counts: Counter[tuple[str, str]] = Counter()
        latest_story_at: dict[tuple[str, str], datetime | None] = {}
        for story_id, owner_ids in selected_by_story.items():
            story = story_lookup.get(story_id)
            if story is None:
                continue
            if allowed_channel_ids and story.channel_id not in allowed_channel_ids:
                continue
            ordered_ids = sorted(owner_ids)
            for index, left_id in enumerate(ordered_ids):
                for right_id in ordered_ids[index + 1 :]:
                    pair = _canonical_pair(left_id, right_id)
                    shared_counts[pair] += 1
                    current_latest = latest_story_at.get(pair)
                    if story is not None and (current_latest is None or story.timestamp_end > current_latest):
                        latest_story_at[pair] = story.timestamp_end

        return [
            NodeRelation(
                source_node_id=pair[0],
                target_node_id=pair[1],
                relation_type="related",
                score=float(shared_story_count),
                shared_story_count=shared_story_count,
                latest_story_at=latest_story_at.get(pair),
            )
            for pair, shared_story_count in sorted(
                shared_counts.items(),
                key=lambda item: (-item[1], item[0][0], item[0][1]),
            )
            if shared_story_count > 0
        ]

    # ── Message-atomic query methods ──────────────────────────────────────────

    def node_show_messages(
        self,
        *,
        kind: NodeKind,
        slug: str,
        message_limit: int = 20,
        message_offset: int = 0,
    ) -> NodeDetail | None:
        """Message-atomic parallel of node_show(). Returns NodeDetail where the
        `messages` field is populated (not `stories`).
        """
        node = self.repository.get_node_by_slug(kind=kind, slug=slug)
        if node is None:
            return None

        node_id = node.node_id

        # Fetch all message assignments for this node, paginated by assigned_at DESC.
        all_assignments = self.repository.list_message_node_assignments(node_ids=[node_id])
        all_assignments_sorted = sorted(
            all_assignments,
            key=lambda a: (a.assigned_at or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        paged_assignments = all_assignments_sorted[message_offset: message_offset + message_limit]

        # Fetch message objects for paged assignments.
        paged_keys = [(a.channel_id, a.message_id) for a in paged_assignments]
        messages_by_key: dict[tuple[int, int], RawMessage] = {}
        for msg in self.repository.list_raw_messages_by_keys(paged_keys):
            messages_by_key[(msg.channel_id, msg.message_id)] = msg

        # Build channel title lookup.
        channel_profiles: dict[int, ChannelProfile | None] = {}
        for assignment in paged_assignments:
            if assignment.channel_id not in channel_profiles:
                channel_profiles[assignment.channel_id] = self.repository.get_channel_profile(assignment.channel_id)

        message_rows = tuple(
            NodeMessage(
                channel_id=assignment.channel_id,
                message_id=assignment.message_id,
                channel_title=_channel_title_for_story(
                    assignment.channel_id, channel_profiles.get(assignment.channel_id)
                ),
                timestamp=msg.timestamp,
                confidence=assignment.confidence,
                text=msg.english_text or msg.text or "",
                english_text=msg.english_text,
                media_refs=msg.media_refs,
            )
            for assignment in paged_assignments
            if (msg := messages_by_key.get((assignment.channel_id, assignment.message_id))) is not None
        )

        # Related entities: count co-occurring messages.
        # For each other node, count how many messages appear with BOTH this node and that other.
        all_keys_for_node = self.repository.list_message_keys_for_node(node_id)
        all_assignments_for_messages = self.repository.list_message_node_assignments(
            message_keys=all_keys_for_node
        )

        # Build: message_key → set of node_ids assigned to that message.
        message_key_to_nodes: dict[tuple[int, int], set[str]] = defaultdict(set)
        for assignment in all_assignments_for_messages:
            message_key_to_nodes[(assignment.channel_id, assignment.message_id)].add(assignment.node_id)

        # Count co-occurrences: how many messages contain both node_id and some other node.
        co_occurrence: Counter[str] = Counter()
        for key, node_ids_in_msg in message_key_to_nodes.items():
            if node_id not in node_ids_in_msg:
                continue
            for other_node_id in node_ids_in_msg:
                if other_node_id != node_id:
                    co_occurrence[other_node_id] += 1

        # Fetch the related node objects.
        related_node_ids = sorted(co_occurrence)
        related_nodes = {n.node_id: n for n in self.repository.get_nodes(related_node_ids)}

        bucketed: dict[str, list[RelatedNode]] = defaultdict(list)
        for other_id, count in co_occurrence.items():
            related = related_nodes.get(other_id)
            if related is None or related.status != "active":
                continue
            bucketed[related.kind].append(
                RelatedNode(
                    node_id=related.node_id,
                    kind=related.kind,
                    slug=related.slug,
                    display_name=related.display_name,
                    summary=related.summary,
                    article_count=related.article_count,
                    score=float(count),
                    shared_story_count=count,
                    latest_story_at=None,
                )
            )

        # Event hierarchy (deferred — same as existing node_show).
        parent_event = None
        child_events: tuple = ()
        if kind == "event":
            snapshot = build_event_hierarchy_snapshot(self.repository)
            snap_node = snapshot.nodes_by_id.get(node_id)
            if snap_node is not None:
                parent_event = snapshot.ref_for(snap_node.parent_node_id) if snap_node.parent_node_id else None
                child_ids = snapshot.children_by_parent.get(node_id, ())
                excluded_actor_keys = _implicit_parent_actor_keys(snap_node)
                all_msg_assignments_by_story: dict[str, list] = {}  # not used in message path
                child_events = tuple(
                    _build_event_child_summary(
                        child=snapshot.node(child_id),
                        child_story_ids=set(snapshot.direct_story_ids_by_node.get(child_id, set())),
                        assignments_by_story=all_msg_assignments_by_story,
                        related_nodes={},
                        excluded_actor_keys=excluded_actor_keys,
                    )
                    for child_id in sorted(
                        child_ids,
                        key=lambda cid: (
                            -(snapshot.rollup_last_updated_by_node.get(cid).timestamp() if snapshot.rollup_last_updated_by_node.get(cid) is not None else 0.0),
                            -(snapshot.node(cid).event_start_at.timestamp() if snapshot.node(cid).event_start_at is not None else 0.0),
                            snapshot.node(cid).display_name.lower(),
                        ),
                    )
                )

        return NodeDetail(
            node_id=node.node_id,
            kind=node.kind,
            slug=node.slug,
            display_name=node.display_name,
            summary=node.summary,
            article_count=node.article_count,
            parent_event=parent_event,
            child_events=child_events,
            events=tuple(_sort_related(bucketed.get("event", []))),
            people=tuple(_sort_related(bucketed.get("person", []))),
            nations=tuple(_sort_related(bucketed.get("nation", []))),
            orgs=tuple(_sort_related(bucketed.get("org", []))),
            places=tuple(_sort_related(bucketed.get("place", []))),
            themes=tuple(_sort_related(bucketed.get("theme", []))),
            stories=(),
            messages=message_rows,
        )

    def grouped_messages(
        self,
        *,
        node_id: str,
        window: str = "1d",
    ) -> list[MessageGroup]:
        """Query-time grouping of messages assigned to a node, bucketed by time window."""
        # Parse window string.
        _window_map = {"1d": 86400, "3d": 259200, "7d": 604800}
        window_seconds = _window_map.get(window, 86400)
        if window not in _window_map:
            # Try to parse "Nd" pattern.
            if window.endswith("d"):
                try:
                    window_seconds = int(window[:-1]) * 86400
                except ValueError:
                    window_seconds = 86400

        # Fetch all message assignments for this node.
        all_assignments = self.repository.list_message_node_assignments(node_ids=[node_id])
        if not all_assignments:
            return []

        # Fetch message timestamps by batch-loading raw messages.
        all_keys = [(a.channel_id, a.message_id) for a in all_assignments]
        messages_by_key: dict[tuple[int, int], RawMessage] = {}
        for msg in self.repository.list_raw_messages_by_keys(all_keys):
            messages_by_key[(msg.channel_id, msg.message_id)] = msg

        # Fetch channel profiles for channel title resolution.
        channel_ids_needed = {a.channel_id for a in all_assignments}
        channel_profiles: dict[int, ChannelProfile | None] = {
            ch_id: self.repository.get_channel_profile(ch_id) for ch_id in channel_ids_needed
        }

        # Bucket assignments by floor(timestamp / window_seconds).
        buckets: dict[int, list[tuple[MessageNodeAssignment, RawMessage]]] = defaultdict(list)
        for assignment in all_assignments:
            msg = messages_by_key.get((assignment.channel_id, assignment.message_id))
            if msg is None:
                continue
            bucket_index = int(msg.timestamp.timestamp()) // window_seconds
            buckets[bucket_index].append((assignment, msg))

        groups: list[MessageGroup] = []
        for bucket_index, items in buckets.items():
            group_id = hashlib.sha256(f"{node_id}:{bucket_index}".encode()).hexdigest()[:16]
            timestamps = [msg.timestamp for _assignment, msg in items]
            node_messages = tuple(
                NodeMessage(
                    channel_id=assignment.channel_id,
                    message_id=assignment.message_id,
                    channel_title=_channel_title_for_story(
                        assignment.channel_id, channel_profiles.get(assignment.channel_id)
                    ),
                    timestamp=msg.timestamp,
                    confidence=assignment.confidence,
                    text=msg.english_text or msg.text or "",
                    english_text=msg.english_text,
                    media_refs=msg.media_refs,
                )
                for assignment, msg in sorted(items, key=lambda item: item[1].timestamp)
            )
            groups.append(
                MessageGroup(
                    group_id=group_id,
                    dominant_node_id=node_id,
                    messages=node_messages,
                    timestamp_start=min(timestamps),
                    timestamp_end=max(timestamps),
                )
            )

        # Sort groups by timestamp_start DESC.
        groups.sort(key=lambda g: g.timestamp_start, reverse=True)
        return groups
