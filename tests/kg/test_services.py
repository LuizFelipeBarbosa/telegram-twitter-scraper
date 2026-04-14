from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from telegram_scraper.config import Settings
from telegram_scraper.kg.config import KGSettings
from telegram_scraper.kg.math_utils import cosine_similarity
from telegram_scraper.kg.event_hierarchy import KGEventHierarchyService
from telegram_scraper.kg.models import (
    ChannelProfile,
    ChannelSummary,
    CrossChannelMatch,
    CrossChannelMessageMatch,
    ExtractedSemanticNode,
    MediaRef,
    MessageEmbeddingRecord,
    MessageMatch,
    MessageNodeAssignment,
    MessageSemanticExtraction,
    MessageSemanticRecord,
    Node,
    NodeCentroidRecord,
    NodeDetail,
    NodeListEntry,
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
from telegram_scraper.kg.services import KGChannelMaintenanceService, KGChannelRepairService, KGNodeProcessingService, KGProcessingResult, KGProcessingWorker, KGQueryService
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
    def __init__(
        self,
        payloads: dict[str, StorySemanticExtraction] | None = None,
        *,
        failing_story_ids: set[str] | None = None,
        message_payloads: dict[tuple[int, int], MessageSemanticExtraction] | None = None,
        failing_message_keys: set[tuple[int, int]] | None = None,
    ):
        self.payloads = payloads or {}
        self.failing_story_ids = failing_story_ids or set()
        self.message_payloads = message_payloads or {}
        self.failing_message_keys = failing_message_keys or set()

    def extract_story(self, story: StoryUnit) -> StorySemanticExtraction:
        if story.story_id in self.failing_story_ids:
            raise ValueError("malformed response")
        return self.payloads.get(story.story_id, StorySemanticExtraction(story_id=story.story_id))

    def extract_stories(self, stories):
        return [self.extract_story(story) for story in stories]

    def extract_message(self, message: RawMessage) -> MessageSemanticExtraction:
        key = (message.channel_id, message.message_id)
        if key in self.failing_message_keys:
            raise ValueError("malformed response")
        return self.message_payloads.get(
            key,
            MessageSemanticExtraction(channel_id=message.channel_id, message_id=message.message_id),
        )

    def extract_messages(self, messages, *, max_workers=None):
        return [self.extract_message(msg) for msg in messages]


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
        self.message_embeddings: dict[tuple[int, int], MessageEmbeddingRecord] = {}

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

    def upsert_message_embeddings(self, records):
        for record in records:
            self.message_embeddings[(record.channel_id, record.message_id)] = record

    def fetch_message_embeddings(self, keys):
        return {
            key: list(self.message_embeddings[key].embedding)
            for key in keys
            if key in self.message_embeddings
        }

    def query_message_embeddings(self, embedding, *, top_k, exclude_channel_id=None, timestamp_gte=None):
        rows = []
        for record in self.message_embeddings.values():
            if exclude_channel_id is not None and record.channel_id == exclude_channel_id:
                continue
            if timestamp_gte is not None and record.timestamp < timestamp_gte:
                continue
            rows.append(
                MessageMatch(
                    channel_id=record.channel_id,
                    message_id=record.message_id,
                    similarity_score=cosine_similarity(embedding, record.embedding),
                    metadata={},
                )
            )
        rows.sort(key=lambda row: row.similarity_score, reverse=True)
        return rows[:top_k]

    def delete_message_embeddings(self, keys):
        for key in keys:
            self.message_embeddings.pop(key, None)

    def update_message_node_ids(self, *, channel_id, message_id, node_ids):
        key = (channel_id, message_id)
        if key not in self.message_embeddings:
            return
        old = self.message_embeddings[key]
        self.message_embeddings[key] = replace(old, node_ids=tuple(node_ids))


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
        self.theme_heat_rows: list[NodeHeatSnapshot] = []
        self.schema_ensured = False
        # Message-atomic pipeline stores
        self.message_semantics: dict[tuple[int, int], MessageSemanticRecord] = {}
        self.message_nodes: dict[tuple[int, int, str], MessageNodeAssignment] = {}
        self.cross_channel_message_matches: list[CrossChannelMessageMatch] = []
        self.embedded_messages: set[tuple[int, int]] = set()
        self.extracted_messages: set[tuple[int, int]] = set()

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

    def get_story_units_by_ids(self, story_ids):
        return [self.stories[story_id] for story_id in story_ids if story_id in self.stories]

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

    def get_node_by_slug(self, *, kind, slug, status="active"):
        for node in self.nodes.values():
            if node.kind == kind and node.slug == slug and (status is None or node.status == status):
                return node
        return None

    def get_node_support_records(self, node_ids):
        story_ids_by_node: dict[str, set[str]] = {}
        channel_ids_by_node: dict[str, set[int]] = {}
        cross_story_ids = {
            match.story_id
            for match in self.cross_channel_matches
        } | {
            match.matched_story_id
            for match in self.cross_channel_matches
        }
        for story_id, node_id in self.story_nodes:
            story_ids_by_node.setdefault(node_id, set()).add(story_id)
            channel_ids_by_node.setdefault(node_id, set()).add(self.stories[story_id].channel_id)
        return [
            NodeSupportRecord(
                node_id=node_id,
                story_count=len(story_ids_by_node.get(node_id, set())),
                channel_count=len(channel_ids_by_node.get(node_id, set())),
                has_cross_channel_match=bool(story_ids_by_node.get(node_id, set()) & cross_story_ids),
                channel_ids=tuple(sorted(channel_ids_by_node.get(node_id, set()))),
            )
            for node_id in node_ids
            if node_id in self.nodes
        ]

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

    def list_story_node_assignments(self, *, story_ids=None, node_ids=None):
        story_id_filter = set(story_ids or [])
        node_id_filter = set(node_ids or [])
        rows = []
        for (_story_id, _node_id), assignment in self.story_nodes.items():
            if story_id_filter and assignment.story_id not in story_id_filter:
                continue
            if node_id_filter and assignment.node_id not in node_id_filter:
                continue
            rows.append(assignment)
        rows.sort(key=lambda assignment: (assignment.story_id, not assignment.is_primary_event, -assignment.confidence, assignment.node_id))
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

    # ── Message-atomic pipeline methods ──────────────────────────────────────

    def upsert_message_semantics(self, records):
        for record in records:
            self.message_semantics[(record.channel_id, record.message_id)] = record

    def get_message_semantic_record(self, *, channel_id, message_id):
        return self.message_semantics.get((channel_id, message_id))

    def save_message_node_assignments(self, assignments):
        for assignment in assignments:
            self.message_nodes[(assignment.channel_id, assignment.message_id, assignment.node_id)] = assignment

    def list_message_node_assignments(self, *, message_keys=None, node_ids=None):
        # Mirror the real repository guard: prevent accidental full-table scans.
        if message_keys is None and node_ids is None:
            return []
        key_filter = set(tuple(k) for k in (message_keys or []))
        node_filter = set(node_ids or [])
        rows = []
        for (ch_id, msg_id, node_id), assignment in self.message_nodes.items():
            if key_filter and (ch_id, msg_id) not in key_filter:
                continue
            if node_filter and node_id not in node_filter:
                continue
            rows.append(assignment)
        return rows

    def list_message_keys_for_node(self, node_id):
        return [(ch_id, msg_id) for (ch_id, msg_id, nid) in self.message_nodes if nid == node_id]

    def save_cross_channel_message_matches(self, matches):
        self.cross_channel_message_matches.extend(matches)

    def list_cross_channel_message_matches(self, *, channel_id=None, message_id=None):
        rows = list(self.cross_channel_message_matches)
        if channel_id is not None:
            rows = [m for m in rows if m.channel_id == channel_id or m.matched_channel_id == channel_id]
        if message_id is not None:
            rows = [m for m in rows if m.message_id == message_id or m.matched_message_id == message_id]
        return rows

    def mark_message_embedded(self, *, channel_id, message_id, version):
        self.embedded_messages.add((channel_id, message_id))

    def mark_messages_extracted(self, keys):
        for key in keys:
            self.extracted_messages.add(tuple(key))

    def list_messages_without_embeddings(self, *, channel_id=None, limit=None):
        rows = [
            msg for key, msg in self.raw_messages.items()
            if key not in self.embedded_messages and (channel_id is None or msg.channel_id == channel_id)
        ]
        rows.sort(key=lambda m: m.timestamp)
        return rows[:limit] if limit is not None else rows

    def list_messages_without_semantics(self, *, channel_id=None, limit=None):
        rows = [
            msg for key, msg in self.raw_messages.items()
            if key not in self.message_semantics and (channel_id is None or msg.channel_id == channel_id)
        ]
        rows.sort(key=lambda m: m.timestamp)
        return rows[:limit] if limit is not None else rows

    def refresh_message_heat_view(self):
        pass

    def list_message_heat_rows(self, *, kind):
        return []

    def list_message_keys_for_node_on_date(self, node_id, day):
        return [
            (ch_id, msg_id)
            for (ch_id, msg_id, nid) in self.message_nodes
            if nid == node_id
            and (ch_id, msg_id) in self.raw_messages
            and self.raw_messages[(ch_id, msg_id)].timestamp.date() == day
        ]

    def get_raw_message(self, *, channel_id, message_id):
        return self.raw_messages.get((channel_id, message_id))

    def list_raw_messages_by_keys(self, keys):
        result = []
        for key in keys:
            msg = self.raw_messages.get(tuple(key))
            if msg is not None:
                result.append(msg)
        result.sort(key=lambda m: m.timestamp)
        return result

    def list_candidate_channel_ids(self):
        return list({msg.channel_id for msg in self.raw_messages.values()})

    def list_node_ids_for_channels(self, *, channel_ids, status="active"):
        return []

    def save_theme_daily_stats(self, stats):
        for stat in stats:
            self.theme_daily_stats[(stat.node_id, stat.date)] = stat

    def refresh_theme_heat_view(self):
        rows: list[NodeHeatSnapshot] = []
        total_recent = max(len(self.stories), 1)
        for theme in self.list_nodes(kind="theme"):
            article_count = len(self.list_story_ids_for_node(theme.node_id))
            heat = article_count / total_recent
            rows.append(
                NodeHeatSnapshot(
                    node_id=theme.node_id,
                    kind="theme",
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

    def delete_nodes(self, node_ids):
        for node_id in node_ids:
            self.nodes.pop(node_id, None)

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

    def refresh_node_heat_view(self):
        self.refresh_theme_heat_view()

    def list_node_heat_rows(self, *, kind):
        from dataclasses import replace
        if kind != "theme":
            return []
        return [replace(row, phase=None) for row in self.theme_heat_rows]

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
        self.refresh_all_calls = 0
        self.refresh_all_from_messages_calls = 0

    def refresh_all(self, *, days=31):
        del days
        self.calls += 1
        self.refresh_all_calls += 1
        return type(
            "ProjectionResult",
            (),
            {
                "relations_created": 11,
                "theme_stats_written": 7,
            },
        )()

    def refresh_all_from_messages(self, *, days=31):
        del days
        self.calls += 1
        self.refresh_all_from_messages_calls += 1
        return type(
            "ProjectionResult",
            (),
            {
                "relations_created": 11,
                "theme_stats_written": 7,
            },
        )()


class FakeStreamEntry:
    def __init__(self, entry_id: str, payload: RawMessage) -> None:
        self.entry_id = entry_id
        self.payload = payload


class FakeStream:
    def __init__(self, entries: list[FakeStreamEntry] | None = None) -> None:
        self._entries: list[FakeStreamEntry] = list(entries or [])
        self._acked: list[str] = []
        self.group_ensured = False

    def ensure_group(self) -> None:
        self.group_ensured = True

    def add(self, message: RawMessage) -> str:
        entry_id = f"entry-{message.channel_id}-{message.message_id}"
        self._entries.append(FakeStreamEntry(entry_id, message))
        return entry_id

    def read(self, *, consumer_name: str, count: int) -> list[FakeStreamEntry]:
        batch = self._entries[:count]
        self._entries = self._entries[count:]
        return batch

    def ack(self, entry_ids) -> None:
        self._acked.extend(entry_ids)


def build_message(
    channel_id: int,
    message_id: int,
    *,
    minute: int = 0,
    text: str = "test message",
    english_text: str | None = None,
) -> RawMessage:
    timestamp = datetime(2026, 4, 9, 12, minute, 0, tzinfo=timezone.utc)
    return RawMessage(
        channel_id=channel_id,
        message_id=message_id,
        timestamp=timestamp,
        sender_id=None,
        sender_name=None,
        text=text,
        english_text=english_text,
    )


class KGProcessMessagesTests(unittest.TestCase):
    """Tests for KGNodeProcessingService.process_messages()."""

    def test_process_single_message_creates_node_assignment_and_semantic_record(self):
        """process_messages([msg]) with one theme candidate → 1 assignment, 1 node, semantic record saved."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        msg = build_message(100, 1, text="Ceasefire negotiations advance")
        repository.upsert_raw_messages([msg])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100,
                    message_id=1,
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                )
            }
        )

        result = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_messages([msg])

        self.assertEqual(result.assignments_created, 1)
        self.assertEqual(result.nodes_created, 1)
        self.assertIsNotNone(repository.get_message_semantic_record(channel_id=100, message_id=1))
        self.assertEqual(len(repository.message_nodes), 1)
        theme_node = repository.get_node_by_slug(kind="theme", slug="ceasefire-peace-negotiations", status=None)
        self.assertIsNotNone(theme_node)

    def test_process_two_messages_with_same_theme_creates_one_node_with_count_two(self):
        """Two messages from same channel extracting the same theme → 1 node article_count=2, 2 assignments."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        msg1 = build_message(100, 1, minute=0, text="Ceasefire update one")
        msg2 = build_message(100, 2, minute=1, text="Ceasefire update two")
        repository.upsert_raw_messages([msg1, msg2])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100, message_id=1,
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
                (100, 2): MessageSemanticExtraction(
                    channel_id=100, message_id=2,
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
            }
        )

        result = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_messages([msg1, msg2])

        self.assertEqual(result.assignments_created, 2)
        self.assertEqual(result.nodes_created, 1)
        theme = repository.get_node_by_slug(kind="theme", slug="ceasefire-peace-negotiations")
        self.assertIsNotNone(theme)
        self.assertEqual(theme.article_count, 2)
        self.assertEqual(len(repository.message_nodes), 2)

    def test_process_messages_is_idempotent(self):
        """Running process_messages again on the same messages doesn't create duplicate assignments."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        msg = build_message(100, 1, text="Ceasefire negotiations advance")
        repository.upsert_raw_messages([msg])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100, message_id=1,
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                )
            }
        )

        service = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        )
        result1 = service.process_messages([msg])
        result2 = service.process_messages([msg])  # same message again

        self.assertEqual(result1.assignments_created, 1)
        self.assertEqual(result2.assignments_created, 0)  # skipped — already has semantics
        self.assertEqual(len(repository.message_nodes), 1)

    def test_cross_channel_message_match_creates_match_record_and_promotes_node(self):
        """Two messages from different channels with same event and high embedding similarity
        → CrossChannelMessageMatch saved, cross-channel support registered."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        # Pre-seed msg2's embedding in the vector store so msg1's query finds it.
        msg1 = build_message(100, 1, minute=0, text="Hormuz closure event")
        msg2 = build_message(200, 2, minute=1, text="Hormuz closure event")
        repository.upsert_raw_messages([msg1, msg2])

        # Seed msg2's embedding so the cross-channel query can find it.
        vector_store.upsert_message_embeddings([
            MessageEmbeddingRecord(
                channel_id=200,
                message_id=2,
                embedding=[1.0, 0.0, 0.0],
                timestamp=msg2.timestamp,
            )
        ])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100, message_id=1,
                    events=(ExtractedSemanticNode(
                        name="April 8 Hormuz Reclosure",
                        start_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
                    ),),
                    primary_event="April 8 Hormuz Reclosure",
                ),
                (200, 2): MessageSemanticExtraction(
                    channel_id=200, message_id=2,
                    events=(ExtractedSemanticNode(
                        name="April 8 Hormuz Reclosure",
                        start_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
                    ),),
                    primary_event="April 8 Hormuz Reclosure",
                ),
            }
        )

        # Process msg1 first (msg2 embedding is already in store, so cross-channel query will find it).
        result = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_messages([msg1])

        self.assertGreater(result.cross_channel_matches, 0)
        self.assertGreater(len(repository.cross_channel_message_matches), 0)
        match = repository.cross_channel_message_matches[0]
        self.assertEqual(match.channel_id, 100)
        self.assertEqual(match.message_id, 1)
        self.assertEqual(match.matched_channel_id, 200)

    def test_process_messages_sets_primary_event_flag(self):
        """The primary_event from extraction gets is_primary_event=True on its assignment."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        msg = build_message(100, 1, text="Hormuz closure event and peace talks")
        repository.upsert_raw_messages([msg])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100, message_id=1,
                    events=(
                        ExtractedSemanticNode(name="April 8 Hormuz Reclosure", start_at=datetime(2026, 4, 8, tzinfo=timezone.utc)),
                        ExtractedSemanticNode(name="April 9 Peace Talks", start_at=datetime(2026, 4, 9, tzinfo=timezone.utc)),
                    ),
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                    primary_event="April 8 Hormuz Reclosure",
                )
            }
        )

        KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_messages([msg])

        assignments = list(repository.message_nodes.values())
        primary_events = [a for a in assignments if a.is_primary_event]
        self.assertEqual(len(primary_events), 1)
        primary_node = repository.nodes[primary_events[0].node_id]
        self.assertEqual(primary_node.kind, "event")

    def test_process_messages_calls_refresh_all_from_messages_not_refresh_all(self):
        """process_messages with per_batch projection_policy calls refresh_all_from_messages, not refresh_all."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        projection_service = FakeProjectionService()

        msg = build_message(100, 1, text="Ceasefire negotiations advance")
        repository.upsert_raw_messages([msg])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100,
                    message_id=1,
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                )
            }
        )

        service = KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
            projection_service=projection_service,
        )
        # Default options use projection_policy="per_batch", which should route to
        # refresh_all_from_messages rather than the legacy refresh_all.
        service.process_messages([msg])

        self.assertEqual(projection_service.refresh_all_from_messages_calls, 1,
                         "process_messages must call refresh_all_from_messages (not refresh_all)")
        self.assertEqual(projection_service.refresh_all_calls, 0,
                         "process_messages must NOT call the legacy refresh_all")


