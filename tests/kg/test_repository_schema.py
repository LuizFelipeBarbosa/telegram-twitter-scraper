from __future__ import annotations

import unittest

from telegram_scraper.kg.repository import SCHEMA_STATEMENTS


class RepositorySchemaTests(unittest.TestCase):
    def test_schema_includes_node_tables_and_theme_phase_view(self):
        schema = "\n".join(SCHEMA_STATEMENTS)

        self.assertIn("CREATE TABLE IF NOT EXISTS nodes", schema)
        self.assertIn("UNIQUE (kind, slug)", schema)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_nodes_kind_canonical_name", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS story_nodes", schema)
        self.assertIn("is_primary_event BOOLEAN NOT NULL DEFAULT FALSE", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS node_relations", schema)
        self.assertIn("shared_story_count INT NOT NULL", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS theme_daily_stats", schema)
        self.assertIn("CREATE MATERIALIZED VIEW IF NOT EXISTS theme_heat_view", schema)
        self.assertIn("WHERE n.kind = 'theme' AND n.status = 'active'", schema)
        self.assertIn("WHEN base.heat_1d > 0.10 AND base.heat_31d < 0.02 THEN 'emerging'", schema)
        self.assertIn("WHEN base.heat_31d > 0.05 AND base.heat_1d < 0.01 THEN 'fading'", schema)
        self.assertIn("WHEN base.heat_3d > 0.10 AND base.heat_7d < 0.02 THEN 'flash_event'", schema)


if __name__ == "__main__":
    unittest.main()
