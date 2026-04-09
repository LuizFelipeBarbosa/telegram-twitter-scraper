import unittest
from types import SimpleNamespace

from telegram_scraper.chat_discovery import build_chat_record, filter_chats, resolve_chat
from telegram_scraper.models import ChatType


class ChatDiscoveryTests(unittest.TestCase):
    def test_build_chat_record_for_direct_message(self):
        dialog = SimpleNamespace(
            id=101,
            entity=SimpleNamespace(id=101, first_name="Alice", last_name="Smith", username="alice"),
            name="Alice Smith",
        )

        chat = build_chat_record(dialog)

        self.assertEqual(chat.chat_type, ChatType.DIRECT)
        self.assertEqual(chat.title, "Alice Smith")
        self.assertEqual(chat.username, "alice")
        self.assertEqual(chat.slug, "alice")

    def test_filter_chats_respects_defaults_and_excludes(self):
        direct = build_chat_record(
            SimpleNamespace(
                id=101,
                entity=SimpleNamespace(id=101, first_name="Alice", username="alice"),
                name="Alice",
            )
        )
        group = build_chat_record(
            SimpleNamespace(
                id=202,
                entity=SimpleNamespace(id=202, title="Markets", megagroup=True, username=None),
                name="Markets",
            )
        )

        chats = filter_chats(
            [direct, group],
            chat_types=(ChatType.GROUP, ChatType.CHANNEL, ChatType.SAVED),
            include_chats=(),
            exclude_chats=("markets",),
        )

        self.assertEqual(chats, [])

    def test_resolve_chat_matches_slug_and_username(self):
        chat = build_chat_record(
            SimpleNamespace(
                id=202,
                entity=SimpleNamespace(id=202, title="Markets", megagroup=True, username="markets"),
                name="Markets",
            )
        )

        self.assertEqual(resolve_chat([chat], "markets"), chat)
        self.assertEqual(resolve_chat([chat], "@markets"), chat)


if __name__ == "__main__":
    unittest.main()
