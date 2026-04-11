from __future__ import annotations

import unittest

from telegram_scraper.viz_api.queries import WINDOW_FIELD_MAP


class VisualizationQueryHelpersTests(unittest.TestCase):
    def test_window_field_map_exposes_theme_heat_columns(self):
        self.assertEqual(WINDOW_FIELD_MAP["1d"], "heat_1d")
        self.assertEqual(WINDOW_FIELD_MAP["7d"], "heat_7d")
        self.assertEqual(WINDOW_FIELD_MAP["31d"], "heat_31d")


if __name__ == "__main__":
    unittest.main()
