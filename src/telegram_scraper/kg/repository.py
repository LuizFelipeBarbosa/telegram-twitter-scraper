from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime
import json
from typing import Any, Callable, Sequence

from telegram_scraper.kg.models import (
    ChannelProfile,
    ChannelSummary,
    CrossChannelMessageMatch,
    DelimiterPattern,
    MediaRef,
    MessageNodeAssignment,
    MessageSemanticRecord,
    Node,
    NodeDetail,
    NodeHeatSnapshot,
    NodeKind,
    NodeListEntry,
    NodeRelation,
    NodeSupportRecord,
    RawMessage,
    RelatedNode,
    ThemeDailyStat,
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
        parent_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
        UNIQUE (kind, slug)
    )
    """,
    "ALTER TABLE nodes ADD COLUMN IF NOT EXISTS parent_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind_status ON nodes (kind, status)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind_normalized_name ON nodes (kind, normalized_name)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind_canonical_name ON nodes (kind, canonical_name)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_event_parent ON nodes (kind, parent_node_id)",
    """
    CREATE TABLE IF NOT EXISTS node_relations (
        source_node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        target_node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        relation_type TEXT NOT NULL,
        score DOUBLE PRECISION NOT NULL,
        shared_message_count INT NOT NULL DEFAULT 0,
        latest_message_at TIMESTAMPTZ,
        PRIMARY KEY (source_node_id, target_node_id, relation_type),
        CHECK (source_node_id <> target_node_id)
    )
    """,
    # Rename legacy columns if they still exist (idempotent via DO $$ block).
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'node_relations' AND column_name = 'shared_story_count'
        ) THEN
            ALTER TABLE node_relations RENAME COLUMN shared_story_count TO shared_message_count;
        END IF;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'node_relations' AND column_name = 'latest_story_at'
        ) THEN
            ALTER TABLE node_relations RENAME COLUMN latest_story_at TO latest_message_at;
        END IF;
    END $$;
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
    "ALTER TABLE nodes ADD COLUMN IF NOT EXISTS parent_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_nodes_event_parent ON nodes (kind, parent_node_id)",
    "DROP MATERIALIZED VIEW IF EXISTS theme_heat_view CASCADE",
    "DROP MATERIALIZED VIEW IF EXISTS node_heat_view CASCADE",
    # ============================================================
    # Message-atomic pipeline tables.
    # ============================================================
    "ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS is_extracted BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS is_embedded BOOLEAN NOT NULL DEFAULT FALSE",
    "CREATE INDEX IF NOT EXISTS idx_raw_messages_extraction_pending ON raw_messages (channel_id, message_id) WHERE NOT is_extracted",
    "CREATE INDEX IF NOT EXISTS idx_raw_messages_embedding_pending ON raw_messages (channel_id, message_id) WHERE NOT is_embedded",
    """
    CREATE TABLE IF NOT EXISTS message_embeddings (
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        embedding_version TEXT NOT NULL DEFAULT 'text-embedding-3-small',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (channel_id, message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS message_semantics (
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        extraction_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        primary_event_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
        extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (channel_id, message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS message_nodes (
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        confidence DOUBLE PRECISION NOT NULL,
        assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_primary_event BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (channel_id, message_id, node_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_message_nodes_node ON message_nodes (node_id)",
    "CREATE INDEX IF NOT EXISTS idx_message_nodes_node_assigned_at ON message_nodes (node_id, assigned_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_message_nodes_node_primary ON message_nodes (node_id, is_primary_event)",
    """
    CREATE TABLE IF NOT EXISTS message_matches (
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        matched_channel_id BIGINT NOT NULL,
        matched_message_id BIGINT NOT NULL,
        similarity_score DOUBLE PRECISION NOT NULL,
        timestamp_delta_seconds INT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (channel_id, message_id, matched_channel_id, matched_message_id),
        CHECK (NOT (channel_id = matched_channel_id AND message_id = matched_message_id))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_message_matches_matched ON message_matches (matched_channel_id, matched_message_id)",
    # Drop old message_heat_view (if created in a previous migration run) before creating node_heat_view.
    "DROP MATERIALIZED VIEW IF EXISTS message_heat_view CASCADE",
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS node_heat_view AS
    WITH RECURSIVE
    windows AS (
        SELECT unnest(ARRAY[1, 3, 5, 7, 14, 31]) AS days
    ),
    window_totals AS (
        SELECT w.days, COUNT(*) AS total
        FROM windows w
        JOIN raw_messages rm ON rm.timestamp >= NOW() - (w.days || ' days')::INTERVAL
        GROUP BY w.days
    ),
    node_descendants AS (
        SELECT node_id AS root_id, node_id AS descendant_id, 0 AS depth
        FROM nodes
        WHERE status = 'active'

        UNION ALL

        SELECT nd.root_id, n.node_id, nd.depth + 1
        FROM node_descendants nd
        JOIN nodes n ON n.parent_node_id = nd.descendant_id
        WHERE n.status = 'active' AND nd.depth < 10
    ),
    window_counts AS (
        SELECT
            nd.root_id AS node_id,
            w.days,
            COUNT(DISTINCT (mn.channel_id, mn.message_id)) AS cnt
        FROM node_descendants nd
        JOIN message_nodes mn ON mn.node_id = nd.descendant_id
        JOIN raw_messages rm
            ON rm.channel_id = mn.channel_id AND rm.message_id = mn.message_id
        CROSS JOIN windows w
        WHERE rm.timestamp >= NOW() - (w.days || ' days')::INTERVAL
        GROUP BY nd.root_id, w.days
    ),
    base AS (
        SELECT
            n.node_id,
            n.kind,
            n.slug,
            n.display_name,
            n.article_count,
            COALESCE(MAX(CASE WHEN wc.days = 1  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_1d,
            COALESCE(MAX(CASE WHEN wc.days = 3  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_3d,
            COALESCE(MAX(CASE WHEN wc.days = 5  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_5d,
            COALESCE(MAX(CASE WHEN wc.days = 7  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_7d,
            COALESCE(MAX(CASE WHEN wc.days = 14 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_14d,
            COALESCE(MAX(CASE WHEN wc.days = 31 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_31d
        FROM nodes n
        LEFT JOIN window_counts wc ON wc.node_id = n.node_id
        LEFT JOIN window_totals wt ON wt.days = wc.days
        WHERE n.status = 'active'
        GROUP BY n.node_id, n.kind, n.slug, n.display_name, n.article_count
    )
    SELECT * FROM base
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_node_heat_view_node ON node_heat_view (node_id)",
    "CREATE INDEX IF NOT EXISTS idx_node_heat_view_kind ON node_heat_view (kind)",
]


class PostgresRepository:
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
                cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", ("kg-schema",))
            try:
                with connection.cursor() as cursor:
                    for statement in SCHEMA_STATEMENTS:
                        cursor.execute(statement)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", ("kg-schema",))
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
                        rm.channel_id,
                        cp.channel_title,
                        cp.channel_slug,
                        cp.channel_username,
                        COUNT(DISTINCT rm.message_id)::INT AS message_count
                    FROM raw_messages rm
                    LEFT JOIN channel_profiles cp ON cp.channel_id = rm.channel_id
                    GROUP BY rm.channel_id, cp.channel_title, cp.channel_slug, cp.channel_username
                    ORDER BY COALESCE(NULLIF(cp.channel_title, ''), NULLIF(cp.channel_slug, ''), NULLIF(cp.channel_username, ''), rm.channel_id::TEXT)
                    """
                )
                rows = cursor.fetchall()
        return [_channel_summary_from_row(row) for row in rows]

    def list_candidate_channel_ids(self) -> list[int]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT mn.channel_id
                    FROM message_nodes mn
                    JOIN nodes n ON n.node_id = mn.node_id
                    WHERE n.status = 'candidate'
                    ORDER BY mn.channel_id
                    """
                )
                rows = cursor.fetchall()
        return [int(row[0]) for row in rows]

    def list_node_ids_for_channels(
        self,
        *,
        channel_ids: Sequence[int],
        status: str | None = "active",
    ) -> list[str]:
        if not channel_ids:
            return []
        query = """
            SELECT DISTINCT mn.node_id
            FROM message_nodes mn
            JOIN nodes n ON n.node_id = mn.node_id
            WHERE mn.channel_id = ANY(%s)
        """
        params: list[Any] = [list(channel_ids)]
        if status is not None:
            query += " AND n.status = %s"
            params.append(status)
        query += " ORDER BY mn.node_id"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

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
        """Return raw messages not yet assigned to any node (is_extracted = FALSE)."""
        query = """
            SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                   text, english_text, source_language, translated_at,
                   media_refs, forwarded_from, reply_to_message_id, raw_json
            FROM raw_messages
            WHERE channel_id = %s AND is_extracted = FALSE
            ORDER BY timestamp, message_id
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
                node.parent_node_id,
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
                            event_end_at,
                            parent_node_id
                        )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()), %s, %s, %s)
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
                        event_end_at = EXCLUDED.event_end_at,
                        parent_node_id = EXCLUDED.parent_node_id
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
                           event_start_at, event_end_at, parent_node_id
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
                   event_start_at, event_end_at, parent_node_id
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

    def get_node_by_slug(self, *, kind: NodeKind, slug: str, status: str | None = "active") -> Node | None:
        query = """
            SELECT node_id, kind, slug, display_name, canonical_name, normalized_name, summary,
                   aliases, status, label_source, article_count, created_at, last_updated,
                   event_start_at, event_end_at, parent_node_id
            FROM nodes
            WHERE kind = %s AND slug = %s
        """
        params: list[Any] = [kind, slug]
        if status is not None:
            query += " AND status = %s"
            params.append(status)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    params,
                )
                row = cursor.fetchone()
        return _node_from_row(row) if row is not None else None

    def get_node_support_records(self, node_ids: Sequence[str]) -> list[NodeSupportRecord]:
        if not node_ids:
            return []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH msg_support AS (
                        SELECT
                            mn.node_id,
                            COUNT(DISTINCT (mn.channel_id, mn.message_id))::INT AS message_count,
                            COUNT(DISTINCT mn.channel_id)::INT AS channel_count,
                            ARRAY_AGG(DISTINCT mn.channel_id ORDER BY mn.channel_id) AS channel_ids
                        FROM message_nodes mn
                        WHERE mn.node_id = ANY(%s)
                        GROUP BY mn.node_id
                    ),
                    cross_support AS (
                        SELECT
                            mn.node_id,
                            BOOL_OR(mm.channel_id IS NOT NULL) AS has_cross_channel_match
                        FROM message_nodes mn
                        LEFT JOIN message_matches mm
                          ON mm.channel_id = mn.channel_id AND mm.message_id = mn.message_id
                        WHERE mn.node_id = ANY(%s)
                        GROUP BY mn.node_id
                    )
                    SELECT
                        n.node_id,
                        COALESCE(ms.message_count, 0),
                        COALESCE(ms.channel_count, 0),
                        COALESCE(cs.has_cross_channel_match, FALSE),
                        COALESCE(ms.channel_ids, ARRAY[]::BIGINT[])
                    FROM nodes n
                    LEFT JOIN msg_support ms ON ms.node_id = n.node_id
                    LEFT JOIN cross_support cs ON cs.node_id = n.node_id
                    WHERE n.node_id = ANY(%s)
                    """,
                    (list(node_ids), list(node_ids), list(node_ids)),
                )
                rows = cursor.fetchall()
        return [
            NodeSupportRecord(
                node_id=str(row[0]),
                message_count=int(row[1] or 0),
                channel_count=int(row[2] or 0),
                has_cross_channel_match=bool(row[3]),
                channel_ids=tuple(int(value) for value in (row[4] or ())),
            )
            for row in rows
        ]

    def save_node_relations(self, relations: Sequence[NodeRelation]) -> None:
        if not relations:
            return
        rows = [
            (
                relation.source_node_id,
                relation.target_node_id,
                relation.relation_type,
                relation.score,
                relation.shared_message_count,
                ensure_utc(relation.latest_message_at) if relation.latest_message_at is not None else None,
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
                        shared_message_count,
                        latest_message_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
                        score = EXCLUDED.score,
                        shared_message_count = EXCLUDED.shared_message_count,
                        latest_message_at = EXCLUDED.latest_message_at
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
                    SELECT source_node_id, target_node_id, relation_type, score, shared_message_count, latest_message_at
                    FROM node_relations
                    WHERE source_node_id = %s OR target_node_id = %s
                    ORDER BY score DESC, latest_message_at DESC NULLS LAST
                    """,
                    (node_id, node_id),
                )
                rows = cursor.fetchall()
        return [_node_relation_from_row(row) for row in rows]

    def list_relations_for_nodes(self, node_ids: Sequence[str]) -> list[NodeRelation]:
        if not node_ids:
            return []
        id_list = list(node_ids)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source_node_id, target_node_id, relation_type, score, shared_message_count, latest_message_at
                    FROM node_relations
                    WHERE source_node_id = ANY(%s) AND target_node_id = ANY(%s)
                    ORDER BY score DESC, latest_message_at DESC NULLS LAST
                    """,
                    (id_list, id_list),
                )
                rows = cursor.fetchall()
        return [_node_relation_from_row(row) for row in rows]

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

    def refresh_node_heat_view(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("REFRESH MATERIALIZED VIEW node_heat_view")
            connection.commit()

    def refresh_theme_heat_view(self) -> None:
        self.refresh_node_heat_view()

    def delete_nodes(self, node_ids: Sequence[str]) -> None:
        if not node_ids:
            return
        node_id_list = list(node_ids)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE message_semantics
                    SET primary_event_node_id = NULL
                    WHERE primary_event_node_id = ANY(%s)
                    """,
                    (node_id_list,),
                )
                cursor.execute("DELETE FROM nodes WHERE node_id = ANY(%s)", (node_id_list,))
            connection.commit()

    def clear_semantic_state(self, *, channel_id: int | None = None) -> tuple[list[str], list[str], list[str]]:
        """Clear message-level semantic state (assignments, semantics, relations) for a channel (or all).

        Returns (message_ids_cleared, deleted_theme_ids, deleted_event_ids) where
        message_ids_cleared is a list of "<channel_id>:<message_id>" strings for the
        cleared messages — kept for API compatibility with callers that log/count them.
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                msg_query = "SELECT channel_id, message_id FROM message_nodes"
                msg_params: list[Any] = []
                if channel_id is not None:
                    msg_query += " WHERE channel_id = %s"
                    msg_params.append(channel_id)
                cursor.execute(msg_query, msg_params)
                message_keys = [(int(row[0]), int(row[1])) for row in cursor.fetchall()]
                if not message_keys:
                    return [], [], []

                cursor.execute(
                    """
                    SELECT DISTINCT n.node_id, n.kind
                    FROM message_nodes mn
                    JOIN nodes n ON n.node_id = mn.node_id
                    WHERE (mn.channel_id, mn.message_id) = ANY(%s)
                    """,
                    (message_keys,),
                )
                affected = [(str(row[0]), str(row[1])) for row in cursor.fetchall()]
                affected_node_ids = [node_id for node_id, _kind in affected]

                cursor.execute(
                    "DELETE FROM message_semantics WHERE (channel_id, message_id) = ANY(%s)",
                    (message_keys,),
                )
                cursor.execute(
                    "DELETE FROM message_nodes WHERE (channel_id, message_id) = ANY(%s)",
                    (message_keys,),
                )
                cursor.execute(
                    """
                    UPDATE raw_messages
                    SET is_extracted = FALSE
                    WHERE (channel_id, message_id) = ANY(%s)
                    """,
                    (message_keys,),
                )
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
                        SET article_count = COALESCE(stats.message_count, 0),
                            last_updated = COALESCE(stats.last_message_at, n.last_updated)
                        FROM (
                            SELECT
                                mn.node_id,
                                COUNT(*)::INT AS message_count,
                                MAX(rm.timestamp) AS last_message_at
                            FROM message_nodes mn
                            JOIN raw_messages rm ON rm.channel_id = mn.channel_id AND rm.message_id = mn.message_id
                            WHERE mn.node_id = ANY(%s)
                            GROUP BY mn.node_id
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
                          AND node_id NOT IN (SELECT DISTINCT node_id FROM message_nodes)
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
                        cursor.execute(
                            """
                            UPDATE message_semantics
                            SET primary_event_node_id = NULL
                            WHERE primary_event_node_id = ANY(%s)
                            """,
                            (deleted_node_ids,),
                        )
                        cursor.execute("DELETE FROM nodes WHERE node_id = ANY(%s)", (deleted_node_ids,))
                else:
                    deleted_rows = []
                connection.commit()

        message_ids = [f"{channel_id}:{message_id}" for channel_id, message_id in message_keys]
        theme_ids = [node_id for node_id, kind in deleted_rows if kind == "theme"]
        event_ids = [node_id for node_id, kind in deleted_rows if kind == "event"]
        return message_ids, theme_ids, event_ids

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

    def list_node_heat_rows(self, *, kind: str) -> list[NodeHeatSnapshot]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT node_id, kind, slug, display_name, article_count,
                           heat_1d, heat_3d, heat_5d, heat_7d, heat_14d, heat_31d
                    FROM node_heat_view
                    WHERE kind = %s
                    ORDER BY heat_1d DESC, heat_3d DESC, display_name ASC
                    """,
                    (kind,),
                )
                rows = cursor.fetchall()
        return [_node_heat_from_row(row) for row in rows]

    def list_theme_heat(self, *, phase: str | None = None, limit: int | None = None) -> list[NodeHeatSnapshot]:
        from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS, classify_phase

        rows = self.list_node_heat_rows(kind="theme")
        classified = [
            replace(row, phase=classify_phase(row, DEFAULT_THEME_HEAT_THRESHOLDS))
            for row in rows
        ]
        if phase is not None:
            classified = [r for r in classified if r.phase == phase]
        if limit is not None:
            classified = classified[:limit]
        return classified

    def get_theme_history(self, *, slug: str) -> list[ThemeHistoryPoint]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tds.node_id, n.slug, n.display_name, tds.date, tds.article_count, tds.centroid_drift
                    FROM theme_daily_stats tds
                    JOIN nodes n ON n.node_id = tds.node_id
                    WHERE n.kind = 'theme' AND n.slug = %s AND n.status = 'active'
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

    # ============================================================
    # Message-atomic pipeline methods (Session 2 of refactor).
    # ============================================================

    def upsert_message_semantics(self, records: Sequence[MessageSemanticRecord]) -> None:
        if not records:
            return
        rows = [
            (
                record.channel_id,
                record.message_id,
                self._jsonb(record.extraction_payload),
                record.primary_event_node_id,
                ensure_utc(record.extracted_at) if record.extracted_at is not None else None,
                ensure_utc(record.updated_at) if record.updated_at is not None else None,
            )
            for record in records
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO message_semantics (
                        channel_id,
                        message_id,
                        extraction_payload,
                        primary_event_node_id,
                        extracted_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()))
                    ON CONFLICT (channel_id, message_id) DO UPDATE SET
                        extraction_payload = EXCLUDED.extraction_payload,
                        primary_event_node_id = EXCLUDED.primary_event_node_id,
                        extracted_at = EXCLUDED.extracted_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    rows,
                )
            connection.commit()

    def get_message_semantic_record(
        self, *, channel_id: int, message_id: int
    ) -> MessageSemanticRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT channel_id, message_id, extraction_payload,
                           primary_event_node_id, extracted_at, updated_at
                    FROM message_semantics
                    WHERE channel_id = %s AND message_id = %s
                    """,
                    (channel_id, message_id),
                )
                row = cursor.fetchone()
        return _message_semantic_from_row(row) if row is not None else None

    def save_message_node_assignments(
        self, assignments: Sequence[MessageNodeAssignment]
    ) -> None:
        if not assignments:
            return
        rows = [
            (
                assignment.channel_id,
                assignment.message_id,
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
                    INSERT INTO message_nodes (channel_id, message_id, node_id, confidence, assigned_at, is_primary_event)
                    VALUES (%s, %s, %s, %s, COALESCE(%s, NOW()), %s)
                    ON CONFLICT (channel_id, message_id, node_id) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        is_primary_event = EXCLUDED.is_primary_event
                    """,
                    rows,
                )
            connection.commit()

    def list_message_node_assignments(
        self,
        *,
        message_keys: Sequence[tuple[int, int]] | None = None,
        node_ids: Sequence[str] | None = None,
    ) -> list[MessageNodeAssignment]:
        if message_keys is None and node_ids is None:
            return []
        if message_keys is not None and len(message_keys) == 0:
            return []
        if node_ids is not None and len(node_ids) == 0:
            return []
        query = """
            SELECT channel_id, message_id, node_id, confidence, assigned_at, is_primary_event
            FROM message_nodes
            WHERE 1 = 1
        """
        params: list[Any] = []
        if message_keys:
            query += " AND (channel_id, message_id) = ANY(%s)"
            params.append(list(message_keys))
        if node_ids:
            query += " AND node_id = ANY(%s)"
            params.append(list(node_ids))
        query += " ORDER BY channel_id, message_id, is_primary_event DESC, confidence DESC, node_id"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_message_node_assignment_from_row(row) for row in rows]

    def list_message_keys_for_node(
        self, node_id: str
    ) -> list[tuple[int, int]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT channel_id, message_id
                    FROM message_nodes
                    WHERE node_id = %s
                    ORDER BY channel_id, message_id
                    """,
                    (node_id,),
                )
                rows = cursor.fetchall()
        return [(int(row[0]), int(row[1])) for row in rows]

    def save_cross_channel_message_matches(
        self, matches: Sequence[CrossChannelMessageMatch]
    ) -> None:
        if not matches:
            return
        rows = [
            (
                match.channel_id,
                match.message_id,
                match.matched_channel_id,
                match.matched_message_id,
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
                    INSERT INTO message_matches (
                        channel_id,
                        message_id,
                        matched_channel_id,
                        matched_message_id,
                        similarity_score,
                        timestamp_delta_seconds,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
                    ON CONFLICT (channel_id, message_id, matched_channel_id, matched_message_id) DO UPDATE SET
                        similarity_score = EXCLUDED.similarity_score,
                        timestamp_delta_seconds = EXCLUDED.timestamp_delta_seconds,
                        created_at = EXCLUDED.created_at
                    """,
                    rows,
                )
            connection.commit()

    def list_cross_channel_message_matches(
        self, *, channel_id: int | None = None, message_id: int | None = None
    ) -> list[CrossChannelMessageMatch]:
        query = """
            SELECT channel_id, message_id, matched_channel_id, matched_message_id,
                   similarity_score, timestamp_delta_seconds, created_at
            FROM message_matches
            WHERE 1 = 1
        """
        params: list[Any] = []
        if channel_id is not None:
            query += " AND channel_id = %s"
            params.append(channel_id)
        if message_id is not None:
            query += " AND message_id = %s"
            params.append(message_id)
        query += " ORDER BY similarity_score DESC, created_at DESC"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_cross_channel_message_match_from_row(row) for row in rows]

    def mark_message_embedded(self, *, channel_id: int, message_id: int, version: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE raw_messages
                    SET is_embedded = TRUE
                    WHERE channel_id = %s AND message_id = %s
                    """,
                    (channel_id, message_id),
                )
                cursor.execute(
                    """
                    INSERT INTO message_embeddings (channel_id, message_id, embedding_version)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (channel_id, message_id) DO UPDATE SET
                        embedding_version = EXCLUDED.embedding_version
                    """,
                    (channel_id, message_id, version),
                )
            connection.commit()

    def mark_messages_extracted(self, keys: Sequence[tuple[int, int]]) -> None:
        if not keys:
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE raw_messages
                    SET is_extracted = TRUE
                    WHERE (channel_id, message_id) = ANY(%s)
                    """,
                    (list(keys),),
                )
            connection.commit()

    def list_messages_without_embeddings(
        self, *, channel_id: int | None = None, limit: int | None = None
    ) -> list[RawMessage]:
        query = """
            SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                   text, english_text, source_language, translated_at,
                   media_refs, forwarded_from, reply_to_message_id, raw_json
            FROM raw_messages
            WHERE is_embedded = FALSE
        """
        params: list[Any] = []
        if channel_id is not None:
            query += " AND channel_id = %s"
            params.append(channel_id)
        query += " ORDER BY timestamp ASC, message_id ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def list_messages_without_semantics(
        self, *, channel_id: int | None = None, limit: int | None = None
    ) -> list[RawMessage]:
        query = """
            SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                   text, english_text, source_language, translated_at,
                   media_refs, forwarded_from, reply_to_message_id, raw_json
            FROM raw_messages
            WHERE is_extracted = FALSE
        """
        params: list[Any] = []
        if channel_id is not None:
            query += " AND channel_id = %s"
            params.append(channel_id)
        query += " ORDER BY timestamp ASC, message_id ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def list_message_keys_for_node_on_date(
        self, node_id: str, day: date
    ) -> list[tuple[int, int]]:
        """Return (channel_id, message_id) tuples where this node is assigned AND
        the message's raw_messages.timestamp falls on `day` (UTC date boundary).
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT mn.channel_id, mn.message_id
                    FROM message_nodes mn
                    JOIN raw_messages rm ON rm.channel_id = mn.channel_id AND rm.message_id = mn.message_id
                    WHERE mn.node_id = %s
                      AND rm.timestamp >= %s::date
                      AND rm.timestamp < (%s::date + INTERVAL '1 day')
                    ORDER BY rm.timestamp, mn.channel_id, mn.message_id
                    """,
                    (node_id, day, day),
                )
                rows = cursor.fetchall()
        return [(int(row[0]), int(row[1])) for row in rows]

    def get_raw_message(
        self, *, channel_id: int, message_id: int
    ) -> RawMessage | None:
        """Fetch one raw_messages row by primary key. Return None if absent."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                           text, english_text, source_language, translated_at,
                           media_refs, forwarded_from, reply_to_message_id, raw_json
                    FROM raw_messages
                    WHERE channel_id = %s AND message_id = %s
                    """,
                    (channel_id, message_id),
                )
                row = cursor.fetchone()
        return _raw_message_from_row(row) if row is not None else None

    def list_raw_messages_by_keys(
        self, keys: Sequence[tuple[int, int]]
    ) -> list[RawMessage]:
        """Batch fetch raw_messages rows by (channel_id, message_id) pairs."""
        if not keys:
            return []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT channel_id, message_id, timestamp, sender_id, sender_name,
                           text, english_text, source_language, translated_at,
                           media_refs, forwarded_from, reply_to_message_id, raw_json
                    FROM raw_messages
                    WHERE (channel_id, message_id) = ANY(%s)
                    ORDER BY timestamp ASC, channel_id ASC, message_id ASC
                    """,
                    (list(keys),),
                )
                rows = cursor.fetchall()
        return [_raw_message_from_row(row) for row in rows]

    def get_node_detail(self, *, kind: NodeKind, slug: str) -> NodeDetail | None:
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
                    shared_message_count=relation.shared_message_count,
                    latest_message_at=relation.latest_message_at,
                )
            )

        return NodeDetail(
            node_id=node.node_id,
            kind=node.kind,
            slug=node.slug,
            display_name=node.display_name,
            summary=node.summary,
            article_count=node.article_count,
            parent_event=None,
            child_events=(),
            events=tuple(_sort_related(bucketed["event"])),
            people=tuple(_sort_related(bucketed["person"])),
            nations=tuple(_sort_related(bucketed["nation"])),
            orgs=tuple(_sort_related(bucketed["org"])),
            places=tuple(_sort_related(bucketed["place"])),
            themes=tuple(_sort_related(bucketed["theme"])),
        )


def _sort_related(nodes: list[RelatedNode]) -> list[RelatedNode]:
    return sorted(
        nodes,
        key=lambda item: (
            -item.score,
            -(item.latest_message_at.timestamp() if item.latest_message_at is not None else 0.0),
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
        parent_node_id=str(row[15]) if row[15] is not None else None,
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


def _node_relation_from_row(row: Sequence[Any]) -> NodeRelation:
    return NodeRelation(
        source_node_id=str(row[0]),
        target_node_id=str(row[1]),
        relation_type=str(row[2]),
        score=float(row[3]),
        shared_message_count=int(row[4]),
        latest_message_at=ensure_utc(row[5]) if row[5] is not None else None,
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
        message_count=int(row[4]),
    )


def _node_heat_from_row(row: Sequence[Any]) -> NodeHeatSnapshot:
    return NodeHeatSnapshot(
        node_id=str(row[0]),
        kind=str(row[1]),
        slug=str(row[2]),
        display_name=str(row[3]),
        article_count=int(row[4]),
        heat_1d=float(row[5]),
        heat_3d=float(row[6]),
        heat_5d=float(row[7]),
        heat_7d=float(row[8]),
        heat_14d=float(row[9]),
        heat_31d=float(row[10]),
        phase=None,
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
            child_count=0,
            parent_event=None,
        )


def _message_semantic_from_row(row: Sequence[Any]) -> MessageSemanticRecord:
    return MessageSemanticRecord(
        channel_id=int(row[0]),
        message_id=int(row[1]),
        extraction_payload=dict(row[2] or {}),
        primary_event_node_id=str(row[3]) if row[3] is not None else None,
        extracted_at=ensure_utc(row[4]) if row[4] is not None else None,
        updated_at=ensure_utc(row[5]) if row[5] is not None else None,
    )


def _message_node_assignment_from_row(row: Sequence[Any]) -> MessageNodeAssignment:
    return MessageNodeAssignment(
        channel_id=int(row[0]),
        message_id=int(row[1]),
        node_id=str(row[2]),
        confidence=float(row[3]),
        assigned_at=ensure_utc(row[4]) if row[4] is not None else None,
        is_primary_event=bool(row[5]),
    )


def _cross_channel_message_match_from_row(row: Sequence[Any]) -> CrossChannelMessageMatch:
    return CrossChannelMessageMatch(
        channel_id=int(row[0]),
        message_id=int(row[1]),
        matched_channel_id=int(row[2]),
        matched_message_id=int(row[3]),
        similarity_score=float(row[4]),
        timestamp_delta_seconds=int(row[5]) if row[5] is not None else None,
        created_at=ensure_utc(row[6]) if row[6] is not None else None,
    )


# Backward-compatibility alias
PostgresStoryRepository = PostgresRepository
