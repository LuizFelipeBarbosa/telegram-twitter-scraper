from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from telegram_scraper.kg.config import KGSettings
from telegram_scraper.viz_api.app import create_app


class FakeVisualizationQueries:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def list_channels(self) -> dict:
        return {
            "channels": [
                {
                    "channel_id": 1,
                    "channel_title": "Signal Watch",
                    "channel_slug": "signal-watch",
                    "channel_username": "signalwatch",
                    "story_count": 4,
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

    def get_graph_snapshot(self, **_: object) -> dict:
        return {
            "window": "7d",
            "nodes": [
                {
                    "node_id": "event-1",
                    "kind": "event",
                    "slug": "april-8-hormuz-reclosure",
                    "display_name": "April 8 Hormuz Reclosure",
                    "summary": None,
                    "article_count": 3,
                    "score": 3.0,
                    "heat": None,
                    "phase": None,
                    "child_count": 2,
                    "parent_event": None,
                }
            ],
            "relations": [
                {
                    "source": "event-1",
                    "target": "theme-1",
                    "type": "related",
                    "score": 2.5,
                }
            ],
        }

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
                    "shared_story_count": 2,
                    "latest_story_at": "2026-04-08T00:00:00Z",
                }
            ],
            "nations": [],
            "orgs": [],
            "places": [],
            "themes": [],
            "stories": [],
        }


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
        self.assertEqual(snapshot_response.json()["nodes"][0]["display_name"], "April 8 Hormuz Reclosure")
        self.assertEqual(snapshot_response.json()["nodes"][0]["child_count"], 2)
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


if __name__ == "__main__":
    unittest.main()
