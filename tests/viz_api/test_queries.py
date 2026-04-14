from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from telegram_scraper.kg.models import (
    ChannelSummary,
    MessageGroup,
    Node,
    NodeDetail,
    NodeHeatSnapshot,
    NodeListEntry,
    NodeMessage,
    NodeRelation,
    RelatedNode,
)
from telegram_scraper.viz_api.queries import VisualizationQueries


UTC = timezone.utc


class FakeRepository:
    def ensure_schema(self) -> None:
        return None

    def list_candidate_channel_ids(self) -> list[int]:
        return [1]

    def list_node_ids_for_channels(self, *, channel_ids, status="active") -> list[str]:
        del status
        if list(channel_ids) == [1]:
            return ["visible-event", "visible-theme", "visible-person"]
        return []

    def list_node_heat_rows(self, *, kind: str) -> list[NodeHeatSnapshot]:
        rows = {
            "event": [
                NodeHeatSnapshot(
                    node_id="visible-event",
                    kind="event",
                    slug="visible-event",
                    display_name="Visible Event",
                    article_count=10,
                    heat_1d=0.8,
                    heat_3d=0.7,
                    heat_5d=0.6,
                    heat_7d=0.5,
                    heat_14d=0.4,
                    heat_31d=0.3,
                ),
                NodeHeatSnapshot(
                    node_id="hidden-event",
                    kind="event",
                    slug="hidden-event",
                    display_name="Hidden Event",
                    article_count=9,
                    heat_1d=0.7,
                    heat_3d=0.6,
                    heat_5d=0.5,
                    heat_7d=0.4,
                    heat_14d=0.3,
                    heat_31d=0.2,
                ),
            ],
            "theme": [
                NodeHeatSnapshot(
                    node_id="visible-theme",
                    kind="theme",
                    slug="visible-theme",
                    display_name="Visible Theme",
                    article_count=7,
                    heat_1d=0.4,
                    heat_3d=0.3,
                    heat_5d=0.2,
                    heat_7d=0.1,
                    heat_14d=0.1,
                    heat_31d=0.1,
                ),
                NodeHeatSnapshot(
                    node_id="hidden-theme",
                    kind="theme",
                    slug="hidden-theme",
                    display_name="Hidden Theme",
                    article_count=6,
                    heat_1d=0.35,
                    heat_3d=0.25,
                    heat_5d=0.2,
                    heat_7d=0.15,
                    heat_14d=0.1,
                    heat_31d=0.05,
                ),
            ],
        }
        return rows[kind]

    def get_node_by_slug(self, *, kind, slug, status="active") -> Node | None:
        del status
        mapping = {
            ("theme", "visible-theme"): Node(
                node_id="visible-theme",
                kind="theme",
                slug="visible-theme",
                display_name="Visible Theme",
                canonical_name="Visible Theme",
                normalized_name="visible theme",
                status="active",
            ),
            ("theme", "hidden-theme"): Node(
                node_id="hidden-theme",
                kind="theme",
                slug="hidden-theme",
                display_name="Hidden Theme",
                canonical_name="Hidden Theme",
                normalized_name="hidden theme",
                status="active",
            ),
        }
        return mapping.get((kind, slug))


