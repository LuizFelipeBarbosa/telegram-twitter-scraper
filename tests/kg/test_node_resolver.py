"""Tests for NodeResolver.resolve_message (per-message resolution API).

These tests exercise the new resolve_message() method and the supporting
register_message() helper on _NodeSupportState.  The existing resolve()
(story-based) method is left untouched and is not re-tested here.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from telegram_scraper.kg.config import KGSettings
from telegram_scraper.kg.models import (
    ExtractedSemanticNode,
    Node,
    NodeKind,
    NodeSupportRecord,
)
from telegram_scraper.kg.node_resolver import NodeResolver, _NodeSupportState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc

_MINIMAL_SETTINGS_MAP = {
    "DATABASE_URL": "postgresql://localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "PINECONE_API_KEY": "pc-test",
    "OPENAI_API_KEY": "sk-test",
    "KG_THEME_MATCH_THRESHOLD": "0.78",
    "KG_EVENT_MATCH_THRESHOLD": "0.80",
    "KG_EVENT_MATCH_WINDOW_DAYS": "14",
}


def _settings() -> KGSettings:
    return KGSettings.from_mapping(_MINIMAL_SETTINGS_MAP)


def _utc_now() -> datetime:
    return datetime(2026, 4, 13, 12, 0, 0, tzinfo=_UTC)


def _ts(hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 4, 13, hour, minute, 0, tzinfo=_UTC)


def _empty_node_cache() -> dict[NodeKind, dict[str, Node]]:
    return {k: {} for k in ("event", "person", "nation", "org", "place", "theme")}


def _make_resolver(
    node_cache: dict[NodeKind, dict[str, Node]] | None = None,
    support_records: dict[str, NodeSupportRecord] | None = None,
    theme_centroids: dict[str, list[float]] | None = None,
    event_centroids: dict[str, list[float]] | None = None,
) -> NodeResolver:
    return NodeResolver(
        settings=_settings(),
        node_cache=node_cache if node_cache is not None else _empty_node_cache(),
        support_records=support_records or {},
        theme_centroids=theme_centroids or {},
        event_centroids=event_centroids or {},
        pending_theme_centroids={},
        pending_event_centroids={},
        utc_now=_utc_now,
    )


def _candidate(name: str, aliases: tuple[str, ...] = (), summary: str | None = None) -> ExtractedSemanticNode:
    return ExtractedSemanticNode(name=name, summary=summary, aliases=aliases)


def _make_node(
    node_id: str,
    kind: NodeKind,
    name: str,
    aliases: tuple[str, ...] = (),
    article_count: int = 0,
    status: str = "active",
) -> Node:
    from telegram_scraper.kg.node_resolver import _normalize_name, _slugify
    return Node(
        node_id=node_id,
        kind=kind,
        slug=_slugify(name),
        display_name=name,
        canonical_name=name,
        normalized_name=_normalize_name(name),
        aliases=aliases,
        article_count=article_count,
        status=status,
        created_at=_utc_now(),
        last_updated=_utc_now(),
    )


# ---------------------------------------------------------------------------
# Test 1: resolve_message creates a new node when no match exists
# ---------------------------------------------------------------------------

class TestResolveMessageCreatesNewNode(unittest.TestCase):
    def test_creates_node_for_unknown_entity(self) -> None:
        resolver = _make_resolver()
        result = resolver.resolve_message(
            kind="person",
            candidate=_candidate("Jane Doe"),
            embedding=[],
            channel_id=1,
            message_id=100,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertTrue(result.created)
        self.assertEqual(result.node.display_name, "Jane Doe")
        self.assertEqual(result.node.kind, "person")
        self.assertAlmostEqual(result.confidence, 1.0)
        # article_count should be 1 after the first message
        self.assertEqual(result.node.article_count, 1)

    def test_new_person_node_is_immediately_active(self) -> None:
        """Persons are always active (not candidate) regardless of activate_immediately."""
        resolver = _make_resolver()
        result = resolver.resolve_message(
            kind="person",
            candidate=_candidate("Jane Doe"),
            embedding=[],
            channel_id=1,
            message_id=100,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertEqual(result.node.status, "active")

    def test_new_theme_node_is_candidate_when_not_forced(self) -> None:
        resolver = _make_resolver()
        result = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Global Trade"),
            embedding=[0.1, 0.2, 0.3],
            channel_id=1,
            message_id=200,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertTrue(result.created)
        self.assertEqual(result.node.status, "candidate")

    def test_new_theme_node_is_active_when_forced(self) -> None:
        resolver = _make_resolver()
        result = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Global Trade"),
            embedding=[0.1, 0.2, 0.3],
            channel_id=1,
            message_id=200,
            message_timestamp=_ts(),
            activate_immediately=True,
        )
        self.assertTrue(result.created)
        self.assertEqual(result.node.status, "active")


# ---------------------------------------------------------------------------
# Test 2: resolve_message matches an existing node by exact normalized name
# ---------------------------------------------------------------------------

class TestResolveMessageExactNameMatch(unittest.TestCase):
    def test_matches_existing_node_by_name(self) -> None:
        existing = _make_node("node-1", "person", "Joe Biden")
        cache = _empty_node_cache()
        cache["person"]["node-1"] = existing

        resolver = _make_resolver(node_cache=cache)
        result = resolver.resolve_message(
            kind="person",
            candidate=_candidate("Joe Biden"),
            embedding=[],
            channel_id=1,
            message_id=50,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertFalse(result.created)
        self.assertEqual(result.node.node_id, "node-1")
        self.assertAlmostEqual(result.confidence, 0.99)

    def test_matches_case_insensitively(self) -> None:
        existing = _make_node("node-2", "person", "Joe Biden")
        cache = _empty_node_cache()
        cache["person"]["node-2"] = existing

        resolver = _make_resolver(node_cache=cache)
        result = resolver.resolve_message(
            kind="person",
            candidate=_candidate("JOE BIDEN"),
            embedding=[],
            channel_id=1,
            message_id=51,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertFalse(result.created)
        self.assertEqual(result.node.node_id, "node-2")


# ---------------------------------------------------------------------------
# Test 3: resolve_message matches an existing node by alias
# ---------------------------------------------------------------------------

class TestResolveMessageAliasMatch(unittest.TestCase):
    def test_matches_existing_node_by_alias(self) -> None:
        existing = _make_node("node-3", "person", "Joseph Biden", aliases=("Joe Biden", "POTUS"))
        cache = _empty_node_cache()
        cache["person"]["node-3"] = existing

        resolver = _make_resolver(node_cache=cache)
        result = resolver.resolve_message(
            kind="person",
            candidate=_candidate("Joe Biden"),
            embedding=[],
            channel_id=1,
            message_id=60,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertFalse(result.created)
        self.assertEqual(result.node.node_id, "node-3")
        # alias match → confidence 0.95
        self.assertAlmostEqual(result.confidence, 0.95)


# ---------------------------------------------------------------------------
# Test 4: Two different messages bump article_count and promote to active
# ---------------------------------------------------------------------------

class TestResolveMessagePromotion(unittest.TestCase):
    def test_two_distinct_messages_promote_candidate_theme(self) -> None:
        resolver = _make_resolver()

        # First message — creates node as candidate
        r1 = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Climate Change"),
            embedding=[0.5, 0.5, 0.0],
            channel_id=10,
            message_id=1,
            message_timestamp=_ts(hour=10),
            activate_immediately=False,
        )
        self.assertTrue(r1.created)
        self.assertEqual(r1.node.status, "candidate")
        self.assertEqual(r1.node.article_count, 1)

        # Second message (different id) — should bump count and promote
        r2 = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Climate Change"),
            embedding=[0.5, 0.5, 0.0],
            channel_id=10,
            message_id=2,
            message_timestamp=_ts(hour=11),
            activate_immediately=False,
        )
        self.assertFalse(r2.created)
        self.assertEqual(r2.node.node_id, r1.node.node_id)
        self.assertEqual(r2.node.article_count, 2)
        self.assertEqual(r2.node.status, "active")


# ---------------------------------------------------------------------------
# Test 5: Same (channel_id, message_id) is idempotent — article_count stays 1
# ---------------------------------------------------------------------------

class TestResolveMessageIdempotent(unittest.TestCase):
    def test_same_message_key_does_not_bump_count(self) -> None:
        resolver = _make_resolver()

        r1 = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Inflation"),
            embedding=[0.3, 0.7, 0.0],
            channel_id=5,
            message_id=99,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertEqual(r1.node.article_count, 1)

        # Same channel_id + message_id → must not bump
        r2 = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Inflation"),
            embedding=[0.3, 0.7, 0.0],
            channel_id=5,
            message_id=99,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertFalse(r2.created)
        self.assertEqual(r2.node.article_count, 1, "article_count must stay 1 for duplicate message_key")

    def test_register_message_directly_is_idempotent(self) -> None:
        state = _NodeSupportState(message_count=0)
        key = (7, 42)
        first = state.register_message(message_key=key, channel_id=7)
        second = state.register_message(message_key=key, channel_id=7)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(state.message_count, 1)


# ---------------------------------------------------------------------------
# Test 6: Messages from different channels update channel_ids correctly
# ---------------------------------------------------------------------------

class TestResolveMessageCrossChannelTracking(unittest.TestCase):
    def test_two_channels_add_distinct_channel_ids(self) -> None:
        resolver = _make_resolver()

        resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Energy Crisis"),
            embedding=[0.6, 0.4, 0.0],
            channel_id=100,
            message_id=1,
            message_timestamp=_ts(hour=9),
            activate_immediately=False,
        )

        r2 = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Energy Crisis"),
            embedding=[0.6, 0.4, 0.0],
            channel_id=200,
            message_id=2,
            message_timestamp=_ts(hour=10),
            activate_immediately=False,
        )

        support = resolver.node_support[r2.node.node_id]
        self.assertIn(100, support.channel_ids)
        self.assertIn(200, support.channel_ids)
        self.assertEqual(support.channel_count, 2)
        # article_count should reflect two distinct messages
        self.assertEqual(r2.node.article_count, 2)

    def test_register_message_updates_channel_ids(self) -> None:
        state = _NodeSupportState(message_count=0)
        state.register_message(message_key=(10, 1), channel_id=10)
        state.register_message(message_key=(20, 2), channel_id=20)
        self.assertEqual(state.channel_ids, {10, 20})
        self.assertEqual(state.message_count, 2)


# ---------------------------------------------------------------------------
# Test 7: Themes use embedding-based centroid matching
# ---------------------------------------------------------------------------

class TestResolveMessageEmbeddingMatch(unittest.TestCase):
    def test_theme_matched_via_centroid_similarity(self) -> None:
        """A theme node with a stored centroid that is very close to the query
        embedding should be returned as an existing match, not a new node."""
        existing = _make_node("theme-99", "theme", "Hormuz Strait Tensions")
        cache = _empty_node_cache()
        cache["theme"]["theme-99"] = existing

        # Centroid stored for the existing node
        theme_centroids = {"theme-99": [1.0, 0.0, 0.0]}

        resolver = _make_resolver(node_cache=cache, theme_centroids=theme_centroids)

        # Query embedding is very close to the stored centroid (cosine ~ 1.0)
        result = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Strait of Hormuz Crisis"),
            embedding=[0.99, 0.01, 0.0],
            channel_id=1,
            message_id=500,
            message_timestamp=_ts(),
            activate_immediately=False,
        )

        # Should match existing, not create a new node
        self.assertFalse(result.created, "Should match existing node via centroid similarity")
        self.assertEqual(result.node.node_id, "theme-99")
        # Confidence should be the cosine similarity (above threshold 0.78)
        self.assertGreaterEqual(result.confidence, 0.78)

    def test_theme_not_matched_when_below_threshold(self) -> None:
        """A theme node whose centroid is far from the query should NOT match."""
        existing = _make_node("theme-77", "theme", "Unrelated Topic")
        cache = _empty_node_cache()
        cache["theme"]["theme-77"] = existing

        # Centroid orthogonal to the query
        theme_centroids = {"theme-77": [0.0, 1.0, 0.0]}

        resolver = _make_resolver(node_cache=cache, theme_centroids=theme_centroids)

        result = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Completely Different Theme"),
            embedding=[1.0, 0.0, 0.0],
            channel_id=1,
            message_id=600,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertTrue(result.created, "Should create new node when centroid similarity is below threshold")


# ---------------------------------------------------------------------------
# Test 8: register_cross_channel_support works for message-based matches
# ---------------------------------------------------------------------------

class TestRegisterCrossChannelSupportMessageBased(unittest.TestCase):
    def test_cross_channel_support_promotes_candidate_theme(self) -> None:
        """register_cross_channel_support should promote a candidate even when
        it was populated via resolve_message rather than resolve."""
        resolver = _make_resolver()

        # Create a candidate theme via a single message (not yet promoted)
        r1 = resolver.resolve_message(
            kind="theme",
            candidate=_candidate("Nuclear Proliferation"),
            embedding=[0.2, 0.8, 0.0],
            channel_id=50,
            message_id=1,
            message_timestamp=_ts(),
            activate_immediately=False,
        )
        self.assertEqual(r1.node.status, "candidate")

        # Simulate a cross-channel match flagged by the caller
        promoted = resolver.register_cross_channel_support(node_ids=[r1.node.node_id])
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0].status, "active")


if __name__ == "__main__":
    unittest.main()