class KGProcessingWorkerTests(unittest.TestCase):
    """Tests for KGProcessingWorker.process_batch() and run_loop()."""

    def _make_worker(
        self,
        *,
        stream: FakeStream,
        repository: FakeRepository | None = None,
        vector_store: FakeVectorStore | None = None,
        embedder: FakeEmbedder | None = None,
        extractor: FakeExtractor | None = None,
        translator: FakeTranslator | None = None,
    ) -> KGProcessingWorker:
        repo = repository or FakeRepository()
        vs = vector_store or FakeVectorStore()
        emb = embedder or FakeEmbedder()
        ext = extractor or FakeExtractor()
        settings = build_settings()
        return KGProcessingWorker(
            repository=repo,
            stream=stream,
            embedder=emb,
            vector_store=vs,
            settings=settings,
            extractor=ext,
            translator=translator,
        )

    def test_process_batch_empty_stream_returns_zero_result(self):
        stream = FakeStream()
        worker = self._make_worker(stream=stream)
        result = worker.process_batch(consumer_name="w1", batch_size=10)
        self.assertIsInstance(result, KGProcessingResult)
        self.assertEqual(result.messages_processed, 0)
        self.assertEqual(result.messages_embedded, 0)

    def test_process_batch_full_pipeline_upserts_translates_embeds_processes_and_acks(self):
        """End-to-end: stream → upsert → translate → embed → process_messages → ack."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        msg = build_message(100, 1, text="Ceasefire negotiations advance", minute=0)
        stream = FakeStream([FakeStreamEntry("entry-100-1", msg)])

        extractor = FakeExtractor(
            message_payloads={
                (100, 1): MessageSemanticExtraction(
                    channel_id=100, message_id=1,
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                )
            }
        )
        translator = FakeTranslator({(100, 1): ("Ceasefire negotiations advance", "en")})

        worker = KGProcessingWorker(
            repository=repository,
            stream=stream,
            embedder=embedder,
            vector_store=vector_store,
            settings=settings,
            extractor=extractor,
            translator=translator,
        )
        result = worker.process_batch(consumer_name="w1", batch_size=10)

        # Message was upserted.
        self.assertIn((100, 1), repository.raw_messages)
        # Schema was ensured.
        self.assertTrue(repository.schema_ensured)
        # Stream entry was acked.
        self.assertIn("entry-100-1", stream._acked)
        # Results look correct.
        self.assertEqual(result.messages_processed, 1)
        self.assertGreaterEqual(result.messages_embedded, 1)
        self.assertEqual(result.assignments_created, 1)
        self.assertEqual(result.nodes_created, 1)
        # Semantic record was saved.
        self.assertIsNotNone(repository.get_message_semantic_record(channel_id=100, message_id=1))

    def test_process_batch_acks_entries_even_on_empty_extraction(self):
        """Even when extraction produces nothing, entries are still acked."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()

        msg = build_message(100, 5, text="Some message")
        stream = FakeStream([FakeStreamEntry("entry-100-5", msg)])
        extractor = FakeExtractor()  # returns empty extraction for every message

        worker = self._make_worker(
            stream=stream,
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
        )
        result = worker.process_batch(consumer_name="w1", batch_size=10)
        self.assertIn("entry-100-5", stream._acked)
        self.assertEqual(result.messages_processed, 1)

    def test_run_loop_stops_after_idle_cycles(self):
        """run_loop with stop_after_idle_cycles=1 processes all entries then stops."""
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()

        msg = build_message(100, 1, text="Test message")
        stream = FakeStream([FakeStreamEntry("entry-100-1", msg)])

        extractor = FakeExtractor()
        slept: list[float] = []

        worker = self._make_worker(
            stream=stream,
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
        )
        result = worker.run_loop(
            consumer_name="w1",
            batch_size=10,
            poll_interval_seconds=0.0,
            sleep_fn=slept.append,
            stop_after_idle_cycles=1,
        )
        self.assertEqual(result.messages_processed, 1)
        self.assertEqual(len(slept), 1)  # slept once on the idle cycle


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

    def test_theme_first_sight_stays_hidden_candidate(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        story = build_story("story-theme", channel_id=100, minute=0, combined_text="Ceasefire negotiations advance")
        repository.save_story_units([story])
        vector_store.upsert_story_embeddings([StoryEmbeddingRecord(story.story_id, [0.9, 0.1, 0.0], 100, story.timestamp_start)])

        extractor = FakeExtractor(
            {
                "story-theme": StorySemanticExtraction(
                    story_id="story-theme",
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                    people=(ExtractedSemanticNode(name="Donald Trump"),),
                )
            }
        )

        KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_stories([story])

        hidden = repository.get_node_by_slug(kind="theme", slug="ceasefire-peace-negotiations", status=None)
        assert hidden is not None
        self.assertEqual(hidden.status, "candidate")
        self.assertIsNone(repository.get_node_by_slug(kind="theme", slug="ceasefire-peace-negotiations"))
        self.assertEqual(KGQueryService(repository).list_nodes(kind="theme"), [])
        self.assertEqual(KGQueryService(repository).themes_now(), [])
        self.assertIsNone(KGQueryService(repository).node_show(kind="theme", slug="ceasefire-peace-negotiations"))

    def test_theme_promotes_after_second_supporting_story_without_changing_identity(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        story_a = build_story("story-a", channel_id=100, minute=0, combined_text="Ceasefire update one")
        story_b = build_story("story-b", channel_id=100, minute=1, combined_text="Ceasefire update two")
        repository.save_story_units([story_a, story_b])
        vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(story_a.story_id, [0.9, 0.1, 0.0], 100, story_a.timestamp_start),
                StoryEmbeddingRecord(story_b.story_id, [0.9, 0.1, 0.0], 100, story_b.timestamp_start),
            ]
        )

        extractor = FakeExtractor(
            {
                "story-a": StorySemanticExtraction(
                    story_id="story-a",
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
                "story-b": StorySemanticExtraction(
                    story_id="story-b",
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
            }
        )

        KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_stories([story_a, story_b])

        theme = repository.get_node_by_slug(kind="theme", slug="ceasefire-peace-negotiations")
        assert theme is not None
        self.assertEqual(theme.status, "active")
        self.assertEqual(theme.article_count, 2)
        assigned_theme_ids = {
            assignment.node_id
            for assignment in repository.story_nodes.values()
            if repository.nodes[assignment.node_id].kind == "theme"
        }
        self.assertEqual(assigned_theme_ids, {theme.node_id})
        self.assertEqual(
            [row.slug for row in KGQueryService(repository).list_nodes(kind="theme")],
            ["ceasefire-peace-negotiations"],
        )

    def test_cross_channel_match_promotes_hidden_theme_with_single_supporting_story(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        story_a = build_story("story-a", channel_id=100, minute=0, combined_text="Ceasefire negotiations advance")
        story_b = build_story("story-b", channel_id=200, minute=1, combined_text="Ceasefire negotiations advance")
        repository.save_story_units([story_a, story_b])
        vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(story_a.story_id, [0.9, 0.1, 0.0], 100, story_a.timestamp_start),
                StoryEmbeddingRecord(story_b.story_id, [0.9, 0.1, 0.0], 200, story_b.timestamp_start),
            ]
        )

        extractor = FakeExtractor(
            {
                "story-a": StorySemanticExtraction(
                    story_id="story-a",
                    themes=(ExtractedSemanticNode(name="Ceasefire Peace Negotiations"),),
                ),
                "story-b": StorySemanticExtraction(
                    story_id="story-b",
                    people=(ExtractedSemanticNode(name="Donald Trump"),),
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

        theme = repository.get_node_by_slug(kind="theme", slug="ceasefire-peace-negotiations")
        assert theme is not None
        self.assertEqual(theme.status, "active")
        self.assertEqual(theme.article_count, 1)
        self.assertGreater(result.cross_channel_matches, 0)

    def test_generic_strike_events_resolve_directly_to_actor_cluster(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        story_tel_aviv = build_story("story-tel-aviv", channel_id=100, minute=0, combined_text="Iranian strike on Tel Aviv")
        story_haifa = build_story("story-haifa", channel_id=100, minute=1, combined_text="Iranian strike on Haifa Port")
        repository.save_story_units([story_tel_aviv, story_haifa])
        vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(story_tel_aviv.story_id, [0.0, 1.0, 0.0], 100, story_tel_aviv.timestamp_start),
                StoryEmbeddingRecord(story_haifa.story_id, [0.0, 1.0, 0.0], 100, story_haifa.timestamp_start),
            ]
        )

        extractor = FakeExtractor(
            {
                "story-tel-aviv": StorySemanticExtraction(
                    story_id="story-tel-aviv",
                    events=(ExtractedSemanticNode(name="Iranian strike on Tel Aviv"),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    places=(ExtractedSemanticNode(name="Tel Aviv"),),
                    primary_event="Iranian strike on Tel Aviv",
                ),
                "story-haifa": StorySemanticExtraction(
                    story_id="story-haifa",
                    events=(ExtractedSemanticNode(name="Iranian strike on Haifa Port"),),
                    nations=(ExtractedSemanticNode(name="Iran"),),
                    places=(ExtractedSemanticNode(name="Haifa"),),
                    primary_event="Iranian strike on Haifa Port",
                ),
            }
        )

        KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_stories([story_tel_aviv, story_haifa])

        events = repository.list_nodes(kind="event", status=None)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].display_name, "Iranian strikes")
        self.assertEqual(events[0].status, "active")
        self.assertEqual(
            {
                assignment.node_id
                for assignment in repository.story_nodes.values()
                if repository.nodes[assignment.node_id].kind == "event"
            },
            {events[0].node_id},
        )

    def test_named_operation_events_activate_immediately_as_parent_style_nodes(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()
        story = build_story("story-operation", channel_id=100, minute=0, combined_text="Operation True Promise wave")
        repository.save_story_units([story])
        vector_store.upsert_story_embeddings([StoryEmbeddingRecord(story.story_id, [0.0, 1.0, 0.0], 100, story.timestamp_start)])

        extractor = FakeExtractor(
            {
                "story-operation": StorySemanticExtraction(
                    story_id="story-operation",
                    events=(ExtractedSemanticNode(name="16th wave of Operation True Promise 4 retaliatory strikes"),),
                    primary_event="16th wave of Operation True Promise 4 retaliatory strikes",
                )
            }
        )

        KGNodeProcessingService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=settings,
        ).process_stories([story])

        operation = repository.get_node_by_slug(kind="event", slug="operation-true-promise-4")
        assert operation is not None
        self.assertEqual(operation.status, "active")
        self.assertEqual(
            [node.display_name for node in repository.list_nodes(kind="event", status=None)],
            ["Operation True Promise 4"],
        )

    def test_node_processing_merges_person_middle_initial_variants(self):
        repository = FakeRepository()
        vector_store = FakeVectorStore()
        embedder = FakeEmbedder()
        settings = build_settings()

        story_a = build_story("story-a", channel_id=100, minute=0, combined_text="Trump speaks")
        story_b = build_story("story-b", channel_id=100, minute=1, combined_text="Trump responds")
        repository.save_story_units([story_a, story_b])
        vector_store.upsert_story_embeddings(
            [
                StoryEmbeddingRecord(story_a.story_id, [0.7, 0.2, 0.0], 100, story_a.timestamp_start),
                StoryEmbeddingRecord(story_b.story_id, [0.7, 0.2, 0.0], 100, story_b.timestamp_start),
            ]
        )

        extractor = FakeExtractor(
            {
                "story-a": StorySemanticExtraction(
                    story_id="story-a",
                    people=(ExtractedSemanticNode(name="Donald Trump"),),
                ),
                "story-b": StorySemanticExtraction(
                    story_id="story-b",
                    people=(
                        ExtractedSemanticNode(name="Donald J. Trump"),
                        ExtractedSemanticNode(name="Donald J Trump"),
                    ),
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

        self.assertEqual(result.nodes_created, 1)
        self.assertEqual(result.assignments_created, 2)
        people = [node for node in repository.nodes.values() if node.kind == "person"]
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0].display_name, "Donald Trump")
        self.assertIn("Donald J. Trump", people[0].aliases)
        assignment_node_ids = {
            assignment.node_id
            for assignment in repository.story_nodes.values()
            if repository.nodes[assignment.node_id].kind == "person"
        }
        self.assertEqual(assignment_node_ids, {people[0].node_id})

    def test_event_hierarchy_service_groups_named_operations_and_scoped_airstrike_families(self):
        repository = FakeRepository()

        _t = datetime(2026, 4, 1, tzinfo=timezone.utc)
        operation = Node(
            node_id="event-operation",
            kind="event",
            slug="operation-true-promise-4",
            display_name="Operation True Promise 4",
            canonical_name="Operation True Promise 4",
            normalized_name="operation true promise 4",
            article_count=1,
            created_at=_t,
            last_updated=_t,
        )
        wave = Node(
            node_id="event-wave",
            kind="event",
            slug="16th-wave-operation-true-promise-4",
            display_name="16th wave of Operation True Promise 4 retaliatory strikes",
            canonical_name="16th wave of Operation True Promise 4 retaliatory strikes",
            normalized_name="16th wave of operation true promise 4 retaliatory strikes",
            article_count=1,
            created_at=_t,
            last_updated=_t,
        )
        air_one = Node(
            node_id="event-air-one",
            kind="event",
            slug="israeli-airstrike-on-southern-suburb-of-beirut",
            display_name="Israeli airstrike on southern suburb of Beirut",
            canonical_name="Israeli airstrike on southern suburb of Beirut",
            normalized_name="israeli airstrike on southern suburb of beirut",
            article_count=1,
            created_at=_t,
            last_updated=_t,
        )
        air_two = Node(
            node_id="event-air-two",
            kind="event",
            slug="israeli-airstrike-on-residential-building-in-southern-lebanon",
            display_name="Israeli airstrike on residential building in southern Lebanon",
            canonical_name="Israeli airstrike on residential building in southern Lebanon",
            normalized_name="israeli airstrike on residential building in southern lebanon",
            article_count=1,
            created_at=_t,
            last_updated=_t,
        )
        israel = Node(
            node_id="nation-israel",
            kind="nation",
            slug="israel",
            display_name="Israel",
            canonical_name="Israel",
            normalized_name="israel",
            article_count=2,
        )
        south_lebanon = Node(
            node_id="place-south-lebanon",
            kind="place",
            slug="southern-lebanon",
            display_name="Southern Lebanon",
            canonical_name="Southern Lebanon",
            normalized_name="southern lebanon",
            article_count=2,
        )
        repository.save_nodes([operation, wave, air_one, air_two, israel, south_lebanon])
        # Use message-based assignments (message-atomic pipeline).
        # msg_1 → operation; msg_2 → wave; msg_3 → air_one + israel + south_lebanon;
        # msg_4 → air_two + israel + south_lebanon.
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=operation.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=wave.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=3, node_id=air_one.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=4, node_id=air_two.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=3, node_id=israel.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=4, node_id=israel.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=3, node_id=south_lebanon.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=4, node_id=south_lebanon.node_id, confidence=0.8),
        ])

        result = KGEventHierarchyService(repository).rebuild()

        self.assertEqual(result.parents_created, 1)
        self.assertEqual(repository.nodes[wave.node_id].parent_node_id, operation.node_id)
        synthetic_parents = [node for node in repository.nodes.values() if node.label_source == "hierarchy_group"]
        self.assertEqual(len(synthetic_parents), 1)
        self.assertEqual(synthetic_parents[0].display_name, "Israeli airstrikes")
        self.assertEqual(repository.nodes[air_one.node_id].parent_node_id, synthetic_parents[0].node_id)
        self.assertEqual(repository.nodes[air_two.node_id].parent_node_id, synthetic_parents[0].node_id)

    def test_event_hierarchy_prefers_label_scope_over_noisy_story_entities(self):
        repository = FakeRepository()

        _t = datetime(2026, 4, 1, tzinfo=timezone.utc)
        air_one = Node(
            node_id="event-air-one",
            kind="event",
            slug="israeli-airstrike-on-residential-building-in-southern-lebanon",
            display_name="Israeli airstrike on residential building in southern Lebanon",
            canonical_name="Israeli airstrike on residential building in southern Lebanon",
            normalized_name="israeli airstrike on residential building in southern lebanon",
            article_count=1,
            created_at=_t,
            last_updated=_t,
        )
        air_two = Node(
            node_id="event-air-two",
            kind="event",
            slug="israeli-airstrike-on-town-square-in-southern-lebanon",
            display_name="Israeli airstrike on town square in southern Lebanon",
            canonical_name="Israeli airstrike on town square in southern Lebanon",
            normalized_name="israeli airstrike on town square in southern lebanon",
            article_count=1,
            created_at=_t,
            last_updated=_t,
        )
        noisy_person = Node(
            node_id="person-noisy",
            kind="person",
            slug="johnny-james-miller",
            display_name="Johnny James Miller",
            canonical_name="Johnny James Miller",
            normalized_name="johnny james miller",
            article_count=2,
        )
        noisy_org = Node(
            node_id="org-noisy",
            kind="org",
            slug="irna",
            display_name="IRNA",
            canonical_name="IRNA",
            normalized_name="irna",
            article_count=2,
        )
        noisy_place = Node(
            node_id="place-noisy",
            kind="place",
            slug="tehran",
            display_name="Tehran",
            canonical_name="Tehran",
            normalized_name="tehran",
            article_count=2,
        )
        repository.save_nodes([air_one, air_two, noisy_person, noisy_org, noisy_place])
        # msg_1 → air_one + noisy entities; msg_2 → air_two + noisy entities.
        # The test verifies that label-derived actor ("Israeli") wins over noisy co-occurrences.
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=air_one.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=air_two.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=noisy_person.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=noisy_person.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=noisy_org.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=noisy_org.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=noisy_place.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=noisy_place.node_id, confidence=0.8),
        ])

        result = KGEventHierarchyService(repository).rebuild()

        self.assertEqual(result.parents_created, 1)
        synthetic_parents = [node for node in repository.nodes.values() if node.label_source == "hierarchy_group"]
        self.assertEqual(len(synthetic_parents), 1)
        self.assertEqual(synthetic_parents[0].display_name, "Israeli airstrikes")
        self.assertEqual(repository.nodes[air_one.node_id].parent_node_id, synthetic_parents[0].node_id)
        self.assertEqual(repository.nodes[air_two.node_id].parent_node_id, synthetic_parents[0].node_id)

    def test_event_hierarchy_replaces_location_scoped_strike_parents_with_actor_parent(self):
        repository = FakeRepository()

        _t = datetime(2026, 4, 1, tzinfo=timezone.utc)
        old_tel_aviv_parent = Node(
            node_id="event-old-parent-tel-aviv",
            kind="event",
            slug="iranian-strikes-in-tel-aviv",
            display_name="Iranian strikes in Tel Aviv",
            canonical_name="Iranian strikes in Tel Aviv",
            normalized_name="iranian strikes in tel aviv",
            article_count=1,
            label_source="hierarchy_group",
            created_at=_t,
            last_updated=_t,
        )
        old_haifa_parent = Node(
            node_id="event-old-parent-haifa",
            kind="event",
            slug="iranian-strikes-in-haifa",
            display_name="Iranian strikes in Haifa",
            canonical_name="Iranian strikes in Haifa",
            normalized_name="iranian strikes in haifa",
            article_count=1,
            label_source="hierarchy_group",
            created_at=_t,
            last_updated=_t,
        )
        tel_aviv_strike = Node(
            node_id="event-tel-aviv",
            kind="event",
            slug="iranian-strike-on-tel-aviv",
            display_name="Iranian strike on Tel Aviv",
            canonical_name="Iranian strike on Tel Aviv",
            normalized_name="iranian strike on tel aviv",
            article_count=1,
            created_at=_t,
            last_updated=_t,
            parent_node_id=old_tel_aviv_parent.node_id,
        )
        haifa_strike = Node(
            node_id="event-haifa",
            kind="event",
            slug="iranian-strike-on-haifa-port",
            display_name="Iranian strike on Haifa Port",
            canonical_name="Iranian strike on Haifa Port",
            normalized_name="iranian strike on haifa port",
            article_count=1,
            created_at=_t,
            last_updated=_t,
            parent_node_id=old_haifa_parent.node_id,
        )
        iran = Node(
            node_id="nation-iran",
            kind="nation",
            slug="iran",
            display_name="Iran",
            canonical_name="Iran",
            normalized_name="iran",
            article_count=2,
        )
        tel_aviv = Node(
            node_id="place-tel-aviv",
            kind="place",
            slug="tel-aviv",
            display_name="Tel Aviv",
            canonical_name="Tel Aviv",
            normalized_name="tel aviv",
            article_count=1,
        )
        haifa = Node(
            node_id="place-haifa",
            kind="place",
            slug="haifa",
            display_name="Haifa",
            canonical_name="Haifa",
            normalized_name="haifa",
            article_count=1,
        )
        repository.save_nodes([old_tel_aviv_parent, old_haifa_parent, tel_aviv_strike, haifa_strike, iran, tel_aviv, haifa])
        # msg_1 → tel_aviv_strike + iran + tel_aviv; msg_2 → haifa_strike + iran + haifa.
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=tel_aviv_strike.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=haifa_strike.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=iran.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=iran.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=tel_aviv.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=haifa.node_id, confidence=0.8),
        ])

        result = KGEventHierarchyService(repository).rebuild()

        self.assertEqual(result.parents_deleted, 2)
        self.assertNotIn(old_tel_aviv_parent.node_id, repository.nodes)
        self.assertNotIn(old_haifa_parent.node_id, repository.nodes)
        synthetic_parents = [node for node in repository.nodes.values() if node.label_source == "hierarchy_group"]
        self.assertEqual(len(synthetic_parents), 1)
        self.assertEqual(synthetic_parents[0].display_name, "Iranian strikes")
        self.assertEqual(repository.nodes[tel_aviv_strike.node_id].parent_node_id, synthetic_parents[0].node_id)
        self.assertEqual(repository.nodes[haifa_strike.node_id].parent_node_id, synthetic_parents[0].node_id)

    def test_query_service_rolls_parent_events_and_exposes_child_parent_links(self):
        repository = FakeRepository()
        parent_story = build_story("story-parent", channel_id=100, minute=0, combined_text="Operation overview")
        child_story = build_story("story-child", channel_id=100, minute=1, combined_text="Wave action")
        theme_story = build_story("story-theme", channel_id=100, minute=2, combined_text="Wave action theme")
        repository.save_story_units([parent_story, child_story, theme_story])

        parent = Node(
            node_id="event-parent",
            kind="event",
            slug="operation-roaring-lion",
            display_name="Operation Roaring Lion",
            canonical_name="Operation Roaring Lion",
            normalized_name="operation roaring lion",
            article_count=1,
            created_at=parent_story.timestamp_start,
            last_updated=parent_story.timestamp_end,
        )
        child = Node(
            node_id="event-child",
            kind="event",
            slug="day-2-of-operation-roaring-lion",
            display_name="Day 2 of Operation Roaring Lion",
            canonical_name="Day 2 of Operation Roaring Lion",
            normalized_name="day 2 of operation roaring lion",
            article_count=2,
            created_at=child_story.timestamp_start,
            last_updated=theme_story.timestamp_end,
            event_start_at=child_story.timestamp_start,
        )
        theme = Node(
            node_id="theme-1",
            kind="theme",
            slug="regional-escalation",
            display_name="Regional Escalation",
            canonical_name="Regional Escalation",
            normalized_name="regional escalation",
            article_count=1,
            last_updated=theme_story.timestamp_end,
        )
        org = Node(
            node_id="org-1",
            kind="org",
            slug="idf",
            display_name="IDF",
            canonical_name="IDF",
            normalized_name="idf",
            article_count=2,
            last_updated=theme_story.timestamp_end,
        )
        place = Node(
            node_id="place-1",
            kind="place",
            slug="northern-strip",
            display_name="Northern Strip",
            canonical_name="Northern Strip",
            normalized_name="northern strip",
            article_count=2,
            last_updated=theme_story.timestamp_end,
        )
        repository.save_nodes([parent, child, theme, org, place])
        # Keep story assignments for the legacy node_show() path (stories display + relations).
        repository.save_story_node_assignments(
            [
                StoryNodeAssignment(parent_story.story_id, parent.node_id, 1.0, is_primary_event=True),
                StoryNodeAssignment(child_story.story_id, child.node_id, 1.0, is_primary_event=True),
                StoryNodeAssignment(theme_story.story_id, child.node_id, 1.0, is_primary_event=True),
                StoryNodeAssignment(theme_story.story_id, theme.node_id, 0.7),
                StoryNodeAssignment(child_story.story_id, org.node_id, 0.8),
                StoryNodeAssignment(theme_story.story_id, org.node_id, 0.8),
                StoryNodeAssignment(child_story.story_id, place.node_id, 0.8),
                StoryNodeAssignment(theme_story.story_id, place.node_id, 0.8),
            ]
        )
        # Message assignments drive hierarchy rebuild() and article_count in snapshot.
        # msg_1 → parent event; msg_2, msg_3 → child event (giving child 2 keys, parent rollup = 3).
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id=parent.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=child.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=3, node_id=child.node_id, confidence=1.0, is_primary_event=True),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=org.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=3, node_id=org.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id=place.node_id, confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=3, node_id=place.node_id, confidence=0.8),
        ])

        KGEventHierarchyService(repository).rebuild()
        service = KGQueryService(repository)

        event_rows = service.list_nodes(kind="event")
        self.assertEqual([row.slug for row in event_rows], ["operation-roaring-lion"])
        # Rollup from snapshot: parent has 1 direct msg + 2 child msgs = 3.
        self.assertEqual(event_rows[0].article_count, 3)
        self.assertEqual(event_rows[0].child_count, 1)

        parent_detail = service.node_show(kind="event", slug="operation-roaring-lion")
        assert parent_detail is not None
        # article_count from message-based snapshot rollup.
        self.assertEqual(parent_detail.article_count, 3)
        self.assertEqual([child_ref.slug for child_ref in parent_detail.child_events], ["day-2-of-operation-roaring-lion"])
        self.assertEqual(parent_detail.child_events[0].primary_location, "Northern Strip")
        self.assertEqual(parent_detail.child_events[0].location_labels, ("Northern Strip",))
        self.assertEqual(parent_detail.child_events[0].organization_labels, ("IDF",))
        self.assertEqual(parent_detail.child_events[0].event_start_at, child.event_start_at)
        # Story display still works via legacy story assignments.
        self.assertEqual(len(parent_detail.stories), 3)
        self.assertEqual([related.slug for related in parent_detail.themes], ["regional-escalation"])

        child_detail = service.node_show(kind="event", slug="day-2-of-operation-roaring-lion")
        assert child_detail is not None
        self.assertEqual(child_detail.parent_event.slug, "operation-roaring-lion")
        # article_count from message-based snapshot: child has 2 direct message keys.
        self.assertEqual(child_detail.article_count, 2)
        self.assertEqual(len(child_detail.stories), 2)

        relations = service.snapshot_relations(nodes=event_rows + service.list_nodes(kind="theme"))
        self.assertEqual(len(relations), 1)
        self.assertEqual({relations[0].source_node_id, relations[0].target_node_id}, {parent.node_id, theme.node_id})
        self.assertEqual(relations[0].shared_story_count, 1)

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