class FakeQueryService:
    def __init__(self, repository: FakeRepository):
        self.repository = repository
        self.snapshot_relation_channel_ids = None

    def channels(self):
        return [
            ChannelSummary(channel_id=1, channel_title="Rebuilt Channel", story_count=3),
            ChannelSummary(channel_id=2, channel_title="Legacy Channel", story_count=4),
        ]

    def list_nodes(self, *, kind, limit=50, include_children=False):
        del kind, limit, include_children
        return [
            NodeListEntry(
                node_id="visible-theme",
                kind="theme",
                slug="visible-theme",
                display_name="Visible Theme",
                summary=None,
                article_count=7,
            ),
            NodeListEntry(
                node_id="hidden-theme",
                kind="theme",
                slug="hidden-theme",
                display_name="Hidden Theme",
                summary=None,
                article_count=6,
            ),
        ]

    def snapshot_relations(self, *, nodes, channel_ids=None):
        self.snapshot_relation_channel_ids = tuple(channel_ids or ())
        if {node.node_id for node in nodes} == {"visible-event"}:
            return [
                NodeRelation(
                    source_node_id="visible-event",
                    target_node_id="visible-theme",
                    relation_type="related",
                    score=2.0,
                    shared_story_count=2,
                )
            ]
        return []

    def theme_history(self, slug: str):
        if slug != "visible-theme":
            return []
        from telegram_scraper.kg.models import ThemeHistoryPoint

        return [
            ThemeHistoryPoint(
                node_id="visible-theme",
                slug="visible-theme",
                display_name="Visible Theme",
                date=datetime(2026, 4, 13, tzinfo=UTC).date(),
                article_count=3,
                centroid_drift=0.1,
            )
        ]

    def node_show_messages(self, *, kind, slug, message_limit=20, message_offset=0):
        del kind, message_limit, message_offset
        if slug == "hidden-event":
            return NodeDetail(
                node_id="hidden-event",
                kind="event",
                slug="hidden-event",
                display_name="Hidden Event",
                summary=None,
                article_count=2,
            )
        if slug != "visible-event":
            return None
        return NodeDetail(
            node_id="visible-event",
            kind="event",
            slug="visible-event",
            display_name="Visible Event",
            summary=None,
            article_count=3,
            people=(
                RelatedNode(
                    node_id="visible-person",
                    kind="person",
                    slug="visible-person",
                    display_name="Visible Person",
                    summary=None,
                    article_count=2,
                    score=1.0,
                    shared_story_count=1,
                ),
                RelatedNode(
                    node_id="hidden-person",
                    kind="person",
                    slug="hidden-person",
                    display_name="Hidden Person",
                    summary=None,
                    article_count=2,
                    score=1.0,
                    shared_story_count=1,
                ),
            ),
            messages=(
                NodeMessage(
                    channel_id=1,
                    message_id=101,
                    channel_title="Rebuilt Channel",
                    timestamp=datetime(2026, 4, 13, 12, 0, tzinfo=UTC),
                    confidence=0.9,
                    text="Visible message",
                ),
                NodeMessage(
                    channel_id=2,
                    message_id=102,
                    channel_title="Legacy Channel",
                    timestamp=datetime(2026, 4, 13, 13, 0, tzinfo=UTC),
                    confidence=0.8,
                    text="Legacy message",
                ),
            ),
        )

    def grouped_messages(self, *, node_id: str, window: str = "1d"):
        if node_id != "visible-event":
            return []
        return [
            MessageGroup(
                group_id="grp-abc123",
                dominant_node_id="visible-event",
                messages=(
                    NodeMessage(
                        channel_id=1,
                        message_id=101,
                        channel_title="Rebuilt Channel",
                        timestamp=datetime(2026, 4, 13, 12, 0, tzinfo=UTC),
                        confidence=0.9,
                        text="Visible message",
                    ),
                    NodeMessage(
                        channel_id=2,
                        message_id=102,
                        channel_title="Legacy Channel",
                        timestamp=datetime(2026, 4, 13, 13, 0, tzinfo=UTC),
                        confidence=0.8,
                        text="Hidden channel message",
                    ),
                ),
                timestamp_start=datetime(2026, 4, 13, 12, 0, tzinfo=UTC),
                timestamp_end=datetime(2026, 4, 13, 13, 0, tzinfo=UTC),
            ),
        ]


class VisualizationQueriesTests(unittest.TestCase):
    def _build_queries(self) -> tuple[VisualizationQueries, FakeQueryService]:
        repository = FakeRepository()
        service = FakeQueryService(repository)
        with patch("telegram_scraper.viz_api.queries.PostgresStoryRepository", return_value=repository), patch(
            "telegram_scraper.viz_api.queries.KGQueryService",
            return_value=service,
        ):
            queries = VisualizationQueries("postgresql://unused/test")
        return queries, service

    def test_filters_channels_and_node_lists_to_rebuilt_channels(self):
        queries, _service = self._build_queries()

        channels = queries.list_channels()
        themes = queries.list_kind_nodes(kind="theme")

        self.assertEqual([channel["channel_id"] for channel in channels["channels"]], [1])
        self.assertEqual([node["node_id"] for node in themes["nodes"]], ["visible-theme"])

    def test_filters_graph_snapshot_and_node_detail_to_visible_set(self):
        queries, service = self._build_queries()

        snapshot = queries.get_graph_snapshot(window="7d", kinds=["event"])
        detail = queries.get_node_detail(kind="event", slug="visible-event")

        self.assertEqual([node["node_id"] for node in snapshot["nodes"]], ["visible-event"])
        self.assertEqual(service.snapshot_relation_channel_ids, (1,))
        # Only message from channel 1 (visible) should remain; channel 2 is not a candidate.
        self.assertEqual([msg["message_id"] for msg in detail["messages"]], [101])
        self.assertEqual([person["node_id"] for person in detail["people"]], ["visible-person"])
        # Legacy stories field must not appear in the payload.
        self.assertNotIn("stories", detail)

    def test_get_grouped_messages_filters_invisible_channels(self):
        queries, _service = self._build_queries()

        groups = queries.get_grouped_messages(node_id="visible-event", window="1d")

        # Group should exist but only contain message from channel 1.
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["group_id"], "grp-abc123")
        self.assertEqual(len(groups[0]["messages"]), 1)
        self.assertEqual(groups[0]["messages"][0]["channel_id"], 1)

    def test_get_grouped_messages_drops_empty_groups(self):
        queries, _service = self._build_queries()

        # node_id that returns no groups from fake service
        groups = queries.get_grouped_messages(node_id="nonexistent-node", window="1d")

        self.assertEqual(groups, [])

    def test_related_node_fields_remapped_to_message_names(self):
        queries, _service = self._build_queries()

        detail = queries.get_node_detail(kind="event", slug="visible-event")

        people = detail["people"]
        self.assertEqual(len(people), 1)
        self.assertIn("shared_message_count", people[0])
        self.assertIn("latest_message_at", people[0])
        self.assertNotIn("shared_story_count", people[0])
        self.assertNotIn("latest_story_at", people[0])

    def test_hidden_theme_history_and_hidden_node_detail_raise_not_found(self):
        queries, _service = self._build_queries()

        with self.assertRaises(KeyError):
            queries.get_theme_history("hidden-theme")

        with self.assertRaises(KeyError):
            queries.get_node_detail(kind="event", slug="hidden-event")


if __name__ == "__main__":
    unittest.main()
