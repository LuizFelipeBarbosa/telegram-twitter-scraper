from __future__ import annotations

import unittest

from telegram_scraper.kg.repository import SCHEMA_STATEMENTS


class RepositorySchemaTests(unittest.TestCase):
    def test_schema_includes_node_tables_and_node_heat_view(self):
        schema = "\n".join(SCHEMA_STATEMENTS)

        self.assertIn("CREATE TABLE IF NOT EXISTS nodes", schema)
        self.assertIn("UNIQUE (kind, slug)", schema)
        self.assertIn("parent_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL", schema)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_nodes_event_parent", schema)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_nodes_kind_canonical_name", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS story_nodes", schema)
        self.assertIn("is_primary_event BOOLEAN NOT NULL DEFAULT FALSE", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS node_relations", schema)
        self.assertIn("shared_story_count INT NOT NULL", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS theme_daily_stats", schema)
        self.assertIn("DROP MATERIALIZED VIEW IF EXISTS theme_heat_view CASCADE", schema)
        self.assertIn("CREATE MATERIALIZED VIEW IF NOT EXISTS node_heat_view", schema)
        self.assertIn("WITH RECURSIVE", schema)
        self.assertIn("node_descendants", schema)
        self.assertIn("idx_node_heat_view_node", schema)
        self.assertIn("idx_node_heat_view_kind", schema)
        self.assertNotIn("THEN 'emerging'", schema)
        self.assertNotIn("THEN 'fading'", schema)
        self.assertIn("parent_node_id", schema)
        self.assertIn("idx_nodes_event_parent", schema)


if __name__ == "__main__":
    unittest.main()
