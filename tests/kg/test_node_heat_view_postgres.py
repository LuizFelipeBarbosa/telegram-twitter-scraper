# tests/kg/test_node_heat_view_postgres.py
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import pytest

if not os.environ.get("KG_PG_INTEGRATION"):
    pytest.skip(
        "set KG_PG_INTEGRATION=1 and point DATABASE_URL at a disposable db",
        allow_module_level=True,
    )

from telegram_scraper.kg.repository import PostgresStoryRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class NodeHeatViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/telegram_kg")
        cls.repo = PostgresStoryRepository(url)
        cls.repo.ensure_schema()

    def setUp(self):
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM message_nodes")
                cur.execute("DELETE FROM raw_messages")
                cur.execute("DELETE FROM nodes")
            conn.commit()

    def _insert_node(self, *, node_id, kind, slug, status="active", parent_node_id=None):
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO nodes (node_id, kind, slug, display_name, canonical_name,
                       normalized_name, summary, aliases, status, label_source, article_count,
                       parent_node_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (node_id, kind, slug, slug, slug, slug, None, [], status, "test", 0, parent_node_id),
                )
            conn.commit()

    def _insert_message(self, *, channel_id, message_id, minutes_ago=0):
        ts = _now() - timedelta(minutes=minutes_ago)
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO raw_messages (channel_id, message_id, timestamp,
                       sender_id, sender_name, text, media_refs, raw_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (channel_id, message_id, ts, None, None, "text", "[]", "{}"),
                )
            conn.commit()

    def _assign(self, channel_id, message_id, node_id):
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO message_nodes (channel_id, message_id, node_id, confidence, is_primary_event)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (channel_id, message_id, node_id, 1.0, False),
                )
            conn.commit()

    def _refresh(self):
        self.repo.refresh_node_heat_view()

    def test_leaf_event_heat_equals_direct_assignment(self):
        event_id = _uuid()
        channel_id = 1
        message_id = 1001
        self._insert_node(node_id=event_id, kind="event", slug="leaf")
        self._insert_message(channel_id=channel_id, message_id=message_id, minutes_ago=10)
        self._assign(channel_id, message_id, event_id)
        self._refresh()
        rows = self.repo.list_node_heat_rows(kind="event")
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0].heat_1d, 0)

    def test_parent_event_rolls_up_child(self):
        parent_id = _uuid()
        child_id = _uuid()
        channel_id = 1
        message_id = 1002
        self._insert_node(node_id=parent_id, kind="event", slug="parent")
        self._insert_node(node_id=child_id, kind="event", slug="child", parent_node_id=parent_id)
        self._insert_message(channel_id=channel_id, message_id=message_id, minutes_ago=10)
        self._assign(channel_id, message_id, child_id)
        self._refresh()
        rows = {r.slug: r for r in self.repo.list_node_heat_rows(kind="event")}
        self.assertGreater(rows["parent"].heat_1d, 0, "parent should have heat from child's message")
        self.assertEqual(rows["parent"].heat_1d, rows["child"].heat_1d)

    def test_no_double_count(self):
        parent_id = _uuid()
        child_id = _uuid()
        channel_id = 1
        message_id = 1003
        self._insert_node(node_id=parent_id, kind="event", slug="parent")
        self._insert_node(node_id=child_id, kind="event", slug="child", parent_node_id=parent_id)
        self._insert_message(channel_id=channel_id, message_id=message_id, minutes_ago=10)
        self._assign(channel_id, message_id, parent_id)
        self._assign(channel_id, message_id, child_id)
        self._refresh()
        rows = {r.slug: r for r in self.repo.list_node_heat_rows(kind="event")}
        self.assertEqual(rows["parent"].heat_1d, rows["child"].heat_1d,
                         "same message on parent+child should not double-count")

    def test_inactive_descendant_excluded(self):
        parent_id = _uuid()
        child_id = _uuid()
        channel_id = 1
        message_id = 1004
        self._insert_node(node_id=parent_id, kind="event", slug="parent")
        self._insert_node(node_id=child_id, kind="event", slug="child",
                          parent_node_id=parent_id, status="inactive")
        self._insert_message(channel_id=channel_id, message_id=message_id, minutes_ago=10)
        self._assign(channel_id, message_id, child_id)
        self._refresh()
        rows = self.repo.list_node_heat_rows(kind="event")
        parent_rows = [r for r in rows if r.slug == "parent"]
        self.assertEqual(len(parent_rows), 1)
        self.assertEqual(parent_rows[0].heat_1d, 0.0,
                         "inactive child's messages should not roll up")

    def test_theme_has_no_rollup(self):
        theme_id = _uuid()
        channel_id = 1
        message_id = 1005
        self._insert_node(node_id=theme_id, kind="theme", slug="test-theme")
        self._insert_message(channel_id=channel_id, message_id=message_id, minutes_ago=10)
        self._assign(channel_id, message_id, theme_id)
        self._refresh()
        rows = self.repo.list_node_heat_rows(kind="theme")
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0].heat_1d, 0)


if __name__ == "__main__":
    unittest.main()
