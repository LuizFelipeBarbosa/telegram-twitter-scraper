from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from telegram_scraper.kg.config import KGSettings
from telegram_scraper.viz_api.app import create_app


class FakeVisualizationQueries:
    def __init__(self, database_url: str, **_kwargs: object):
        self.database_url = database_url

    def list_channels(self) -> dict:
        return {
            "channels": [
                {
                    "channel_id": 1,
                    "channel_title": "Signal Watch",
                    "channel_slug": "signal-watch",
                    "channel_username": "signalwatch",
                    "message_count": 4,
                }
            ]
        }

    def list_theme_heat(self, **_: object) -> dict:
        return {
            "window": "7d",
            "total": 1,
            "themes": [
                {
                    "node_id": "theme-1",
                    "slug": "ceasefire-peace-negotiations",
                    "display_name": "Ceasefire Peace Negotiations",
                    "article_count": 12,
                    "heat": 0.33,
                    "phase": "emerging",
                }
            ],
            "topics": [
                {
                    "node_id": "theme-1",
                    "slug": "ceasefire-peace-negotiations",
                    "display_name": "Ceasefire Peace Negotiations",
                    "article_count": 12,
                    "heat": 0.33,
                    "phase": "emerging",
                }
            ],
        }

    def get_graph_snapshot(
        self, *, window="7d", kinds=None, phase=None, limit=300, include_children=False,
    ) -> dict:
        selected_kinds = tuple(kinds or ("event", "theme"))
        ranked_nodes: list[dict] = []

        for kind in selected_kinds:
            thresholds = self.thresholds_for(kind)
            if phase is not None and thresholds is None:
                continue
            heat_result = self.list_node_heat(
                kind=kind, window=window, phase=phase, limit=limit,
            )
            for node in heat_result["nodes"]:
                ranked_nodes.append({
                    "node_id": node["node_id"],
                    "kind": node["kind"],
                    "slug": node["slug"],
                    "display_name": node["display_name"],
                    "summary": None,
                    "article_count": node["article_count"],
                    "score": node["heat"],
                    "heat": node["heat"],
                    "phase": node["phase"],
                    "child_count": 0,
                    "parent_event": None,
                })

        ranked_nodes.sort(key=lambda item: (-float(item["score"]), str(item["display_name"]).lower()))
        ranked_nodes = ranked_nodes[:limit]
        return {"window": window, "nodes": ranked_nodes, "relations": []}

    def thresholds_for(self, kind):
        from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS
        if kind == "theme":
            return DEFAULT_THEME_HEAT_THRESHOLDS
        if kind == "event":
            return DEFAULT_THEME_HEAT_THRESHOLDS  # same defaults for now
        return None

    def list_node_heat(self, *, kind, window, phase=None, limit=50, offset=0):
        from telegram_scraper.kg.heat_phase import PhaseNotSupported
        if phase is not None and self.thresholds_for(kind) is None:
            raise PhaseNotSupported(kind)
        if kind == "theme":
            nodes = [
                {"node_id": "t1", "kind": "theme", "slug": "ceasefire-peace-negotiations",
                 "display_name": "Ceasefire", "article_count": 10, "heat": 0.12, "phase": "emerging"},
            ]
        elif kind == "event":
            nodes = [
                {"node_id": "e1", "kind": "event", "slug": "hormuz-reclosure",
                 "display_name": "Hormuz Reclosure", "article_count": 50, "heat": 0.20, "phase": "emerging"},
                {"node_id": "e2", "kind": "event", "slug": "minor-event",
                 "display_name": "Minor Event", "article_count": 5, "heat": 0.04, "phase": "steady"},
            ]
        else:
            nodes = [
                {"node_id": f"{kind[0]}1", "kind": kind, "slug": f"test-{kind}",
                 "display_name": f"Test {kind}", "article_count": 3, "heat": 0.02, "phase": None},
            ]
        if phase is not None:
            nodes = [n for n in nodes if n.get("phase") == phase]
        return {"window": window, "kind": kind, "total": len(nodes), "nodes": nodes[:limit]}

    def list_kind_nodes(self, *, kind: str, limit: int = 50, include_children: bool = False) -> dict:
        del limit, include_children
        return {
            "kind": kind,
            "nodes": [
                {
                    "node_id": f"{kind}-1",
                    "kind": kind,
                    "slug": f"{kind}-slug",
                    "display_name": f"{kind.title()} Node",
                    "summary": None,
                    "article_count": 2,
                    "last_updated": "2026-04-08T00:00:00Z",
                    "child_count": 0,
                    "parent_event": None,
                }
            ],
        }

    def get_theme_history(self, slug: str) -> dict:
        if slug == "missing":
            raise KeyError(slug)
        return {
            "node_id": "theme-1",
            "slug": slug,
            "display_name": "Ceasefire Peace Negotiations",
            "history": [{"date": "2026-04-08", "article_count": 3, "centroid_drift": 0.14}],
        }

    def get_node_detail(self, *, kind: str, slug: str) -> dict:
        if slug == "missing":
            raise KeyError(slug)
        return {
            "node_id": f"{kind}-1",
            "kind": kind,
            "slug": slug,
            "display_name": "April 8 Hormuz Reclosure",
            "summary": "Node summary",
            "article_count": 3,
            "parent_event": None,
            "child_events": [
                {
                    "node_id": "event-2",
                    "slug": "april-9-follow-up",
                    "display_name": "April 9 Follow-up",
                    "summary": None,
                    "article_count": 1,
                    "child_count": 0,
                    "last_updated": "2026-04-09T00:00:00Z",
                    "event_start_at": "2026-04-08T23:45:00Z",
                    "primary_location": "Tel Aviv",
                    "location_labels": ["Tel Aviv"],
                    "organization_labels": ["Home Front Command"],
                }
            ] if kind == "event" else [],
            "events": [],
            "people": [
                {
                    "node_id": "person-1",
                    "kind": "person",
                    "slug": "donald-trump",
                    "display_name": "Donald Trump",
                    "summary": None,
                    "article_count": 3,
                    "score": 2.0,
                    "shared_message_count": 2,
                    "latest_message_at": "2026-04-08T00:00:00Z",
                }
            ],
            "nations": [],
            "orgs": [],
            "places": [],
            "themes": [],
            "messages": [
                {
                    "channel_id": 1,
                    "message_id": 101,
                    "channel_title": "Signal Watch",
                    "timestamp": "2026-04-08T12:00:00Z",
                    "confidence": 0.9,
                    "text": "Test message text",
                    "english_text": None,
                    "media_refs": [],
                }
            ],
        }

    def get_grouped_messages(self, *, node_id: str, window: str = "1d") -> list:
        return [
            {
                "group_id": "grp-test",
                "dominant_node_id": node_id,
                "messages": [
                    {
                        "channel_id": 1,
                        "message_id": 101,
                        "channel_title": "Signal Watch",
                        "timestamp": "2026-04-08T12:00:00Z",
                        "confidence": 0.9,
                        "text": "Test message text",
                        "english_text": None,
                        "media_refs": [],
                    }
                ],
                "timestamp_start": "2026-04-08T12:00:00Z",
                "timestamp_end": "2026-04-08T13:00:00Z",
            }
        ]