class RebuildNodeRelationsFromMessagesTests(unittest.TestCase):
    """Tests for KGNodeProjectionService.rebuild_node_relations_from_messages()."""

    def _make_node(self, node_id: str, kind: str = "theme") -> "Node":
        from telegram_scraper.kg.models import Node
        return Node(
            node_id=node_id,
            kind=kind,
            slug=node_id,
            display_name=node_id,
            canonical_name=node_id,
            normalized_name=node_id,
            summary=None,
            aliases=(),
            status="active",
            label_source="test",
            article_count=0,
        )

    def test_two_messages_with_two_shared_nodes_produces_one_relation(self):
        """Two messages each mentioning node_a and node_b → 1 relation with shared_count=2."""
        from telegram_scraper.kg.services import KGNodeProjectionService

        repository = FakeRepository()
        vector_store = FakeVectorStore()

        node_a = self._make_node("node-a")
        node_b = self._make_node("node-b")
        repository.save_nodes([node_a, node_b])

        msg1 = build_message(100, 1, minute=0, text="msg1")
        msg2 = build_message(100, 2, minute=1, text="msg2")
        repository.upsert_raw_messages([msg1, msg2])

        # Both messages mention both nodes.
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="node-a", confidence=0.9),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="node-b", confidence=0.8),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id="node-a", confidence=0.85),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id="node-b", confidence=0.75),
        ])

        service = KGNodeProjectionService(repository=repository, vector_store=vector_store)
        count = service.rebuild_node_relations_from_messages()

        self.assertEqual(count, 1)
        relations = repository.list_node_relations("node-a")
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0].shared_story_count, 2)
        self.assertEqual(relations[0].score, 2.0)

    def test_cross_channel_bonus_adds_half_point(self):
        """A cross-channel match between two event nodes adds 0.5 bonus to their relation."""
        from telegram_scraper.kg.services import KGNodeProjectionService
        from telegram_scraper.kg.models import CrossChannelMessageMatch, MessageSemanticRecord

        repository = FakeRepository()
        vector_store = FakeVectorStore()

        node_a = self._make_node("event-a", kind="event")
        node_b = self._make_node("event-b", kind="event")
        repository.save_nodes([node_a, node_b])

        msg1 = build_message(100, 1, minute=0, text="event a msg")
        msg2 = build_message(200, 1, minute=0, text="event b msg")
        repository.upsert_raw_messages([msg1, msg2])

        # Each message mentions one event (no shared message, so no shared_count).
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="event-a", confidence=0.9, is_primary_event=True),
            MessageNodeAssignment(channel_id=200, message_id=1, node_id="event-b", confidence=0.9, is_primary_event=True),
        ])

        # Cross-channel message match.
        repository.save_cross_channel_message_matches([
            CrossChannelMessageMatch(
                channel_id=100, message_id=1,
                matched_channel_id=200, matched_message_id=1,
                similarity_score=0.95,
            )
        ])
        repository.upsert_message_semantics([
            MessageSemanticRecord(channel_id=100, message_id=1, primary_event_node_id="event-a"),
            MessageSemanticRecord(channel_id=200, message_id=1, primary_event_node_id="event-b"),
        ])

        service = KGNodeProjectionService(repository=repository, vector_store=vector_store)
        count = service.rebuild_node_relations_from_messages()

        self.assertEqual(count, 1)
        relations = repository.list_node_relations("event-a")
        self.assertEqual(len(relations), 1)
        self.assertAlmostEqual(relations[0].score, 0.5)
        self.assertEqual(relations[0].shared_story_count, 0)

    def test_no_assignments_produces_no_relations(self):
        from telegram_scraper.kg.services import KGNodeProjectionService

        repository = FakeRepository()
        vector_store = FakeVectorStore()
        service = KGNodeProjectionService(repository=repository, vector_store=vector_store)
        count = service.rebuild_node_relations_from_messages()
        self.assertEqual(count, 0)


