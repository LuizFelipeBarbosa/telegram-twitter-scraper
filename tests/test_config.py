import unittest
from pathlib import Path

from telegram_scraper.config import Settings
from telegram_scraper.models import ChatType


class SettingsTests(unittest.TestCase):
    def test_settings_defaults_from_mapping(self):
        settings = Settings.from_mapping(
            {
                "TG_API_ID": "123",
                "TG_API_HASH": "hash",
                "TG_PHONE": "+15555555555",
            }
        )

        self.assertEqual(settings.api_id, 123)
        self.assertEqual(settings.api_hash, "hash")
        self.assertEqual(settings.phone, "+15555555555")
        self.assertEqual(settings.output_root, Path("/Volumes/T7/theVault/raw/telegram"))
        self.assertIsNone(settings.since_date)
        self.assertEqual(settings.chat_types, (ChatType.GROUP, ChatType.CHANNEL, ChatType.SAVED))

    def test_settings_parse_filters_and_paths(self):
        settings = Settings.from_mapping(
            {
                "TG_API_ID": "123",
                "TG_API_HASH": "hash",
                "TG_PHONE": "+15555555555",
                "SESSION_PATH": "sessions/custom",
                "OUTPUT_ROOT": "/tmp/output",
                "SINCE_DATE": "2026-01-01T00:00:00Z",
                "CHAT_TYPES": "direct,group",
                "INCLUDE_CHATS": "alpha,@beta,123",
                "EXCLUDE_CHATS": "gamma",
            }
        )

        self.assertEqual(settings.session_path, Path("sessions/custom"))
        self.assertEqual(settings.output_root, Path("/tmp/output"))
        self.assertEqual(settings.since_date.isoformat(), "2026-01-01T00:00:00+00:00")
        self.assertEqual(settings.chat_types, (ChatType.DIRECT, ChatType.GROUP))
        self.assertEqual(settings.include_chats, ("alpha", "@beta", "123"))
        self.assertEqual(settings.exclude_chats, ("gamma",))


if __name__ == "__main__":
    unittest.main()