class FakeCache:
    calls: list[tuple[str, int, dict]] = []

    def __init__(self, redis_url: str, *, namespace: str = "viz"):
        self.redis_url = redis_url
        self.namespace = namespace

    def get_or_set(self, name: str, params: dict, *, ttl_seconds: int, loader):
        FakeCache.calls.append((name, ttl_seconds, params))
        return loader()


class VisualizationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeCache.calls = []
        self.settings = KGSettings.from_mapping(
            {
                "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/telegram_kg",
                "REDIS_URL": "redis://localhost:6379/0",
                "PINECONE_API_KEY": "pc-test",
                "OPENAI_API_KEY": "sk-test",
            }
        )

    def _build_client(self) -> TestClient:
        with patch("telegram_scraper.viz_api.app.VisualizationQueries", FakeVisualizationQueries), patch(
            "telegram_scraper.viz_api.app.RedisResponseCache", FakeCache
        ):
            return TestClient(create_app(self.settings))

    def test_channels_snapshot_and_theme_routes_return_expected_payloads(self):
        client = self._build_client()

        channels_response = client.get("/api/channels")
        snapshot_response = client.get("/api/graph/snapshot?window=7d")
        theme_heat_response = client.get("/api/themes/heat?window=7d")

        self.assertEqual(channels_response.status_code, 200)
        self.assertEqual(channels_response.json()["channels"][0]["channel_title"], "Signal Watch")
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(snapshot_response.json()["nodes"][0]["display_name"], "Hormuz Reclosure")
        self.assertEqual(theme_heat_response.status_code, 200)
        self.assertEqual(theme_heat_response.json()["themes"][0]["slug"], "ceasefire-peace-negotiations")
        self.assertIn(("channels", 3600, {}), FakeCache.calls)
        self.assertIn(
            ("graph_snapshot", 900, {"window": "7d", "phase": None, "limit": 300, "kind": [], "include_children": False}),
            FakeCache.calls,
        )

    def test_node_detail_and_theme_alias_routes_return_404_when_missing(self):
        client = self._build_client()

        detail_response = client.get("/api/nodes/event/missing")
        history_response = client.get("/api/themes/missing/history")

        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(detail_response.json()["detail"], "Node not found")
        self.assertEqual(history_response.status_code, 404)
        self.assertEqual(history_response.json()["detail"], "Theme not found")


    def test_nodes_heat_route_returns_schema(self):
        client = self._build_client()
        response = client.get("/api/nodes/heat?kind=theme&window=7d")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kind"], "theme")
        self.assertIn("nodes", body)
        self.assertIn("total", body)
        self.assertEqual(body["window"], "7d")

    def test_nodes_heat_rejects_phase_on_non_phase_kind(self):
        client = self._build_client()
        response = client.get("/api/nodes/heat?kind=person&phase=emerging")
        self.assertEqual(response.status_code, 400)

    def test_graph_snapshot_mixed_kinds_ranking(self):
        client = self._build_client()
        response = client.get("/api/graph/snapshot?window=7d")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()["nodes"]
        scores = [n["score"] for n in nodes]
        self.assertEqual(scores, sorted(scores, reverse=True),
                         "nodes should be sorted by score descending")
        # Under the fix, events and themes interleave by heat
        kinds = [n["kind"] for n in nodes]
        self.assertIn("theme", kinds)
        self.assertIn("event", kinds)

    def test_graph_snapshot_phase_filter_drops_non_phase_kinds(self):
        client = self._build_client()
        response = client.get("/api/graph/snapshot?phase=emerging&kind=event&kind=person")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()["nodes"]
        kinds_present = {n["kind"] for n in nodes}
        self.assertNotIn("person", kinds_present,
                         "non-phase kinds should be dropped when phase filter is applied")

    def test_node_detail_response_has_messages_not_stories(self):
        client = self._build_client()
        response = client.get("/api/nodes/event/hormuz-reclosure")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("messages", body)
        self.assertNotIn("stories", body)
        self.assertEqual(body["messages"][0]["message_id"], 101)

    def test_node_detail_related_nodes_use_message_count_fields(self):
        client = self._build_client()
        response = client.get("/api/nodes/event/hormuz-reclosure")
        self.assertEqual(response.status_code, 200)
        people = response.json()["people"]
        self.assertEqual(len(people), 1)
        self.assertIn("shared_message_count", people[0])
        self.assertIn("latest_message_at", people[0])
        self.assertNotIn("shared_story_count", people[0])
        self.assertNotIn("latest_story_at", people[0])

    def test_topic_messages_alias_returns_messages(self):
        client = self._build_client()
        response = client.get("/api/topics/ceasefire/messages")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("messages", body)
        self.assertNotIn("stories", body)
        self.assertEqual(body["topic_id"], "ceasefire")

    def test_topic_messages_alias_returns_404_when_missing(self):
        client = self._build_client()
        response = client.get("/api/topics/missing/messages")
        self.assertEqual(response.status_code, 404)

    def test_topic_stories_endpoint_no_longer_exists(self):
        client = self._build_client()
        response = client.get("/api/topics/ceasefire/stories")
        self.assertEqual(response.status_code, 404)

    def test_grouped_messages_endpoint_returns_groups(self):
        client = self._build_client()
        response = client.get("/api/nodes/event/hormuz-reclosure/grouped?window=1d")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("groups", body)
        self.assertEqual(len(body["groups"]), 1)
        self.assertEqual(body["groups"][0]["group_id"], "grp-test")
        self.assertEqual(len(body["groups"][0]["messages"]), 1)

    def test_grouped_messages_endpoint_rejects_invalid_window(self):
        client = self._build_client()
        response = client.get("/api/nodes/event/hormuz-reclosure/grouped?window=99d")
        self.assertEqual(response.status_code, 400)

    def test_grouped_messages_endpoint_returns_404_for_missing_node(self):
        client = self._build_client()
        response = client.get("/api/nodes/event/missing/grouped?window=1d")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