class RefreshThemeStatsFromMessagesTests(unittest.TestCase):
    """Tests for KGNodeProjectionService.refresh_theme_stats_from_messages()."""

    def test_smoke_writes_theme_daily_stats(self):
        """Smoke test: theme with 2 messages on today's date → stat written with article_count=2."""
        from telegram_scraper.kg.services import KGNodeProjectionService
        from telegram_scraper.kg.models import Node, MessageEmbeddingRecord

        repository = FakeRepository()
        vector_store = FakeVectorStore()

        theme = Node(
            node_id="theme-x",
            kind="theme",
            slug="theme-x",
            display_name="Theme X",
            canonical_name="Theme X",
            normalized_name="theme x",
            summary=None,
            aliases=(),
            status="active",
            label_source="test",
            article_count=2,
        )
        repository.save_nodes([theme])

        today = datetime.now(timezone.utc).date()
        ts_today = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

        msg1 = RawMessage(channel_id=100, message_id=1, timestamp=ts_today, sender_id=None, sender_name=None, text="t1")
        msg2 = RawMessage(channel_id=100, message_id=2, timestamp=ts_today, sender_id=None, sender_name=None, text="t2")
        repository.upsert_raw_messages([msg1, msg2])
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="theme-x", confidence=0.9),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id="theme-x", confidence=0.8),
        ])
        vector_store.upsert_message_embeddings([
            MessageEmbeddingRecord(channel_id=100, message_id=1, embedding=[1.0, 0.0], timestamp=ts_today),
            MessageEmbeddingRecord(channel_id=100, message_id=2, embedding=[0.9, 0.1], timestamp=ts_today),
        ])

        service = KGNodeProjectionService(repository=repository, vector_store=vector_store)
        count = service.refresh_theme_stats_from_messages(days=1)

        self.assertGreater(count, 0)
        stat = repository.theme_daily_stats.get(("theme-x", today))
        self.assertIsNotNone(stat)
        self.assertEqual(stat.article_count, 2)


