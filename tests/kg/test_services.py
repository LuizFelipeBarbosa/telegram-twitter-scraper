from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from telegram_scraper.config import Settings
from telegram_scraper.kg.config import KGSettings
from telegram_scraper.kg.math_utils import cosine_similarity
from telegram_scraper.kg.models import (
    ChannelProfile,
    ChannelSummary,
    CrossChannelMatch,
    ExtractedSemanticNode,
    MediaRef,
    Node,
    NodeCentroidRecord,
    NodeDetail,
    NodeListEntry,
    NodeRelation,
    NodeStory,
    RawMessage,
    RelatedNode,
    StoryEmbeddingRecord,
    StoryNodeAssignment,
    StorySemanticExtraction,
    StorySemanticRecord,
    StoryUnit,
    ThemeDailyStat,
    ThemeHeatSnapshot,
    ThemeHistoryPoint,
)
from telegram_scraper.kg.services import KGChannelMaintenanceService, KGChannelRepairService, KGNodeProcessingService, KGQueryService
from telegram_scraper.models import ChatRecord, ChatType


def build_settings(**overrides: str) -> KGSettings:
    values = {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/telegram_kg",
        "REDIS_URL": "redis://localhost:6379/0",
        "PINECONE_API_KEY": "pc-test",
        "OPENAI_API_KEY": "sk-test",
    }
    values.update(overrides)
    return KGSettings.from_mapping(values)


def build_story(
    story_id: str,
    *,
    channel_id: int,
    minute: int,
    combined_text: str,
    english_combined_text: str | None = None,
    message_ids: tuple[int, ...] = (1,),
) -> StoryUnit:
    timestamp = datetime(2026, 4, 9, 12, minute, 0, tzinfo=timezone.utc)
    return StoryUnit(
        story_id=story_id,
        channel_id=channel_id,
        timestamp_start=timestamp,
        timestamp_end=timestamp + timedelta(minutes=1),
        message_ids=message_ids,
        combined_text=combined_text,
        english_combined_text=english_combined_text,
        media_refs=(MediaRef(media_type="photo", storage_path=f"media/{story_id}.jpg"),),
    )


class FakeEmbedder:
    def embed_texts(self, texts):
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "hormuz" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "ceasefire" in lowered:
                vectors.append([0.9, 0.1, 0.0])
            elif "trump" in lowered:
                vectors.append([0.7, 0.2, 0.0])
            else:
                vectors.append([0.0, 1.0, 0.0])
        return vectors


class FakeExtractor:
    def __init__(self, payloads: dict[str, StorySemanticExtraction] | None = None, *, failing_story_ids: set[str] | None = None):
        self.payloads = payloads or {}
        self.failing_story_ids = failing_story_ids or set()

    def extract_story(self, story: StoryUnit) -> StorySemanticExtraction:
        if story.story_id in self.failing_story_ids:
            raise ValueError("malformed response")
        return self.payloads.get(story.story_id, StorySemanticExtraction(story_id=story.story_id))

    def extract_stories(self, stories):
        return [self.extract_story(story) for story in stories]


class RecordingExtractor(FakeExtractor):
    def __init__(self):
        super().__init__()
        self.story_texts: dict[str, str] = {}

    def extract_story(self, story: StoryUnit) -> StorySemanticExtraction:
        self.story_texts[story.story_id] = story.english_combined_text or story.combined_text
        return super().extract_story(story)


class FakeTranslator:
    def __init__(self, translations: dict[tuple[int, int], tuple[str | None, str | None]] | None = None):
        self.translations = translations or {}

    def translate_messages(self, messages):
        translated: list[RawMessage] = []
        translated_at = datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc)
        for message in messages:
            english_text, source_language = self.translations.get(
                (message.channel_id, message.message_id),
                (message.text, "en" if message.text else "und"),
            )
            translated.append(
                replace(
                    message,
                    english_text=english_text,
                    source_language=source_language,
                    translated_at=translated_at,
                )
            )
        return translated


