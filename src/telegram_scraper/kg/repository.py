from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
from typing import Any, Callable, Sequence

from telegram_scraper.kg.models import (
    ChannelProfile,
    ChannelSummary,
    CrossChannelMatch,
    DelimiterPattern,
    MediaRef,
    Node,
    NodeDetail,
    NodeKind,
    NodeListEntry,
    NodeRelation,
    NodeStory,
    RawMessage,
    RelatedNode,
    StoryNodeAssignment,
    StorySemanticRecord,
    StoryUnit,
    ThemeDailyStat,
    ThemeHeatSnapshot,
    ThemeHistoryPoint,
)
from telegram_scraper.utils import ensure_utc


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS channel_profiles (
        channel_id BIGINT PRIMARY KEY,
        delimiter_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
        media_group_window_seconds INT NOT NULL DEFAULT 60,
        time_gap_minutes INT NOT NULL DEFAULT 10,
        similarity_merge_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.7,
        lookback_story_count INT NOT NULL DEFAULT 5,
        notes TEXT,
        channel_title TEXT,
        channel_slug TEXT,
        channel_username TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS channel_title TEXT",
    "ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS channel_slug TEXT",
    "ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS channel_username TEXT",
    """
    CREATE TABLE IF NOT EXISTS raw_messages (
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        sender_id BIGINT,
        sender_name TEXT,
        text TEXT,
        english_text TEXT,
        source_language TEXT,
        translated_at TIMESTAMPTZ,
        media_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        forwarded_from BIGINT,
        reply_to_message_id BIGINT,
        raw_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (channel_id, message_id)
    )
    """,
    "ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS english_text TEXT",
    "ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS source_language TEXT",
    "ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS translated_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_raw_messages_channel_timestamp ON raw_messages (channel_id, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_raw_messages_channel_message ON raw_messages (channel_id, message_id)",
    """
    CREATE TABLE IF NOT EXISTS story_units (
        story_id UUID PRIMARY KEY,
        channel_id BIGINT NOT NULL,
        timestamp_start TIMESTAMPTZ NOT NULL,
        timestamp_end TIMESTAMPTZ NOT NULL,
        message_ids BIGINT[] NOT NULL,
        combined_text TEXT NOT NULL DEFAULT '',
        english_combined_text TEXT,
        translation_updated_at TIMESTAMPTZ,
        media_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE story_units ADD COLUMN IF NOT EXISTS english_combined_text TEXT",
    "ALTER TABLE story_units ADD COLUMN IF NOT EXISTS translation_updated_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_story_units_channel_timestamp_start ON story_units (channel_id, timestamp_start)",
    "CREATE INDEX IF NOT EXISTS idx_story_units_timestamp_start ON story_units (timestamp_start)",
    """
    CREATE TABLE IF NOT EXISTS story_messages (
        story_id UUID NOT NULL REFERENCES story_units(story_id) ON DELETE CASCADE,
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        position INT NOT NULL,
        PRIMARY KEY (story_id, message_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_story_messages_channel_message ON story_messages (channel_id, message_id)",
    "CREATE INDEX IF NOT EXISTS idx_story_messages_story_position ON story_messages (story_id, position)",
    """
    CREATE TABLE IF NOT EXISTS nodes (
        node_id UUID PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('person', 'nation', 'org', 'place', 'event', 'theme')),
        slug TEXT NOT NULL,
        display_name TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        summary TEXT,
        aliases TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
        status TEXT NOT NULL DEFAULT 'active',
        label_source TEXT NOT NULL DEFAULT 'semantic_extract',
        article_count INT NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        event_start_at TIMESTAMPTZ,
        event_end_at TIMESTAMPTZ,
        UNIQUE (kind, slug)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind_status ON nodes (kind, status)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind_normalized_name ON nodes (kind, normalized_name)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind_canonical_name ON nodes (kind, canonical_name)",
    """
    CREATE TABLE IF NOT EXISTS story_semantics (
        story_id UUID PRIMARY KEY REFERENCES story_units(story_id) ON DELETE CASCADE,
        extraction_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        primary_event_node_id UUID REFERENCES nodes(node_id),
        processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS story_nodes (
        story_id UUID NOT NULL REFERENCES story_units(story_id) ON DELETE CASCADE,
        node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        confidence DOUBLE PRECISION NOT NULL,
        assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_primary_event BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (story_id, node_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_story_nodes_node ON story_nodes (node_id)",
    "CREATE INDEX IF NOT EXISTS idx_story_nodes_primary_event ON story_nodes (node_id, is_primary_event)",
    """
    CREATE TABLE IF NOT EXISTS node_relations (
        source_node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        target_node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        relation_type TEXT NOT NULL,
        score DOUBLE PRECISION NOT NULL,
        shared_story_count INT NOT NULL,
        latest_story_at TIMESTAMPTZ,
        PRIMARY KEY (source_node_id, target_node_id, relation_type),
        CHECK (source_node_id <> target_node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cross_channel_story_matches (
        story_id UUID NOT NULL REFERENCES story_units(story_id) ON DELETE CASCADE,
        matched_story_id UUID NOT NULL REFERENCES story_units(story_id) ON DELETE CASCADE,
        similarity_score DOUBLE PRECISION NOT NULL,
        timestamp_delta_seconds INT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (story_id, matched_story_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theme_daily_stats (
        node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        date DATE NOT NULL,
        article_count INT NOT NULL,
        centroid_drift DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (node_id, date)
    )
    """,
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS theme_heat_view AS
    WITH windows AS (
        SELECT unnest(ARRAY[1, 3, 5, 7, 14, 31]) AS days
    ),
    window_totals AS (
        SELECT w.days, COUNT(*) AS total
        FROM windows w
        JOIN story_units su ON su.timestamp_start >= NOW() - (w.days || ' days')::INTERVAL
        GROUP BY w.days
    ),
    window_counts AS (
        SELECT sn.node_id, w.days, COUNT(*) AS cnt
        FROM windows w
        JOIN story_units su ON su.timestamp_start >= NOW() - (w.days || ' days')::INTERVAL
        JOIN story_nodes sn ON sn.story_id = su.story_id
        JOIN nodes n ON n.node_id = sn.node_id
        WHERE n.kind = 'theme' AND n.status = 'active'
        GROUP BY sn.node_id, w.days
    ),
    base AS (
        SELECT
            n.node_id,
            n.slug,
            n.display_name,
            n.article_count,
            COALESCE(MAX(CASE WHEN wc.days = 1 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_1d,
            COALESCE(MAX(CASE WHEN wc.days = 3 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_3d,
            COALESCE(MAX(CASE WHEN wc.days = 5 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_5d,
            COALESCE(MAX(CASE WHEN wc.days = 7 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_7d,
            COALESCE(MAX(CASE WHEN wc.days = 14 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_14d,
            COALESCE(MAX(CASE WHEN wc.days = 31 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_31d
        FROM nodes n
        LEFT JOIN window_counts wc ON wc.node_id = n.node_id
        LEFT JOIN window_totals wt ON wt.days = wc.days
        WHERE n.kind = 'theme' AND n.status = 'active'
        GROUP BY n.node_id, n.slug, n.display_name, n.article_count
    )
    SELECT
        base.*,
        CASE
            WHEN base.heat_1d > 0.10 AND base.heat_31d < 0.02 THEN 'emerging'
            WHEN base.heat_31d > 0.05 AND base.heat_1d < 0.01 THEN 'fading'
            WHEN ABS(base.heat_1d - base.heat_31d) < 0.02 THEN 'sustained'
            WHEN base.heat_3d > 0.10 AND base.heat_7d < 0.02 THEN 'flash_event'
            ELSE 'steady'
        END AS phase
    FROM base
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_theme_heat_view_node ON theme_heat_view (node_id)",
]


class PostgresStoryRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError("psycopg is not installed. Install project dependencies before using KG commands.") from exc
        return psycopg.connect(self.database_url)

    def _jsonb(self, value: Any) -> Any:
        from psycopg.types.json import Jsonb

        return Jsonb(_json_ready(value), dumps=json.dumps)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            connection.commit()

    def upsert_channel_profile(self, profile: ChannelProfile) -> None:
        payload = [
            {
                "kind": pattern.kind,
                "pattern": pattern.pattern,
                "case_sensitive": pattern.case_sensitive,
            }
            for pattern in profile.delimiter_patterns
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO channel_profiles (
                        channel_id,
                        delimiter_patterns,
                        media_group_window_seconds,
                        time_gap_minutes,
                        similarity_merge_threshold,
                        lookback_story_count,
                        notes,
                        channel_title,
                        channel_slug,
                        channel_username
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        delimiter_patterns = EXCLUDED.delimiter_patterns,
                        media_group_window_seconds = EXCLUDED.media_group_window_seconds,
                        time_gap_minutes = EXCLUDED.time_gap_minutes,
                        similarity_merge_threshold = EXCLUDED.similarity_merge_threshold,
                        lookback_story_count = EXCLUDED.lookback_story_count,
                        notes = EXCLUDED.notes,
                        channel_title = EXCLUDED.channel_title,
                        channel_slug = EXCLUDED.channel_slug,
                        channel_username = EXCLUDED.channel_username,
                        updated_at = NOW()
                    """,
                    (
                        profile.channel_id,
                        self._jsonb(payload),
                        profile.media_group_window_seconds,
                        profile.time_gap_minutes,
                        profile.similarity_merge_threshold,
                        profile.lookback_story_count,
                        profile.notes,
                        profile.channel_title,
                        profile.channel_slug,
                        profile.channel_username,
                    ),
                )
            connection.commit()

    def get_channel_profile(self, channel_id: int) -> ChannelProfile | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT channel_id, delimiter_patterns, media_group_window_seconds, time_gap_minutes,
                           similarity_merge_threshold, lookback_story_count, notes,
                           channel_title, channel_slug, channel_username, created_at, updated_at
                    FROM channel_profiles
                    WHERE channel_id = %s
                    """,
                    (channel_id,),
                )
                row = cursor.fetchone()
        return _channel_profile_from_row(row) if row is not None else None

    def list_channels(self) -> list[ChannelSummary]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        su.channel_id,
                        cp.channel_title,
                        cp.channel_slug,
                        cp.channel_username,
                        COUNT(DISTINCT su.story_id)::INT AS story_count
                    FROM story_units su
                    LEFT JOIN channel_profiles cp ON cp.channel_id = su.channel_id
                    GROUP BY su.channel_id, cp.channel_title, cp.channel_slug, cp.channel_username
                    ORDER BY COALESCE(NULLIF(cp.channel_title, ''), NULLIF(cp.channel_slug, ''), NULLIF(cp.channel_username, ''), su.channel_id::TEXT)
                    """
                )
                rows = cursor.fetchall()
        return [_channel_summary_from_row(row) for row in rows]

    def upsert_raw_messages(self, messages: Sequence[RawMessage]) -> None:
        if not messages:
            return
        rows = [
            (
                message.channel_id,
                message.message_id,
                ensure_utc(message.timestamp),
                message.sender_id,
                message.sender_name,
                message.text,
                message.english_text,
                message.source_language,
                ensure_utc(message.translated_at) if message.translated_at is not None else None,
                self._jsonb(_serialize_media_refs(message.media_refs)),
                message.forwarded_from,
                message.reply_to_message_id,
                self._jsonb(message.raw_json),
            )
            for message in messages
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO raw_messages (
                        channel_id,
                        message_id,
                        timestamp,
                        sender_id,
                        sender_name,
                        text,
                        english_text,
                        source_language,
                        translated_at,
                        media_refs,
                        forwarded_from,
                        reply_to_message_id,
                        raw_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (channel_id, message_id) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        sender_id = EXCLUDED.sender_id,
                        sender_name = EXCLUDED.sender_name,
                        text = EXCLUDED.text,
                        english_text = COALESCE(raw_messages.english_text, EXCLUDED.english_text),
                        source_language = COALESCE(raw_messages.source_language, EXCLUDED.source_language),
                        translated_at = COALESCE(raw_messages.translated_at, EXCLUDED.translated_at),
                        media_refs = EXCLUDED.media_refs,
                        forwarded_from = EXCLUDED.forwarded_from,
                        reply_to_message_id = EXCLUDED.reply_to_message_id,
                        raw_json = EXCLUDED.raw_json
                    """,
                    rows,
                )
            connection.commit()

    def save_raw_message_translations(self, messages: Sequence[RawMessage]) -> None:
        if not messages:
            return
        rows = [
            (
                message.english_text,
                message.source_language,
                ensure_utc(message.translated_at) if message.translated_at is not None else None,
                message.channel_id,
                message.message_id,
            )
            for message in messages
            if message.english_text is not None or message.source_language is not None or message.translated_at is not None
        ]
        if not rows:
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE raw_messages
                    SET english_text = %s,
                        source_language = %s,
                        translated_at = %s
                    WHERE channel_id = %s AND message_id = %s
                    """,
                    rows,
                )
            connection.commit()

    def list_unsegmented_raw_messages(self, channel_id: int, *, limit: int | None = None) -> list[RawMessage]:
        query = """
            SELECT rm.channel_id, rm.message_id, rm.timestamp, rm.sender_id, rm.sender_name,
                   rm.text, rm.english_text, rm.source_language, rm.translated_at,
                   rm.media_refs, rm.forwarded_from, rm.reply_to_message_id, rm.raw_json
            FROM raw_messages rm
            LEFT JOIN story_messages sm
              ON sm.channel_id = rm.channel_id AND sm.message_id = rm.message_id
            WHERE rm.channel_id = %s AND sm.message_id IS NULL
            ORDER BY rm.timestamp, rm.message_id
        """
        params: list[Any] = [channel_id]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def list_recent_raw_messages(self, channel_id: int, *, limit: int) -> list[RawMessage]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM (
                        SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                               text, english_text, source_language, translated_at,
                               media_refs, forwarded_from, reply_to_message_id, raw_json
                        FROM raw_messages
                        WHERE channel_id = %s
                        ORDER BY timestamp DESC, message_id DESC
                        LIMIT %s
                    ) recent
                    ORDER BY timestamp, message_id
                    """,
                    (channel_id, limit),
                )
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def list_raw_messages(self, channel_id: int) -> list[RawMessage]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                           text, english_text, source_language, translated_at,
                           media_refs, forwarded_from, reply_to_message_id, raw_json
                    FROM raw_messages
                    WHERE channel_id = %s
                    ORDER BY timestamp, message_id
                    """,
                    (channel_id,),
                )
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def get_last_story_unit(self, channel_id: int) -> StoryUnit | None:
        stories = self.list_recent_story_units(channel_id, limit=1)
        return stories[0] if stories else None

    def list_recent_story_units(self, channel_id: int, *, limit: int) -> list[StoryUnit]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT story_id, channel_id, timestamp_start, timestamp_end, message_ids, combined_text,
                           english_combined_text, translation_updated_at, media_refs, created_at
                    FROM story_units
                    WHERE channel_id = %s
                    ORDER BY timestamp_end DESC, created_at DESC
                    LIMIT %s
                    """,
                    (channel_id, limit),
                )
                rows = cursor.fetchall()
        return [_story_from_row(row) for row in rows]

    def list_story_units(self, *, channel_id: int | None = None) -> list[StoryUnit]:
        query = """
            SELECT story_id, channel_id, timestamp_start, timestamp_end, message_ids, combined_text,
                   english_combined_text, translation_updated_at, media_refs, created_at
            FROM story_units
        """
        params: list[Any] = []
        if channel_id is not None:
            query += " WHERE channel_id = %s"
            params.append(channel_id)
        query += " ORDER BY timestamp_start, story_id"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_story_from_row(row) for row in rows]

    def get_story_messages(self, story_id: str) -> list[RawMessage]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rm.channel_id, rm.message_id, rm.timestamp, rm.sender_id, rm.sender_name,
                           rm.text, rm.english_text, rm.source_language, rm.translated_at,
                           rm.media_refs, rm.forwarded_from, rm.reply_to_message_id, rm.raw_json
                    FROM story_messages sm
                    JOIN raw_messages rm
                      ON rm.channel_id = sm.channel_id AND rm.message_id = sm.message_id
                    WHERE sm.story_id = %s
                    ORDER BY sm.position, rm.message_id
                    """,
                    (story_id,),
                )
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def save_story_units(self, stories: Sequence[StoryUnit]) -> None:
        if not stories:
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for story in stories:
                    cursor.execute(
                        """
                        INSERT INTO story_units (
                            story_id,
                            channel_id,
                            timestamp_start,
                            timestamp_end,
                            message_ids,
                            combined_text,
                            english_combined_text,
                            translation_updated_at,
                            media_refs,
                            created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
                        ON CONFLICT (story_id) DO UPDATE SET
                            channel_id = EXCLUDED.channel_id,
                            timestamp_start = EXCLUDED.timestamp_start,
                            timestamp_end = EXCLUDED.timestamp_end,
                            message_ids = EXCLUDED.message_ids,
                            combined_text = EXCLUDED.combined_text,
                            english_combined_text = EXCLUDED.english_combined_text,
                            translation_updated_at = EXCLUDED.translation_updated_at,
                            media_refs = EXCLUDED.media_refs
                        """,
                        (
                            story.story_id,
                            story.channel_id,
                            ensure_utc(story.timestamp_start),
                            ensure_utc(story.timestamp_end),
                            list(story.message_ids),
                            story.combined_text,
                            story.english_combined_text,
                            ensure_utc(story.translation_updated_at) if story.translation_updated_at is not None else None,
                            self._jsonb(_serialize_media_refs(story.media_refs)),
                            ensure_utc(story.created_at) if story.created_at is not None else None,
                        ),
                    )
                    cursor.execute("DELETE FROM story_messages WHERE story_id = %s", (story.story_id,))
                    cursor.executemany(
                        """
                        INSERT INTO story_messages (story_id, channel_id, message_id, position)
                        VALUES (%s, %s, %s, %s)
                        """,
                        [
                            (story.story_id, story.channel_id, message_id, position)
                            for position, message_id in enumerate(story.message_ids)
                        ],
                    )
            connection.commit()

    def list_stories_without_semantics(
        self,
        *,
        channel_id: int | None = None,
        limit: int | None = None,
    ) -> list[StoryUnit]:
        query = """
            SELECT su.story_id, su.channel_id, su.timestamp_start, su.timestamp_end, su.message_ids, su.combined_text,
                   su.english_combined_text, su.translation_updated_at, su.media_refs, su.created_at
            FROM story_units su
            LEFT JOIN story_semantics ss ON ss.story_id = su.story_id
            WHERE ss.story_id IS NULL
        """
        params: list[Any] = []
        if channel_id is not None:
            query += " AND su.channel_id = %s"
            params.append(channel_id)
        query += " ORDER BY su.timestamp_start ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_story_from_row(row) for row in rows]

    def get_story_unit(self, story_id: str) -> StoryUnit | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT story_id, channel_id, timestamp_start, timestamp_end, message_ids, combined_text,
                           english_combined_text, translation_updated_at, media_refs, created_at
                    FROM story_units
                    WHERE story_id = %s
                    """,
                    (story_id,),
                )
                row = cursor.fetchone()
        return _story_from_row(row) if row is not None else None

    def upsert_story_semantics(self, records: Sequence[StorySemanticRecord]) -> None:
        if not records:
            return
        rows = [
            (
                record.story_id,
                self._jsonb(record.extraction_payload),
                record.primary_event_node_id,
                ensure_utc(record.processed_at) if record.processed_at is not None else None,
                ensure_utc(record.updated_at) if record.updated_at is not None else None,
            )
            for record in records
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO story_semantics (
                        story_id,
                        extraction_payload,
                        primary_event_node_id,
                        processed_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()))
                    ON CONFLICT (story_id) DO UPDATE SET
                        extraction_payload = EXCLUDED.extraction_payload,
                        primary_event_node_id = EXCLUDED.primary_event_node_id,
                        processed_at = EXCLUDED.processed_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    rows,
                )
            connection.commit()

    def save_semantic_results(
        self,
        *,
        nodes: Sequence[Node],
        assignments: Sequence[StoryNodeAssignment],
        semantics: Sequence[StorySemanticRecord],
        cross_channel_matches: Sequence[CrossChannelMatch] = (),
    ) -> None:
        if not nodes and not assignments and not semantics and not cross_channel_matches:
            return
        node_rows = [
            (
                node.node_id,
                node.kind,
                node.slug,
                node.display_name,
                node.canonical_name,
                node.normalized_name,
                node.summary,
                list(node.aliases),
                node.status,
                node.label_source,
                node.article_count,
                ensure_utc(node.created_at) if node.created_at is not None else None,
                ensure_utc(node.last_updated) if node.last_updated is not None else None,
                ensure_utc(node.event_start_at) if node.event_start_at is not None else None,
                ensure_utc(node.event_end_at) if node.event_end_at is not None else None,
            )
            for node in nodes
        ]
        assignment_rows = [
            (
                assignment.story_id,
                assignment.node_id,
                assignment.confidence,
                ensure_utc(assignment.assigned_at) if assignment.assigned_at is not None else None,
                assignment.is_primary_event,
            )
            for assignment in assignments
        ]
        semantic_rows = [
            (
                record.story_id,
                self._jsonb(record.extraction_payload),
                record.primary_event_node_id,
                ensure_utc(record.processed_at) if record.processed_at is not None else None,
                ensure_utc(record.updated_at) if record.updated_at is not None else None,
            )
            for record in semantics
        ]
        match_rows = [
            (
                match.story_id,
                match.matched_story_id,
                match.similarity_score,
                match.timestamp_delta_seconds,
                ensure_utc(match.created_at) if match.created_at is not None else None,
            )
            for match in cross_channel_matches
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if node_rows:
                    cursor.executemany(
                        """
                        INSERT INTO nodes (
                            node_id,
                            kind,
                            slug,
                            display_name,
                            canonical_name,
                            normalized_name,
                            summary,
                            aliases,
                            status,
                            label_source,
                            article_count,
                            created_at,
                            last_updated,
                            event_start_at,
                            event_end_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()), %s, %s)
                        ON CONFLICT (node_id) DO UPDATE SET
                            kind = EXCLUDED.kind,
                            slug = EXCLUDED.slug,
                            display_name = EXCLUDED.display_name,
                            canonical_name = EXCLUDED.canonical_name,
                            normalized_name = EXCLUDED.normalized_name,
                            summary = EXCLUDED.summary,
                            aliases = EXCLUDED.aliases,
                            status = EXCLUDED.status,
                            label_source = EXCLUDED.label_source,
                            article_count = EXCLUDED.article_count,
                            last_updated = EXCLUDED.last_updated,
                            event_start_at = EXCLUDED.event_start_at,
                            event_end_at = EXCLUDED.event_end_at
                        """,
                        node_rows,
                    )
                if assignment_rows:
                    cursor.executemany(
                        """
                        INSERT INTO story_nodes (story_id, node_id, confidence, assigned_at, is_primary_event)
                        VALUES (%s, %s, %s, COALESCE(%s, NOW()), %s)
                        ON CONFLICT (story_id, node_id) DO UPDATE SET
                            confidence = EXCLUDED.confidence,
                            assigned_at = EXCLUDED.assigned_at,
                            is_primary_event = EXCLUDED.is_primary_event
                        """,
                        assignment_rows,
                    )
                if semantic_rows:
                    cursor.executemany(
                        """
                        INSERT INTO story_semantics (
                            story_id,
                            extraction_payload,
                            primary_event_node_id,
                            processed_at,
                            updated_at
                        )
                        VALUES (%s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()))
                        ON CONFLICT (story_id) DO UPDATE SET
                            extraction_payload = EXCLUDED.extraction_payload,
                            primary_event_node_id = EXCLUDED.primary_event_node_id,
                            processed_at = EXCLUDED.processed_at,
                            updated_at = EXCLUDED.updated_at
                        """,
                        semantic_rows,
                    )
                if match_rows:
                    cursor.executemany(
                        """
                        INSERT INTO cross_channel_story_matches (
                            story_id,
                            matched_story_id,
                            similarity_score,
                            timestamp_delta_seconds,
                            created_at
                        )
                        VALUES (%s, %s, %s, %s, COALESCE(%s, NOW()))
                        ON CONFLICT (story_id, matched_story_id) DO UPDATE SET
                            similarity_score = EXCLUDED.similarity_score,
                            timestamp_delta_seconds = EXCLUDED.timestamp_delta_seconds,
                            created_at = EXCLUDED.created_at
                        """,
                        match_rows,
                    )
            connection.commit()

    def get_story_semantic_record(self, story_id: str) -> StorySemanticRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT story_id, extraction_payload, primary_event_node_id, processed_at, updated_at
                    FROM story_semantics
                    WHERE story_id = %s
                    """,
                    (story_id,),
                )
                row = cursor.fetchone()
        return _story_semantic_from_row(row) if row is not None else None

    def save_nodes(self, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        rows = [
            (
                node.node_id,
                node.kind,
                node.slug,
                node.display_name,
                node.canonical_name,
                node.normalized_name,
                node.summary,
                list(node.aliases),
                node.status,
                node.label_source,
                node.article_count,
                ensure_utc(node.created_at) if node.created_at is not None else None,
                ensure_utc(node.last_updated) if node.last_updated is not None else None,
                ensure_utc(node.event_start_at) if node.event_start_at is not None else None,
                ensure_utc(node.event_end_at) if node.event_end_at is not None else None,
            )
            for node in nodes
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO nodes (
                        node_id,
                        kind,
                        slug,
                        display_name,
                        canonical_name,
                        normalized_name,
                        summary,
                        aliases,
                        status,
                        label_source,
                        article_count,
                        created_at,
                        last_updated,
                        event_start_at,
                        event_end_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()), %s, %s)
                    ON CONFLICT (node_id) DO UPDATE SET
                        kind = EXCLUDED.kind,
                        slug = EXCLUDED.slug,
                        display_name = EXCLUDED.display_name,
                        canonical_name = EXCLUDED.canonical_name,
                        normalized_name = EXCLUDED.normalized_name,
                        summary = EXCLUDED.summary,
                        aliases = EXCLUDED.aliases,
                        status = EXCLUDED.status,
                        label_source = EXCLUDED.label_source,
                        article_count = EXCLUDED.article_count,
                        last_updated = EXCLUDED.last_updated,
                        event_start_at = EXCLUDED.event_start_at,
                        event_end_at = EXCLUDED.event_end_at
                    """,
                    rows,
                )
            connection.commit()

    def get_nodes(self, node_ids: Sequence[str]) -> list[Node]:
        if not node_ids:
            return []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT node_id, kind, slug, display_name, canonical_name, normalized_name, summary,
                           aliases, status, label_source, article_count, created_at, last_updated,
                           event_start_at, event_end_at
                    FROM nodes
                    WHERE node_id = ANY(%s)
                    """,
                    (list(node_ids),),
                )
                rows = cursor.fetchall()
        return [_node_from_row(row) for row in rows]

    def list_nodes(
        self,
        *,
        kind: NodeKind | None = None,
        status: str | None = "active",
        limit: int | None = None,
    ) -> list[Node]:
        query = """
            SELECT node_id, kind, slug, display_name, canonical_name, normalized_name, summary,
                   aliases, status, label_source, article_count, created_at, last_updated,
                   event_start_at, event_end_at
            FROM nodes
            WHERE 1 = 1
        """
        params: list[Any] = []
        if kind is not None:
            query += " AND kind = %s"
            params.append(kind)
        if status is not None:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY article_count DESC, last_updated DESC, display_name ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_node_from_row(row) for row in rows]

    def get_node_by_slug(self, *, kind: NodeKind, slug: str) -> Node | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT node_id, kind, slug, display_name, canonical_name, normalized_name, summary,
                           aliases, status, label_source, article_count, created_at, last_updated,
                           event_start_at, event_end_at
                    FROM nodes
                    WHERE kind = %s AND slug = %s
                    """,
                    (kind, slug),
                )
                row = cursor.fetchone()
        return _node_from_row(row) if row is not None else None

    def save_node_relations(self, relations: Sequence[NodeRelation]) -> None:
        if not relations:
            return
        rows = [
            (
                relation.source_node_id,
                relation.target_node_id,
                relation.relation_type,
                relation.score,
                relation.shared_story_count,
                ensure_utc(relation.latest_story_at) if relation.latest_story_at is not None else None,
            )
            for relation in relations
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO node_relations (
                        source_node_id,
                        target_node_id,
                        relation_type,
                        score,
                        shared_story_count,
                        latest_story_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
                        score = EXCLUDED.score,
                        shared_story_count = EXCLUDED.shared_story_count,
                        latest_story_at = EXCLUDED.latest_story_at
                    """,
                    rows,
                )
            connection.commit()

    def replace_node_relations(self, relations: Sequence[NodeRelation]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM node_relations")
            connection.commit()
        self.save_node_relations(relations)

    def list_node_relations(self, node_id: str) -> list[NodeRelation]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source_node_id, target_node_id, relation_type, score, shared_story_count, latest_story_at
                    FROM node_relations
                    WHERE source_node_id = %s OR target_node_id = %s
                    ORDER BY score DESC, latest_story_at DESC NULLS LAST
                    """,
                    (node_id, node_id),
                )
                rows = cursor.fetchall()
        return [_node_relation_from_row(row) for row in rows]

    def save_story_node_assignments(self, assignments: Sequence[StoryNodeAssignment]) -> None:
        if not assignments:
            return
        rows = [
            (
                assignment.story_id,
                assignment.node_id,
                assignment.confidence,
                ensure_utc(assignment.assigned_at) if assignment.assigned_at is not None else None,
                assignment.is_primary_event,
            )
            for assignment in assignments
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO story_nodes (story_id, node_id, confidence, assigned_at, is_primary_event)
                    VALUES (%s, %s, %s, COALESCE(%s, NOW()), %s)
                    ON CONFLICT (story_id, node_id) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        assigned_at = EXCLUDED.assigned_at,
                        is_primary_event = EXCLUDED.is_primary_event
                    """,
                    rows,
                )
            connection.commit()

    def delete_story_node_assignments(
        self,
        *,
        node_id: str | None = None,
        story_ids: Sequence[str] | None = None,
    ) -> None:
        clauses: list[str] = []
        params: list[Any] = []
        if node_id is not None:
            clauses.append("node_id = %s")
            params.append(node_id)
        if story_ids:
            clauses.append("story_id = ANY(%s)")
            params.append(list(story_ids))
        if not clauses:
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM story_nodes WHERE {' AND '.join(clauses)}", params)
            connection.commit()

    def get_story_node_assignments(self, story_id: str) -> list[StoryNodeAssignment]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT story_id, node_id, confidence, assigned_at, is_primary_event
                    FROM story_nodes
                    WHERE story_id = %s
                    ORDER BY is_primary_event DESC, confidence DESC, node_id
                    """,
                    (story_id,),
                )
                rows = cursor.fetchall()
        return [_story_node_assignment_from_row(row) for row in rows]

    def list_story_node_ids(self, story_id: str) -> list[str]:
        return [assignment.node_id for assignment in self.get_story_node_assignments(story_id)]

    def list_story_ids_for_node_on_date(self, node_id: str, day: date) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sn.story_id
                    FROM story_nodes sn
                    JOIN story_units su ON su.story_id = sn.story_id
                    WHERE sn.node_id = %s
                      AND su.timestamp_start >= %s::date
                      AND su.timestamp_start < (%s::date + INTERVAL '1 day')
                    ORDER BY su.timestamp_start, sn.story_id
                    """,
                    (node_id, day, day),
                )
                rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

    def list_story_ids_for_node(self, node_id: str) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT story_id FROM story_nodes WHERE node_id = %s ORDER BY story_id",
                    (node_id,),
                )
                rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

    def list_stories_for_node(self, node_id: str, *, limit: int, offset: int) -> tuple[int, list[tuple[StoryUnit, StoryNodeAssignment]]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM story_nodes WHERE node_id = %s", (node_id,))
                total = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    SELECT
                        su.story_id, su.channel_id, su.timestamp_start, su.timestamp_end, su.message_ids, su.combined_text,
                        su.english_combined_text, su.translation_updated_at, su.media_refs, su.created_at,
                        sn.story_id, sn.node_id, sn.confidence, sn.assigned_at, sn.is_primary_event
                    FROM story_nodes sn
                    JOIN story_units su ON su.story_id = sn.story_id
                    WHERE sn.node_id = %s
                    ORDER BY su.timestamp_start DESC, su.story_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (node_id, limit, offset),
                )
                rows = cursor.fetchall()
        items = [
            (
                _story_from_row(row[:10]),
                _story_node_assignment_from_row(row[10:15]),
            )
            for row in rows
        ]
        return total, items

    def save_cross_channel_matches(self, matches: Sequence[CrossChannelMatch]) -> None:
        if not matches:
            return
        rows = [
            (
                match.story_id,
                match.matched_story_id,
                match.similarity_score,
                match.timestamp_delta_seconds,
                ensure_utc(match.created_at) if match.created_at is not None else None,
            )
            for match in matches
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO cross_channel_story_matches (
                        story_id,
                        matched_story_id,
                        similarity_score,
                        timestamp_delta_seconds,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, COALESCE(%s, NOW()))
                    ON CONFLICT (story_id, matched_story_id) DO UPDATE SET
                        similarity_score = EXCLUDED.similarity_score,
                        timestamp_delta_seconds = EXCLUDED.timestamp_delta_seconds,
                        created_at = EXCLUDED.created_at
                    """,
                    rows,
                )
            connection.commit()

    def replace_cross_channel_matches(self, matches: Sequence[CrossChannelMatch]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM cross_channel_story_matches")
            connection.commit()
        self.save_cross_channel_matches(matches)

    def list_cross_channel_matches(self) -> list[CrossChannelMatch]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT story_id, matched_story_id, similarity_score, timestamp_delta_seconds, created_at
                    FROM cross_channel_story_matches
                    ORDER BY similarity_score DESC, created_at DESC
                    """
                )
                rows = cursor.fetchall()
        return [_cross_channel_match_from_row(row) for row in rows]

    def save_theme_daily_stats(self, stats: Sequence[ThemeDailyStat]) -> None:
        if not stats:
            return
        rows = [(stat.node_id, stat.date, stat.article_count, stat.centroid_drift) for stat in stats]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO theme_daily_stats (node_id, date, article_count, centroid_drift)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (node_id, date) DO UPDATE SET
                        article_count = EXCLUDED.article_count,
                        centroid_drift = EXCLUDED.centroid_drift
                    """,
                    rows,
                )
            connection.commit()

    def refresh_theme_heat_view(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("REFRESH MATERIALIZED VIEW theme_heat_view")
            connection.commit()

    def clear_semantic_state(self, *, channel_id: int | None = None) -> tuple[list[str], list[str], list[str]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                story_query = "SELECT story_id FROM story_units"
                story_params: list[Any] = []
                if channel_id is not None:
                    story_query += " WHERE channel_id = %s"
                    story_params.append(channel_id)
                story_query += " ORDER BY timestamp_start, story_id"
                cursor.execute(story_query, story_params)
                story_ids = [str(row[0]) for row in cursor.fetchall()]
                if not story_ids:
                    return [], [], []

                cursor.execute(
                    """
                    SELECT DISTINCT n.node_id, n.kind
                    FROM story_nodes sn
                    JOIN nodes n ON n.node_id = sn.node_id
                    WHERE sn.story_id = ANY(%s)
                    """,
                    (story_ids,),
                )
                affected = [(str(row[0]), str(row[1])) for row in cursor.fetchall()]
                affected_node_ids = [node_id for node_id, _kind in affected]

                cursor.execute(
                    """
                    DELETE FROM cross_channel_story_matches
                    WHERE story_id = ANY(%s) OR matched_story_id = ANY(%s)
                    """,
                    (story_ids, story_ids),
                )
                cursor.execute("DELETE FROM story_semantics WHERE story_id = ANY(%s)", (story_ids,))
                cursor.execute("DELETE FROM story_nodes WHERE story_id = ANY(%s)", (story_ids,))
                if affected_node_ids:
                    affected_theme_ids = [node_id for node_id, kind in affected if kind == "theme"]
                    cursor.execute(
                        """
                        DELETE FROM node_relations
                        WHERE source_node_id = ANY(%s) OR target_node_id = ANY(%s)
                        """,
                        (affected_node_ids, affected_node_ids),
                    )
                    if affected_theme_ids:
                        cursor.execute("DELETE FROM theme_daily_stats WHERE node_id = ANY(%s)", (affected_theme_ids,))
                    cursor.execute(
                        """
                        UPDATE nodes n
                        SET article_count = COALESCE(stats.article_count, 0),
                            last_updated = COALESCE(stats.last_story_at, n.last_updated)
                        FROM (
                            SELECT
                                sn.node_id,
                                COUNT(*)::INT AS article_count,
                                MAX(su.timestamp_end) AS last_story_at
                            FROM story_nodes sn
                            JOIN story_units su ON su.story_id = sn.story_id
                            WHERE sn.node_id = ANY(%s)
                            GROUP BY sn.node_id
                        ) stats
                        WHERE n.node_id = stats.node_id
                        """,
                        (affected_node_ids,),
                    )
                    cursor.execute(
                        """
                        UPDATE nodes
                        SET article_count = 0
                        WHERE node_id = ANY(%s)
                          AND node_id NOT IN (SELECT DISTINCT node_id FROM story_nodes)
                        """,
                        (affected_node_ids,),
                    )
                    cursor.execute(
                        """
                        SELECT node_id, kind
                        FROM nodes
                        WHERE node_id = ANY(%s) AND article_count = 0
                        """,
                        (affected_node_ids,),
                    )
                    deleted_rows = [(str(row[0]), str(row[1])) for row in cursor.fetchall()]
                    deleted_node_ids = [node_id for node_id, _kind in deleted_rows]
                    if deleted_node_ids:
                        cursor.execute("DELETE FROM theme_daily_stats WHERE node_id = ANY(%s)", (deleted_node_ids,))
                        cursor.execute("DELETE FROM nodes WHERE node_id = ANY(%s)", (deleted_node_ids,))
                else:
                    deleted_rows = []
                connection.commit()

        theme_ids = [node_id for node_id, kind in deleted_rows if kind == "theme"]
        event_ids = [node_id for node_id, kind in deleted_rows if kind == "event"]
        return story_ids, theme_ids, event_ids

    def clear_story_state(self, *, channel_id: int) -> tuple[list[str], list[str], list[str]]:
        story_ids, theme_ids, event_ids = self.clear_semantic_state(channel_id=channel_id)
        if not story_ids:
            return story_ids, theme_ids, event_ids
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM story_units WHERE story_id = ANY(%s)", (story_ids,))
            connection.commit()
        return story_ids, theme_ids, event_ids

    def run_with_advisory_lock(self, lock_name: str, callback: Callable[[], None]) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (lock_name,))
                acquired = bool(cursor.fetchone()[0])
            if not acquired:
                return False
            try:
                callback()
                return True
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_name,))
                connection.commit()

    def list_theme_heat(self, *, phase: str | None = None, limit: int | None = None) -> list[ThemeHeatSnapshot]:
        query = """
            SELECT node_id, slug, display_name, article_count, heat_1d, heat_3d, heat_5d, heat_7d, heat_14d, heat_31d, phase
            FROM theme_heat_view
        """
        params: list[Any] = []
        if phase is not None:
            query += " WHERE phase = %s"
            params.append(phase)
        query += " ORDER BY heat_1d DESC, heat_3d DESC, display_name ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_theme_heat_from_row(row) for row in rows]

    def get_theme_history(self, *, slug: str) -> list[ThemeHistoryPoint]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tds.node_id, n.slug, n.display_name, tds.date, tds.article_count, tds.centroid_drift
                    FROM theme_daily_stats tds
                    JOIN nodes n ON n.node_id = tds.node_id
                    WHERE n.kind = 'theme' AND n.slug = %s
                    ORDER BY tds.date
                    """,
                    (slug,),
                )
                rows = cursor.fetchall()
        return [_theme_history_from_row(row) for row in rows]

    def list_node_entries(self, *, kind: NodeKind, limit: int | None = None) -> list[NodeListEntry]:
        query = """
            SELECT node_id, kind, slug, display_name, summary, article_count, last_updated
            FROM nodes
            WHERE kind = %s AND status = 'active'
            ORDER BY article_count DESC, last_updated DESC, display_name ASC
        """
        params: list[Any] = [kind]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_node_list_entry_from_row(row) for row in rows]

    def get_node_detail(self, *, kind: NodeKind, slug: str, story_limit: int = 20, story_offset: int = 0) -> NodeDetail | None:
        node = self.get_node_by_slug(kind=kind, slug=slug)
        if node is None:
            return None
        relations = self.list_node_relations(node.node_id)
        related_ids = {
            relation.target_node_id if relation.source_node_id == node.node_id else relation.source_node_id
            for relation in relations
        }
        related_nodes = {related.node_id: related for related in self.get_nodes(sorted(related_ids))}

        bucketed: dict[str, list[RelatedNode]] = defaultdict(list)
        for relation in relations:
            related_id = relation.target_node_id if relation.source_node_id == node.node_id else relation.source_node_id
            related = related_nodes.get(related_id)
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
                    score=relation.score,
                    shared_story_count=relation.shared_story_count,
                    latest_story_at=relation.latest_story_at,
                )
            )

        total, stories = self.list_stories_for_node(node.node_id, limit=story_limit, offset=story_offset)
        del total
        channel_profiles = {
            profile.channel_id: profile
            for profile in [
                self.get_channel_profile(story.channel_id)
                for story, _assignment in stories
            ]
            if profile is not None
        }
        story_rows = tuple(
            NodeStory(
                story_id=story.story_id,
                channel_id=story.channel_id,
                channel_title=_channel_title_for_story(story.channel_id, channel_profiles.get(story.channel_id)),
                timestamp_start=story.timestamp_start,
                timestamp_end=story.timestamp_end,
                confidence=assignment.confidence,
                preview_text=_preview_text(story.english_combined_text or story.combined_text),
                combined_text=story.english_combined_text or story.combined_text,
                original_preview_text=_preview_text(story.combined_text),
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
            events=tuple(_sort_related(bucketed["event"])),
            people=tuple(_sort_related(bucketed["person"])),
            nations=tuple(_sort_related(bucketed["nation"])),
            orgs=tuple(_sort_related(bucketed["org"])),
            places=tuple(_sort_related(bucketed["place"])),
            themes=tuple(_sort_related(bucketed["theme"])),
            stories=story_rows,
        )


def _channel_title_for_story(channel_id: int, profile: ChannelProfile | None) -> str:
    if profile is not None:
        for value in (profile.channel_title, profile.channel_slug, profile.channel_username):
            if value:
                return value
    return str(channel_id)


def _sort_related(nodes: list[RelatedNode]) -> list[RelatedNode]:
    return sorted(
        nodes,
        key=lambda item: (
            -item.score,
            -(item.latest_story_at.timestamp() if item.latest_story_at is not None else 0.0),
            item.display_name.lower(),
        ),
    )


def _preview_text(text: str, *, limit: int = 200) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def _serialize_media_refs(media_refs: Sequence[MediaRef]) -> list[dict[str, Any]]:
    return [
        {
            "media_type": media.media_type,
            "storage_path": media.storage_path,
            "mime_type": media.mime_type,
            "file_name": media.file_name,
        }
        for media in media_refs
    ]


def _deserialize_media_refs(payload: Any) -> tuple[MediaRef, ...]:
    if not isinstance(payload, list):
        return ()
    refs: list[MediaRef] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        refs.append(
            MediaRef(
                media_type=str(item.get("media_type") or "file"),
                storage_path=str(item["storage_path"]) if item.get("storage_path") is not None else None,
                mime_type=str(item["mime_type"]) if item.get("mime_type") is not None else None,
                file_name=str(item["file_name"]) if item.get("file_name") is not None else None,
            )
        )
    return tuple(refs)


def _story_from_row(row: Sequence[Any]) -> StoryUnit:
    return StoryUnit(
        story_id=str(row[0]),
        channel_id=int(row[1]),
        timestamp_start=ensure_utc(row[2]) or row[2],
        timestamp_end=ensure_utc(row[3]) or row[3],
        message_ids=tuple(int(value) for value in row[4]),
        combined_text=str(row[5] or ""),
        english_combined_text=str(row[6]) if row[6] is not None else None,
        translation_updated_at=ensure_utc(row[7]) if row[7] is not None else None,
        media_refs=_deserialize_media_refs(row[8]),
        created_at=ensure_utc(row[9]) if row[9] is not None else None,
    )


def _node_from_row(row: Sequence[Any]) -> Node:
    return Node(
        node_id=str(row[0]),
        kind=str(row[1]),
        slug=str(row[2]),
        display_name=str(row[3]),
        canonical_name=str(row[4]),
        normalized_name=str(row[5]),
        summary=str(row[6]) if row[6] is not None else None,
        aliases=tuple(str(value) for value in row[7] or []),
        status=str(row[8]),
        label_source=str(row[9]),
        article_count=int(row[10]),
        created_at=ensure_utc(row[11]) if row[11] is not None else None,
        last_updated=ensure_utc(row[12]) if row[12] is not None else None,
        event_start_at=ensure_utc(row[13]) if row[13] is not None else None,
        event_end_at=ensure_utc(row[14]) if row[14] is not None else None,
    )


def _raw_message_from_row(row: Sequence[Any]) -> RawMessage:
    return RawMessage(
        channel_id=int(row[0]),
        message_id=int(row[1]),
        timestamp=ensure_utc(row[2]) or row[2],
        sender_id=int(row[3]) if row[3] is not None else None,
        sender_name=str(row[4]) if row[4] is not None else None,
        text=str(row[5]) if row[5] is not None else None,
        english_text=str(row[6]) if row[6] is not None else None,
        source_language=str(row[7]) if row[7] is not None else None,
        translated_at=ensure_utc(row[8]) if row[8] is not None else None,
        media_refs=_deserialize_media_refs(row[9]),
        forwarded_from=int(row[10]) if row[10] is not None else None,
        reply_to_message_id=int(row[11]) if row[11] is not None else None,
        raw_json=dict(row[12] or {}),
    )


def _story_semantic_from_row(row: Sequence[Any]) -> StorySemanticRecord:
    return StorySemanticRecord(
        story_id=str(row[0]),
        extraction_payload=dict(row[1] or {}),
        primary_event_node_id=str(row[2]) if row[2] is not None else None,
        processed_at=ensure_utc(row[3]) if row[3] is not None else None,
        updated_at=ensure_utc(row[4]) if row[4] is not None else None,
    )


def _story_node_assignment_from_row(row: Sequence[Any]) -> StoryNodeAssignment:
    return StoryNodeAssignment(
        story_id=str(row[0]),
        node_id=str(row[1]),
        confidence=float(row[2]),
        assigned_at=ensure_utc(row[3]) if row[3] is not None else None,
        is_primary_event=bool(row[4]),
    )


def _node_relation_from_row(row: Sequence[Any]) -> NodeRelation:
    return NodeRelation(
        source_node_id=str(row[0]),
        target_node_id=str(row[1]),
        relation_type=str(row[2]),
        score=float(row[3]),
        shared_story_count=int(row[4]),
        latest_story_at=ensure_utc(row[5]) if row[5] is not None else None,
    )


def _channel_profile_from_row(row: Sequence[Any]) -> ChannelProfile:
    patterns = tuple(
        DelimiterPattern(
            kind=str(item.get("kind") or ""),
            pattern=str(item.get("pattern") or ""),
            case_sensitive=bool(item.get("case_sensitive", False)),
        )
        for item in (row[1] or [])
        if isinstance(item, dict)
    )
    return ChannelProfile(
        channel_id=int(row[0]),
        delimiter_patterns=patterns,
        media_group_window_seconds=int(row[2]),
        time_gap_minutes=int(row[3]),
        similarity_merge_threshold=float(row[4]),
        lookback_story_count=int(row[5]),
        notes=str(row[6]) if row[6] is not None else None,
        channel_title=str(row[7]) if row[7] is not None else None,
        channel_slug=str(row[8]) if row[8] is not None else None,
        channel_username=str(row[9]) if row[9] is not None else None,
        created_at=ensure_utc(row[10]) if row[10] is not None else None,
        updated_at=ensure_utc(row[11]) if row[11] is not None else None,
    )


def _channel_summary_from_row(row: Sequence[Any]) -> ChannelSummary:
    channel_id = int(row[0])
    channel_title = str(row[1] or row[2] or row[3] or channel_id)
    return ChannelSummary(
        channel_id=channel_id,
        channel_title=channel_title,
        channel_slug=str(row[2]) if row[2] is not None else None,
        channel_username=str(row[3]) if row[3] is not None else None,
        story_count=int(row[4]),
    )


def _cross_channel_match_from_row(row: Sequence[Any]) -> CrossChannelMatch:
    return CrossChannelMatch(
        story_id=str(row[0]),
        matched_story_id=str(row[1]),
        similarity_score=float(row[2]),
        timestamp_delta_seconds=int(row[3]) if row[3] is not None else None,
        created_at=ensure_utc(row[4]) if row[4] is not None else None,
    )


def _theme_heat_from_row(row: Sequence[Any]) -> ThemeHeatSnapshot:
    return ThemeHeatSnapshot(
        node_id=str(row[0]),
        slug=str(row[1]),
        display_name=str(row[2]),
        article_count=int(row[3]),
        heat_1d=float(row[4]),
        heat_3d=float(row[5]),
        heat_5d=float(row[6]),
        heat_7d=float(row[7]),
        heat_14d=float(row[8]),
        heat_31d=float(row[9]),
        phase=str(row[10]),
    )


def _theme_history_from_row(row: Sequence[Any]) -> ThemeHistoryPoint:
    return ThemeHistoryPoint(
        node_id=str(row[0]),
        slug=str(row[1]),
        display_name=str(row[2]),
        date=row[3],
        article_count=int(row[4]),
        centroid_drift=float(row[5]),
    )


def _node_list_entry_from_row(row: Sequence[Any]) -> NodeListEntry:
    return NodeListEntry(
        node_id=str(row[0]),
        kind=str(row[1]),
        slug=str(row[2]),
        display_name=str(row[3]),
        summary=str(row[4]) if row[4] is not None else None,
        article_count=int(row[5]),
        last_updated=ensure_utc(row[6]) if row[6] is not None else None,
    )