class NodeShowMessagesTests(unittest.TestCase):
    """Tests for KGQueryService.node_show_messages()."""

    def _make_node(self, node_id: str, kind: str = "theme") -> "Node":
        from telegram_scraper.kg.models import Node
        return Node(
            node_id=node_id,
            kind=kind,
            slug=node_id,
            display_name=node_id,
            canonical_name=node_id,
            normalized_name=node_id,
            summary=None,
            aliases=(),
            status="active",
            label_source="test",
            article_count=0,
        )

    def test_returns_messages_not_stories(self):
        """node_show_messages returns NodeDetail with messages populated, stories empty."""
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        theme = self._make_node("theme-t1")
        repository.save_nodes([theme])

        msg = RawMessage(
            channel_id=100, message_id=1,
            timestamp=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            sender_id=None, sender_name=None, text="Theme message content",
            english_text="Theme message content",
        )
        repository.upsert_raw_messages([msg])
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="theme-t1", confidence=0.9),
        ])

        service = KGQueryService(repository=repository)
        detail = service.node_show_messages(kind="theme", slug="theme-t1")

        self.assertIsNotNone(detail)
        self.assertEqual(detail.node_id, "theme-t1")
        self.assertEqual(len(detail.messages), 1)
        self.assertEqual(len(detail.stories), 0)
        self.assertEqual(detail.messages[0].message_id, 1)
        self.assertEqual(detail.messages[0].channel_id, 100)
        self.assertEqual(detail.messages[0].confidence, 0.9)

    def test_returns_none_for_missing_node(self):
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        service = KGQueryService(repository=repository)
        detail = service.node_show_messages(kind="theme", slug="nonexistent")
        self.assertIsNone(detail)

    def test_pagination_via_offset(self):
        """Pagination: message_limit=1 and message_offset=1 returns second message."""
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        theme = self._make_node("theme-pag")
        repository.save_nodes([theme])

        ts_base = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
        for i in range(1, 4):
            msg = RawMessage(
                channel_id=100, message_id=i,
                timestamp=ts_base + timedelta(minutes=i),
                sender_id=None, sender_name=None, text=f"msg {i}",
            )
            repository.upsert_raw_messages([msg])
            repository.save_message_node_assignments([
                MessageNodeAssignment(
                    channel_id=100, message_id=i, node_id="theme-pag",
                    confidence=0.9,
                    assigned_at=ts_base + timedelta(minutes=i),
                ),
            ])

        service = KGQueryService(repository=repository)

        # Page 1: most recent first.
        detail_p1 = service.node_show_messages(kind="theme", slug="theme-pag", message_limit=1, message_offset=0)
        # Page 2: offset by 1.
        detail_p2 = service.node_show_messages(kind="theme", slug="theme-pag", message_limit=1, message_offset=1)

        self.assertEqual(len(detail_p1.messages), 1)
        self.assertEqual(len(detail_p2.messages), 1)
        # The two pages should return different messages.
        self.assertNotEqual(detail_p1.messages[0].message_id, detail_p2.messages[0].message_id)

    def test_related_entities_via_co_occurrence(self):
        """Related nodes are computed from message co-occurrence, not story relations."""
        from telegram_scraper.kg.services import KGQueryService
        from telegram_scraper.kg.models import Node

        repository = FakeRepository()
        theme = self._make_node("theme-main")
        person = Node(
            node_id="person-related",
            kind="person",
            slug="person-related",
            display_name="Related Person",
            canonical_name="Related Person",
            normalized_name="related person",
            summary=None,
            aliases=(),
            status="active",
            label_source="test",
            article_count=1,
        )
        repository.save_nodes([theme, person])

        msg = RawMessage(
            channel_id=100, message_id=1,
            timestamp=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            sender_id=None, sender_name=None, text="Joint message",
        )
        repository.upsert_raw_messages([msg])
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="theme-main", confidence=0.9),
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="person-related", confidence=0.8),
        ])

        service = KGQueryService(repository=repository)
        detail = service.node_show_messages(kind="theme", slug="theme-main")

        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.people), 1)
        self.assertEqual(detail.people[0].node_id, "person-related")
        self.assertEqual(detail.people[0].shared_story_count, 1)