class FakeTelegramClient:
    def __init__(self, chats: list[ChatRecord], message_map: dict[int, list[RawMessage]]):
        self.chats = chats
        self.message_map = message_map

    async def get_dialogs(self):
        return [type("Dialog", (), {"id": chat.chat_id, "entity": type("Entity", (), {"id": chat.chat_id, "broadcast": True, "title": chat.title, "username": chat.username})()})() for chat in self.chats]

    async def iter_message_envelopes(self, chat, *, min_message_id=0, limit=None, reverse=True, offset_id=0):
        del min_message_id, offset_id
        messages = list(self.message_map.get(chat.chat_id, []))
        ordered = sorted(messages, key=lambda item: item.timestamp, reverse=not reverse)
        if limit is not None:
            ordered = ordered[:limit]
        for message in ordered:
            yield type(
                "Envelope",
                (),
                {
                    "record": type(
                        "Record",
                        (),
                        {
                            "posted_at": message.timestamp,
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "sender_name": message.sender_name,
                            "reply_to_message_id": message.reply_to_message_id,
                            "text": message.text or "",
                            "has_media": bool(message.media_refs),
                            "media_files": (),
                            "chat": ChatRecord(
                                chat_id=chat.chat_id,
                                chat_type=ChatType.CHANNEL,
                                title=chat.title,
                                username=chat.username,
                                slug=chat.slug,
                            ),
                        },
                    )(),
                    "raw_json": message.raw_json,
                },
            )()


class FakeVectorStore:
    def __init__(self) -> None:
        self.story_embeddings: dict[str, StoryEmbeddingRecord] = {}
        self.theme_centroids: dict[str, NodeCentroidRecord] = {}
        self.event_centroids: dict[str, NodeCentroidRecord] = {}
        self.deleted_theme_centroids: list[str] = []
        self.deleted_event_centroids: list[str] = []

    def upsert_story_embeddings(self, records):
        for record in records:
            self.story_embeddings[record.story_id] = record

    def update_story_node_ids(self, story_id, node_ids):
        if story_id not in self.story_embeddings:
            return
        self.story_embeddings[story_id] = replace(self.story_embeddings[story_id], node_ids=tuple(node_ids))

    def fetch_story_embeddings(self, story_ids):
        return {
            story_id: list(self.story_embeddings[story_id].embedding)
            for story_id in story_ids
            if story_id in self.story_embeddings
        }

    def query_story_embeddings(self, embedding, *, top_k, exclude_channel_id=None, timestamp_gte=None):
        rows = []
        for record in self.story_embeddings.values():
            if exclude_channel_id is not None and record.channel_id == exclude_channel_id:
                continue
            if timestamp_gte is not None and record.timestamp_start < timestamp_gte:
                continue
            rows.append(
                type(
                    "StoryMatchRow",
                    (),
                    {
                        "story_id": record.story_id,
                        "similarity_score": cosine_similarity(embedding, record.embedding),
                        "metadata": {},
                    },
                )()
            )
        rows.sort(key=lambda row: row.similarity_score, reverse=True)
        return rows[:top_k]

    def upsert_theme_centroids(self, records):
        for record in records:
            self.theme_centroids[record.node_id] = record

    def fetch_theme_centroids(self, node_ids):
        return {
            node_id: list(self.theme_centroids[node_id].embedding)
            for node_id in node_ids
            if node_id in self.theme_centroids
        }

    def query_theme_centroids(self, embedding, *, top_k):
        return self._query_centroids(self.theme_centroids, embedding, top_k)

    def upsert_event_centroids(self, records):
        for record in records:
            self.event_centroids[record.node_id] = record

    def fetch_event_centroids(self, node_ids):
        return {
            node_id: list(self.event_centroids[node_id].embedding)
            for node_id in node_ids
            if node_id in self.event_centroids
        }

    def query_event_centroids(self, embedding, *, top_k):
        return self._query_centroids(self.event_centroids, embedding, top_k)

    def delete_story_embeddings(self, story_ids):
        for story_id in story_ids:
            self.story_embeddings.pop(story_id, None)

    def delete_theme_centroids(self, node_ids):
        for node_id in node_ids:
            self.theme_centroids.pop(node_id, None)
            self.deleted_theme_centroids.append(node_id)

    def delete_event_centroids(self, node_ids):
        for node_id in node_ids:
            self.event_centroids.pop(node_id, None)
            self.deleted_event_centroids.append(node_id)

    def _query_centroids(self, records, embedding, top_k):
        rows = []
        for record in records.values():
            rows.append(
                type(
                    "NodeMatchRow",
                    (),
                    {
                        "node_id": record.node_id,
                        "similarity_score": cosine_similarity(embedding, record.embedding),
                        "metadata": {},
                    },
                )()
            )
        rows.sort(key=lambda row: row.similarity_score, reverse=True)
        return rows[:top_k]


