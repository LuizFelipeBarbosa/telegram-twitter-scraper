from __future__ import annotations

import unittest
from datetime import datetime, timezone

from telegram_scraper.kg.repository import _json_ready


class RepositoryHelpersTests(unittest.TestCase):
    def test_json_ready_converts_nested_datetimes_to_iso_strings(self):
        payload = {
            "outer": {
                "timestamp": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
                "items": [datetime(2026, 4, 10, 8, 30, tzinfo=timezone.utc), b"hello"],
            }
        }

        result = _json_ready(payload)

        self.assertEqual(result["outer"]["timestamp"], "2026-04-11T12:00:00+00:00")
        self.assertEqual(result["outer"]["items"][0], "2026-04-10T08:30:00+00:00")
        self.assertEqual(result["outer"]["items"][1], "hello")


if __name__ == "__main__":
    unittest.main()