class GroupedMessagesTests(unittest.TestCase):
    """Tests for KGQueryService.grouped_messages()."""

    def _make_node(self, node_id: str, kind: str = "event") -> "Node":
        from telegram_scraper.kg.models import Node
        return Node(
            node_id=node_id,
            kind=kind,
            slug=node_id,
            display_name=node_id,
            canonical_name=node_id,
            normalized_name=node_id,
            summary=None,
            aliases=(),
            status="active",
            label_source="test",
            article_count=0,
        )

    def test_three_messages_on_three_different_days_produce_three_groups(self):
        """Messages on 3 different days with window='1d' → 3 groups."""
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        node = self._make_node("event-e1")
        repository.save_nodes([node])

        base = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(3):
            ts = base + timedelta(days=i)
            msg = RawMessage(
                channel_id=100, message_id=i + 1,
                timestamp=ts, sender_id=None, sender_name=None, text=f"day {i+1}",
            )
            repository.upsert_raw_messages([msg])
            repository.save_message_node_assignments([
                MessageNodeAssignment(channel_id=100, message_id=i + 1, node_id="event-e1", confidence=0.9),
            ])

        service = KGQueryService(repository=repository)
        groups = service.grouped_messages(node_id="event-e1", window="1d")

        self.assertEqual(len(groups), 3)
        # Groups are sorted by timestamp_start DESC.
        self.assertGreater(groups[0].timestamp_start, groups[1].timestamp_start)
        self.assertGreater(groups[1].timestamp_start, groups[2].timestamp_start)
        for group in groups:
            self.assertEqual(len(group.messages), 1)
            self.assertEqual(group.dominant_node_id, "event-e1")

    def test_two_messages_within_same_day_produce_one_group(self):
        """Two messages in the same day → 1 group."""
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        node = self._make_node("event-e2")
        repository.save_nodes([node])

        base = datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc)
        for i in range(2):
            ts = base + timedelta(hours=i * 4)  # 4 hours apart, same day.
            msg = RawMessage(
                channel_id=100, message_id=i + 1,
                timestamp=ts, sender_id=None, sender_name=None, text=f"msg {i+1}",
            )
            repository.upsert_raw_messages([msg])
            repository.save_message_node_assignments([
                MessageNodeAssignment(channel_id=100, message_id=i + 1, node_id="event-e2", confidence=0.9),
            ])

        service = KGQueryService(repository=repository)
        groups = service.grouped_messages(node_id="event-e2", window="1d")

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].messages), 2)

    def test_empty_node_returns_empty_list(self):
        """Node with no message assignments → empty list."""
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        service = KGQueryService(repository=repository)
        groups = service.grouped_messages(node_id="nonexistent-node", window="1d")
        self.assertEqual(groups, [])

    def test_group_id_is_deterministic(self):
        """Calling grouped_messages twice returns groups with the same group_ids."""
        from telegram_scraper.kg.services import KGQueryService

        repository = FakeRepository()
        node = self._make_node("event-e3")
        repository.save_nodes([node])

        ts = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        msg = RawMessage(
            channel_id=100, message_id=1,
            timestamp=ts, sender_id=None, sender_name=None, text="once",
        )
        repository.upsert_raw_messages([msg])
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="event-e3", confidence=0.9),
        ])

        service = KGQueryService(repository=repository)
        groups1 = service.grouped_messages(node_id="event-e3", window="1d")
        groups2 = service.grouped_messages(node_id="event-e3", window="1d")

        self.assertEqual(len(groups1), 1)
        self.assertEqual(groups1[0].group_id, groups2[0].group_id)
        self.assertEqual(len(groups1[0].group_id), 16)  # sha256[:16]