class FakeRepository:
    def __init__(self) -> None:
        self.channel_profiles: dict[int, ChannelProfile] = {}
        self.raw_messages: dict[tuple[int, int], RawMessage] = {}
        self.stories: dict[str, StoryUnit] = {}
        self.nodes: dict[str, Node] = {}
        self.story_nodes: dict[tuple[str, str], StoryNodeAssignment] = {}
        self.story_semantics: dict[str, StorySemanticRecord] = {}
        self.node_relations: dict[tuple[str, str, str], NodeRelation] = {}
        self.cross_channel_matches: list[CrossChannelMatch] = []
        self.theme_daily_stats: dict[tuple[str, date], ThemeDailyStat] = {}
        self.theme_heat_rows: list[ThemeHeatSnapshot] = []
        self.schema_ensured = False

    def ensure_schema(self):
        self.schema_ensured = True

    def upsert_channel_profile(self, profile):
        self.channel_profiles[profile.channel_id] = profile

    def get_channel_profile(self, channel_id):
        return self.channel_profiles.get(channel_id)

    def list_channels(self):
        return [
            ChannelSummary(
                channel_id=story.channel_id,
                channel_title=str(story.channel_id),
                story_count=len([item for item in self.stories.values() if item.channel_id == story.channel_id]),
            )
            for story in {item.channel_id: item for item in self.stories.values()}.values()
        ]

    def upsert_raw_messages(self, messages):
        for message in messages:
            self.raw_messages[(message.channel_id, message.message_id)] = message

    def list_unsegmented_raw_messages(self, channel_id, *, limit=None):
        story_message_ids = {
            message_id
            for story in self.stories.values()
            if story.channel_id == channel_id
            for message_id in story.message_ids
        }
        rows = [
            message
            for key, message in self.raw_messages.items()
            if key[0] == channel_id and message.message_id not in story_message_ids
        ]
        rows.sort(key=lambda message: message.timestamp)
        return rows[:limit] if limit is not None else rows

    def list_recent_raw_messages(self, channel_id, *, limit):
        rows = [message for key, message in self.raw_messages.items() if key[0] == channel_id]
        rows.sort(key=lambda message: message.timestamp)
        return rows[-limit:]

    def list_raw_messages(self, channel_id):
        rows = [message for key, message in self.raw_messages.items() if key[0] == channel_id]
        rows.sort(key=lambda message: message.timestamp)
        return rows

    def save_raw_message_translations(self, messages):
        for message in messages:
            self.raw_messages[(message.channel_id, message.message_id)] = message

    def get_last_story_unit(self, channel_id):
        stories = self.list_recent_story_units(channel_id, limit=1)
        return stories[0] if stories else None

    def list_recent_story_units(self, channel_id, *, limit):
        rows = [story for story in self.stories.values() if story.channel_id == channel_id]
        rows.sort(key=lambda story: story.timestamp_end, reverse=True)
        return rows[:limit]

    def list_story_units(self, *, channel_id=None):
        rows = list(self.stories.values())
        if channel_id is not None:
            rows = [story for story in rows if story.channel_id == channel_id]
        return sorted(rows, key=lambda story: story.timestamp_start)

    def get_story_messages(self, story_id):
        story = self.stories.get(story_id)
        if story is None:
            return []
        rows = [
            self.raw_messages[(story.channel_id, message_id)]
            for message_id in story.message_ids
            if (story.channel_id, message_id) in self.raw_messages
        ]
        rows.sort(key=lambda message: message.timestamp)
        return rows

    def save_story_units(self, stories):
        for story in stories:
            self.stories[story.story_id] = story

    def list_stories_without_semantics(self, *, channel_id=None, limit=None):
        rows = [
            story
            for story in self.list_story_units(channel_id=channel_id)
            if story.story_id not in self.story_semantics
        ]
        return rows[:limit] if limit is not None else rows

    def get_story_unit(self, story_id):
        return self.stories.get(story_id)

    def upsert_story_semantics(self, records):
        for record in records:
            self.story_semantics[record.story_id] = record

    def save_semantic_results(self, *, nodes, assignments, semantics, cross_channel_matches=()):
        self.save_nodes(nodes)
        self.save_story_node_assignments(assignments)
        self.upsert_story_semantics(semantics)
        self.save_cross_channel_matches(cross_channel_matches)

    def get_story_semantic_record(self, story_id):
        return self.story_semantics.get(story_id)

    def save_nodes(self, nodes):
        for node in nodes:
            self.nodes[node.node_id] = node

    def get_nodes(self, node_ids):
        return [self.nodes[node_id] for node_id in node_ids if node_id in self.nodes]

    def list_nodes(self, *, kind=None, status="active", limit=None):
        rows = [node for node in self.nodes.values() if (kind is None or node.kind == kind) and (status is None or node.status == status)]
        rows.sort(key=lambda node: (-node.article_count, node.slug))
        return rows[:limit] if limit is not None else rows

    def get_node_by_slug(self, *, kind, slug):
        for node in self.nodes.values():
            if node.kind == kind and node.slug == slug:
                return node
        return None

    def save_node_relations(self, relations):
        for relation in relations:
            self.node_relations[(relation.source_node_id, relation.target_node_id, relation.relation_type)] = relation

    def replace_node_relations(self, relations):
        self.node_relations = {}
        self.save_node_relations(relations)

    def list_node_relations(self, node_id):
        rows = [
            relation
            for relation in self.node_relations.values()
            if relation.source_node_id == node_id or relation.target_node_id == node_id
        ]
        rows.sort(key=lambda relation: (-relation.score, relation.source_node_id, relation.target_node_id))
        return rows

    def save_story_node_assignments(self, assignments):
        for assignment in assignments:
            self.story_nodes[(assignment.story_id, assignment.node_id)] = assignment

    def delete_story_node_assignments(self, *, node_id=None, story_ids=None):
        story_ids = set(story_ids or [])
        for key in list(self.story_nodes):
            current_story_id, current_node_id = key
            if node_id is not None and current_node_id != node_id:
                continue
            if story_ids and current_story_id not in story_ids:
                continue
            del self.story_nodes[key]

    def get_story_node_assignments(self, story_id):
        rows = [assignment for (current_story_id, _), assignment in self.story_nodes.items() if current_story_id == story_id]
        rows.sort(key=lambda assignment: (not assignment.is_primary_event, -assignment.confidence, assignment.node_id))
        return rows

    def list_story_node_ids(self, story_id):
        return [assignment.node_id for assignment in self.get_story_node_assignments(story_id)]

    def list_story_ids_for_node_on_date(self, node_id, day):
        return [
            story_id
            for (story_id, current_node_id), assignment in sorted(self.story_nodes.items())
            if current_node_id == node_id and self.stories[story_id].timestamp_start.date() == day
        ]

    def list_story_ids_for_node(self, node_id):
        return sorted(story_id for (story_id, current_node_id) in self.story_nodes if current_node_id == node_id)

    def list_stories_for_node(self, node_id, *, limit, offset):
        rows = [
            (self.stories[story_id], assignment)
            for (story_id, current_node_id), assignment in self.story_nodes.items()
            if current_node_id == node_id
        ]
        rows.sort(key=lambda item: item[0].timestamp_start, reverse=True)
        return len(rows), rows[offset : offset + limit]

    def save_cross_channel_matches(self, matches):
        self.cross_channel_matches.extend(matches)

    def replace_cross_channel_matches(self, matches):
        self.cross_channel_matches = list(matches)

    def list_cross_channel_matches(self):
        return list(self.cross_channel_matches)

    def save_theme_daily_stats(self, stats):
        for stat in stats:
            self.theme_daily_stats[(stat.node_id, stat.date)] = stat

    def refresh_theme_heat_view(self):
        rows: list[ThemeHeatSnapshot] = []
        total_recent = max(len(self.stories), 1)
        for theme in self.list_nodes(kind="theme"):
            article_count = len(self.list_story_ids_for_node(theme.node_id))
            heat = article_count / total_recent
            rows.append(
                ThemeHeatSnapshot(
                    node_id=theme.node_id,
                    slug=theme.slug,
                    display_name=theme.display_name,
                    article_count=article_count,
                    heat_1d=heat,
                    heat_3d=heat,
                    heat_5d=heat,
                    heat_7d=heat,
                    heat_14d=heat,
                    heat_31d=heat / 2,
                    phase="emerging" if heat > 0 else "steady",
                )
            )
        self.theme_heat_rows = rows

    def clear_semantic_state(self, *, channel_id=None):
        story_ids = [story.story_id for story in self.list_story_units(channel_id=channel_id)]
        affected_node_ids = sorted({node_id for (story_id, node_id) in self.story_nodes if story_id in story_ids})
        for story_id in story_ids:
            self.story_semantics.pop(story_id, None)
        self.story_nodes = {
            key: assignment
            for key, assignment in self.story_nodes.items()
            if key[0] not in story_ids
        }
        self.cross_channel_matches = [
            match
            for match in self.cross_channel_matches
            if match.story_id not in story_ids and match.matched_story_id not in story_ids
        ]
        self.node_relations = {
            key: relation
            for key, relation in self.node_relations.items()
            if relation.source_node_id not in affected_node_ids and relation.target_node_id not in affected_node_ids
        }
        self.theme_daily_stats = {
            key: stat
            for key, stat in self.theme_daily_stats.items()
            if key[0] not in affected_node_ids
        }
        deleted_theme_ids: list[str] = []
        deleted_event_ids: list[str] = []
        for node_id in affected_node_ids:
            remaining = self.list_story_ids_for_node(node_id)
            node = self.nodes.get(node_id)
            if node is None:
                continue
            if not remaining:
                if node.kind == "theme":
                    deleted_theme_ids.append(node_id)
                if node.kind == "event":
                    deleted_event_ids.append(node_id)
                del self.nodes[node_id]
                continue
            self.nodes[node_id] = replace(node, article_count=len(remaining))
        return story_ids, deleted_theme_ids, deleted_event_ids

    def clear_story_state(self, *, channel_id):
        story_ids, deleted_theme_ids, deleted_event_ids = self.clear_semantic_state(channel_id=channel_id)
        self.stories = {
            story_id: story
            for story_id, story in self.stories.items()
            if story.channel_id != channel_id
        }
        return story_ids, deleted_theme_ids, deleted_event_ids

    def run_with_advisory_lock(self, lock_name, callback):
        del lock_name
        callback()
        return True

    def list_theme_heat(self, *, phase=None, limit=None):
        rows = [row for row in self.theme_heat_rows if phase is None or row.phase == phase]
        rows.sort(key=lambda row: (-row.heat_1d, row.slug))
        return rows[:limit] if limit is not None else rows

    def get_theme_history(self, *, slug):
        theme = self.get_node_by_slug(kind="theme", slug=slug)
        if theme is None:
            return []
        rows = [
            ThemeHistoryPoint(
                node_id=theme.node_id,
                slug=theme.slug,
                display_name=theme.display_name,
                date=day,
                article_count=stat.article_count,
                centroid_drift=stat.centroid_drift,
            )
            for (node_id, day), stat in sorted(self.theme_daily_stats.items(), key=lambda item: item[0][1])
            if node_id == theme.node_id
        ]
        return rows

    def list_node_entries(self, *, kind, limit=None):
        rows = [
            NodeListEntry(
                node_id=node.node_id,
                kind=node.kind,
                slug=node.slug,
                display_name=node.display_name,
                summary=node.summary,
                article_count=node.article_count,
                last_updated=node.last_updated,
            )
            for node in self.list_nodes(kind=kind)
        ]
        return rows[:limit] if limit is not None else rows

    def get_node_detail(self, *, kind, slug, story_limit=20, story_offset=0):
        node = self.get_node_by_slug(kind=kind, slug=slug)
        if node is None:
            return None
        related_lookup = {
            "event": [],
            "person": [],
            "nation": [],
            "org": [],
            "place": [],
            "theme": [],
        }
        for relation in self.list_node_relations(node.node_id):
            related_id = relation.target_node_id if relation.source_node_id == node.node_id else relation.source_node_id
            related = self.nodes[related_id]
            related_lookup[related.kind].append(
                RelatedNode(
                    node_id=related.node_id,
                    kind=related.kind,
                    slug=related.slug,
                    display_name=related.display_name,
                    summary=related.summary,
                    article_count=related.article_count,
                    score=relation.score,
                    shared_story_count=relation.shared_story_count,
                    latest_story_at=relation.latest_story_at,
                )
            )
        _total, stories = self.list_stories_for_node(node.node_id, limit=story_limit, offset=story_offset)
        story_rows = tuple(
            NodeStory(
                story_id=story.story_id,
                channel_id=story.channel_id,
                channel_title=str(story.channel_id),
                timestamp_start=story.timestamp_start,
                timestamp_end=story.timestamp_end,
                confidence=assignment.confidence,
                preview_text=story.combined_text[:60],
                combined_text=story.english_combined_text or story.combined_text,
                original_preview_text=story.combined_text[:60],
                original_combined_text=story.combined_text,
                media_refs=story.media_refs,
            )
            for story, assignment in stories
        )
        return NodeDetail(
            node_id=node.node_id,
            kind=node.kind,
            slug=node.slug,
            display_name=node.display_name,
            summary=node.summary,
            article_count=node.article_count,
            events=tuple(related_lookup["event"]),
            people=tuple(related_lookup["person"]),
            nations=tuple(related_lookup["nation"]),
            orgs=tuple(related_lookup["org"]),
            places=tuple(related_lookup["place"]),
            themes=tuple(related_lookup["theme"]),
            stories=story_rows,
        )


class FakeProjectionService:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_all(self, *, days=31):
        del days
        self.calls += 1
        return type(
            "ProjectionResult",
            (),
            {
                "relations_created": 11,
                "theme_stats_written": 7,
            },
        )()


class KGNodeServiceTests(unittest.TestCase):
    def test_node_processing_reuses_canonical_nodes_and_sets_single_primary_event(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        story_a = build_story("story-a", channel_id=100, minute=0, combined_text="Trump Iran Hormuz ceasefire")
        story_b = build_story("story-b", channel_id=200, minute=1, combined_text="President Trump Iran Hormuz ceasefire")
        repository.save_story_units([story_a, story_b])
        vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(story_a.story_id, [1.0, 0.0, 0.0], 100, story_a.timestamp_start),
                StoryEmbeddingRecord(story_b.story_id, [0.95, 0.05, 0.0], 200, story_b.timestamp_start),
            ]
        )

        extractor = FakeExtractor(
            {
                "story-a": StorySemanticExtraction(
                    story_id="story-a",
                    events=(
                        ExtractedSemanticNode(name="April 8 Hormuz Reclosure", start_at=datetime(2026, 4, 8, tzinfo=timezone.utc)),
                        ExtractedSemanticNode(name="April 9 Follow-up Talks", start_at=datetime(2026, 4, 9, tzinfo=timezone.utc)),
                    ),
                    people=(ExtractedSemanticNode(name="Donald Trump", aliases=("President Trump",)),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    orgs=(ExtractedSemanticNode(name="IDF"),),
                    places=(ExtractedSemanticNode(name="Strait of Hormuz"),),
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                    primary_event="April 8 Hormuz Reclosure",
                ),
                "story-b": StorySemanticExtraction(
                    story_id="story-b",
                    events=(ExtractedSemanticNode(name="April 8 Hormuz Reclosure", start_at=datetime(2026, 4, 8, tzinfo=timezone.utc)),),
                    people=(ExtractedSemanticNode(name="President Trump"),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    orgs=(ExtractedSemanticNode(name="IDF"),),
                    places=(ExtractedSemanticNode(name="Strait of Hormuz"),),
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                    primary_event="April 8 Hormuz Reclosure",
                ),
            }
        )

        result = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_stories([story_a, story_b])

        self.assertEqual(result.nodes_created, 7)
        self.assertEqual(result.assignments_created, 13)
        self.assertGreater(result.cross_channel_matches, 0)
        slugs = {node.slug for node in repository.nodes.values()}
        self.assertIn("donald-trump", slugs)
        self.assertIn("iran", slugs)
        self.assertIn("idf", slugs)
        self.assertIn("strait-of-hormuz", slugs)
        self.assertIn("ceasefire-peace-negotiations", slugs)
        self.assertIn("april-8-hormuz-reclosure", slugs)
        self.assertEqual(len([node for node in repository.nodes.values() if node.kind == "person"]), 1)
        primary_events = [assignment for assignment in repository.get_story_node_assignments("story-a") if assignment.is_primary_event]
        self.assertEqual(len(primary_events), 1)

        detail = KGQueryService(repository).node_show(kind="event", slug="april-8-hormuz-reclosure")
        assert detail is not None
        self.assertEqual(detail.people[0].slug, "donald-trump")
        self.assertEqual(detail.nations[0].slug, "iran")
        self.assertEqual(detail.orgs[0].slug, "idf")
        self.assertEqual(detail.themes[0].slug, "ceasefire-peace-negotiations")
        actors_count = len(detail.people) + len(detail.nations) + len(detail.orgs)
        self.assertEqual(actors_count, 3)

    def test_processing_handles_oversized_or_malformed_extraction_without_crashing(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        huge_story = build_story("story-huge", channel_id=100, minute=2, combined_text="x" * 40000)
        repository.save_story_units([huge_story])

        result = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=FakeExtractor(failing_story_ids={"story-huge"}),
            settings=settings,
        ).process_stories([huge_story])

        self.assertEqual(result.nodes_created, 0)
        self.assertEqual(result.assignments_created, 0)
        self.assertIn("story-huge", repository.story_semantics)

    def test_channel_rebuild_preserves_story_units_and_recreates_deterministic_slugs(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        story = build_story("story-rebuild", channel_id=100, minute=3, combined_text="Trump Iran Hormuz ceasefire")
        repository.save_story_units([story])
        vector_store.upsert_story_embeddings([StoryEmbeddingRecord(story.story_id, [1.0, 0.0, 0.0], 100, story.timestamp_start)])

        extractor = FakeExtractor(
            {
                "story-rebuild": StorySemanticExtraction(
                    story_id="story-rebuild",
                    events=(ExtractedSemanticNode(name="April 8 Hormuz Reclosure", start_at=datetime(2026, 4, 8, tzinfo=timezone.utc)),),
                    people=(ExtractedSemanticNode(name="Donald Trump"),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    orgs=(ExtractedSemanticNode(name="IDF"),),
                    places=(ExtractedSemanticNode(name="Strait of Hormuz"),),
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                    primary_event="April 8 Hormuz Reclosure",
                )
            }
        )

        service = KGChannelMaintenanceService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        )

        first = service.rebuild_channel(100)
        first_slugs = sorted(node.slug for node in repository.nodes.values())
        reset = service.reset_channel(100)
        second = service.rebuild_channel(100)
        second_slugs = sorted(node.slug for node in repository.nodes.values())

        self.assertEqual(first.nodes_created, 6)
        self.assertEqual(reset.stories_preserved, 1)
        self.assertIn("story-rebuild", repository.stories)
        self.assertEqual(second.nodes_created, 6)
        self.assertEqual(first_slugs, second_slugs)

    def test_historical_rebuild_channels_skips_cross_channel_matches_and_refreshes_once(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        projection_service = FakeProjectionService()
        story_a = build_story("story-a", channel_id=100, minute=0, combined_text="Trump Iran Hormuz ceasefire")
        story_b = build_story("story-b", channel_id=200, minute=1, combined_text="Trump Iran Hormuz ceasefire")
        repository.save_story_units([story_a, story_b])
        vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(story_a.story_id, [1.0, 0.0, 0.0], 100, story_a.timestamp_start),
                StoryEmbeddingRecord(story_b.story_id, [0.99, 0.01, 0.0], 200, story_b.timestamp_start),
            ]
        )
        extractor = FakeExtractor(
            {
                "story-a": StorySemanticExtraction(
                    story_id="story-a",
                    people=(ExtractedSemanticNode(name="Donald Trump"),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
                "story-b": StorySemanticExtraction(
                    story_id="story-b",
                    people=(ExtractedSemanticNode(name="Donald Trump"),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
            }
        )
        node_service = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
            projection_service=projection_service,
        )
        service = KGChannelMaintenanceService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
            node_service=node_service,
        )

        result = service.rebuild_channels((100, 200), workers=2)

        self.assertEqual(result.channels_processed, 2)
        self.assertEqual(result.stories_processed, 2)
        self.assertEqual(projection_service.calls, 1)
        self.assertEqual(result.relations_created, 11)
        self.assertEqual(result.theme_stats_written, 7)
        self.assertEqual(repository.cross_channel_matches, [])

    def test_repair_channels_rebuilds_story_units_from_raw_messages_and_uses_translated_english_text(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        app_settings = Settings.from_mapping(
            {
                "TG_API_ID": "123",
                "TG_API_HASH": "hash",
                "TG_PHONE": "+15555555555",
                "SINCE_DATE": "2026-02-28T00:00:00Z",
            }
        )
        channel_id = -1001006487902
        chat = ChatRecord(
            chat_id=channel_id,
            chat_type=ChatType.CHANNEL,
            title="Press TV",
            username="presstv",
            slug="presstv",
        )
        repository.upsert_channel_profile(ChannelProfile(channel_id=channel_id, channel_title="Press TV"))
        repository.upsert_raw_messages(
            [
                RawMessage(
                    channel_id=channel_id,
                    message_id=1,
                    timestamp=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
                    sender_id=None,
                    sender_name=None,
                    text="سلام بر ایران",
                    raw_json={"id": 1},
                )
            ]
        )
        repository.save_story_units([build_story("stale-story", channel_id=channel_id, minute=0, combined_text="stale", message_ids=(1,))])

        incoming_messages = {
            channel_id: [
                RawMessage(
                    channel_id=channel_id,
                    message_id=3,
                    timestamp=datetime(2026, 4, 11, 12, 5, tzinfo=timezone.utc),
                    sender_id=None,
                    sender_name=None,
                    text="New English story",
                    raw_json={"id": 3},
                ),
                RawMessage(
                    channel_id=channel_id,
                    message_id=2,
                    timestamp=datetime(2026, 4, 9, 10, 5, tzinfo=timezone.utc),
                    sender_id=None,
                    sender_name=None,
                    text="پیام دوم",
                    raw_json={"id": 2},
                ),
            ]
        }
        extractor = RecordingExtractor()
        translator = FakeTranslator(
            {
                (channel_id, 1): ("Hello Iran", "fa"),
                (channel_id, 2): ("Second message", "fa"),
                (channel_id, 3): ("New English story", "en"),
            }
        )
        service = KGChannelRepairService(
            app_settings=app_settings,
            telegram_client=FakeTelegramClient([chat], incoming_messages),
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
            translator=translator,
        )

        result = asyncio.run(service.repair_channels([channel_id], workers=1))

        self.assertEqual(result.channels_processed, 1)
        self.assertEqual(result.messages_upserted, 2)
        self.assertEqual(result.stories_rebuilt, 2)
        self.assertNotIn("stale-story", repository.stories)
        rebuilt_stories = repository.list_story_units(channel_id=channel_id)
        self.assertEqual(len(rebuilt_stories), 2)
        self.assertEqual(rebuilt_stories[0].english_combined_text, "Hello Iran\nSecond message")
        self.assertIn(rebuilt_stories[0].story_id, extractor.story_texts)
        self.assertEqual(extractor.story_texts[rebuilt_stories[0].story_id], "Hello Iran\nSecond message")

    def test_sync_status_reports_telegram_ingest_and_story_lag(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        app_settings = Settings.from_mapping(
            {
                "TG_API_ID": "123",
                "TG_API_HASH": "hash",
                "TG_PHONE": "+15555555555",
                "SINCE_DATE": "2026-02-28T00:00:00Z",
            }
        )
        channel_id = -1001361890342
        chat = ChatRecord(
            chat_id=channel_id,
            chat_type=ChatType.CHANNEL,
            title="Amir Tsarfati",
            username="beholdisraelchannel",
            slug="beholdisraelchannel",
        )
        raw_message = RawMessage(
            channel_id=channel_id,
            message_id=10,
            timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
            sender_id=None,
            sender_name=None,
            text="Stored raw message",
            raw_json={"id": 10},
            english_text="Stored raw message",
            source_language="en",
            translated_at=datetime(2026, 4, 10, 12, 1, tzinfo=timezone.utc),
        )
        repository.upsert_raw_messages([raw_message])
        repository.save_story_units(
            [
                build_story(
                    "story-sync",
                    channel_id=channel_id,
                    minute=0,
                    combined_text="Stored story",
                    english_combined_text="Stored story",
                    message_ids=(10,),
                )
            ]
        )
        latest_visible = RawMessage(
            channel_id=channel_id,
            message_id=11,
            timestamp=datetime(2026, 4, 11, 15, 0, tzinfo=timezone.utc),
            sender_id=None,
            sender_name=None,
            text="Latest telegram message",
            raw_json={"id": 11},
        )
        service = KGChannelRepairService(
            app_settings=app_settings,
            telegram_client=FakeTelegramClient([chat], {channel_id: [latest_visible]}),
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=FakeExtractor(),
            settings=settings,
            translator=FakeTranslator(),
        )

        statuses = asyncio.run(service.sync_status([channel_id]))

        self.assertEqual(len(statuses), 1)
        status = statuses[0]
        self.assertEqual(status.channel_id, channel_id)
        self.assertEqual(status.raw_message_count, 1)
        self.assertEqual(status.story_count, 1)
        self.assertEqual(status.ingested_latest_at, raw_message.timestamp)
        self.assertEqual(status.telegram_latest_at, latest_visible.timestamp)


if __name__ == "__main__":
    unittest.main()