class FakeRepositoryNewMethodTests(unittest.TestCase):
    """Tests for the three new FakeRepository helper methods."""

    def test_list_message_keys_for_node_on_date(self):
        repository = FakeRepository()
        ts_today = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
        ts_yesterday = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)

        msg_today = RawMessage(channel_id=100, message_id=1, timestamp=ts_today, sender_id=None, sender_name=None, text="t")
        msg_yesterday = RawMessage(channel_id=100, message_id=2, timestamp=ts_yesterday, sender_id=None, sender_name=None, text="y")
        repository.upsert_raw_messages([msg_today, msg_yesterday])
        repository.save_message_node_assignments([
            MessageNodeAssignment(channel_id=100, message_id=1, node_id="node-x", confidence=0.9),
            MessageNodeAssignment(channel_id=100, message_id=2, node_id="node-x", confidence=0.8),
        ])

        keys_today = repository.list_message_keys_for_node_on_date("node-x", ts_today.date())
        keys_yesterday = repository.list_message_keys_for_node_on_date("node-x", ts_yesterday.date())

        self.assertIn((100, 1), keys_today)
        self.assertNotIn((100, 2), keys_today)
        self.assertIn((100, 2), keys_yesterday)
        self.assertNotIn((100, 1), keys_yesterday)

    def test_get_raw_message(self):
        repository = FakeRepository()
        ts = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
        msg = RawMessage(channel_id=100, message_id=42, timestamp=ts, sender_id=None, sender_name=None, text="hello")
        repository.upsert_raw_messages([msg])

        found = repository.get_raw_message(channel_id=100, message_id=42)
        missing = repository.get_raw_message(channel_id=100, message_id=999)

        self.assertIsNotNone(found)
        self.assertEqual(found.message_id, 42)
        self.assertIsNone(missing)

    def test_list_raw_messages_by_keys(self):
        repository = FakeRepository()
        ts = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
        msg1 = RawMessage(channel_id=100, message_id=1, timestamp=ts, sender_id=None, sender_name=None, text="a")
        msg2 = RawMessage(channel_id=100, message_id=2, timestamp=ts + timedelta(seconds=1), sender_id=None, sender_name=None, text="b")
        repository.upsert_raw_messages([msg1, msg2])

        # Fetch both.
        results = repository.list_raw_messages_by_keys([(100, 1), (100, 2)])
        self.assertEqual(len(results), 2)

        # Fetch only one.
        results_one = repository.list_raw_messages_by_keys([(100, 1)])
        self.assertEqual(len(results_one), 1)
        self.assertEqual(results_one[0].message_id, 1)

        # Empty input → empty output.
        results_empty = repository.list_raw_messages_by_keys([])
        self.assertEqual(results_empty, [])

        # Missing key → silently omitted.
        results_missing = repository.list_raw_messages_by_keys([(100, 999)])
        self.assertEqual(results_missing, [])


if __name__ == "__main__":
    unittest.main()
