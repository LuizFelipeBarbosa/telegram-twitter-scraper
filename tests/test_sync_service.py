import asyncio
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from telegram_scraper.markdown_writer import MarkdownWriter
from telegram_scraper.models import ChatRecord, ChatType, MediaRecord, MessageRecord
from telegram_scraper.state_store import StateStore
from telegram_scraper.sync_service import SyncService


def load_stored_messages(path: Path, chat_id: int) -> list[dict[str, object]]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT payload FROM messages WHERE chat_id = ? ORDER BY position",
            (chat_id,),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


class FakeTelegramClient:
    def __init__(self, chats, messages_by_chat):
        self._chats = chats
        self._messages_by_chat = messages_by_chat

    async def get_dialogs(self):
        dialogs = []
        for chat in self._chats:
            entity = SimpleNamespace(
                id=chat.chat_id,
                username=chat.username,
                title=chat.title,
                megagroup=chat.chat_type == ChatType.GROUP,
                broadcast=chat.chat_type == ChatType.CHANNEL,
                self=chat.chat_type == ChatType.SAVED,
                first_name=chat.title if chat.chat_type == ChatType.DIRECT else None,
            )
            dialogs.append(SimpleNamespace(id=chat.chat_id, entity=entity, name=chat.title))
        return dialogs

    async def iter_messages(self, chat, *, min_message_id=0, limit=None, reverse=True, offset_id=0):
        messages = list(self._messages_by_chat.get(chat.chat_id, []))
        if min_message_id:
            messages = [message for message in messages if message.message_id > min_message_id]
        if offset_id:
            messages = [message for message in messages if message.message_id < offset_id]
        messages = sorted(messages, key=lambda item: item.message_id, reverse=not reverse)
        if limit is not None:
            messages = messages[:limit]
        for message in messages:
            yield message

    async def get_messages_by_ids(self, chat, ids):
        by_id = {message.message_id: message for message in self._messages_by_chat.get(chat.chat_id, [])}
        return [by_id[message_id] for message_id in ids if message_id in by_id]


class DummySettings:
    since_date = None
    chat_types = (ChatType.GROUP, ChatType.CHANNEL, ChatType.SAVED)
    include_chats = ()
    exclude_chats = ()


def build_message(chat, message_id, text, *, has_media=False, media_files=()):
    return MessageRecord(
        chat=chat,
        message_id=message_id,
        posted_at=datetime(2026, 4, 7, 18, 14, 55 + message_id, tzinfo=timezone.utc),
        edited_at=None,
        sender_id=999,
        sender_name="Alice",
        direction="incoming",
        reply_to_message_id=None,
        has_media=has_media or bool(media_files),
        text=text,
        media_files=media_files,
    )


class SyncServiceTests(unittest.TestCase):
    def test_sync_chat_updates_state_and_deduplicates_new_messages(self):
        with TemporaryDirectory() as temp_dir:
            chat = ChatRecord(
                chat_id=55,
                chat_type=ChatType.GROUP,
                title="Market Research",
                username="marketresearch",
                slug="marketresearch",
            )
            fake_client = FakeTelegramClient(
                chats=[chat],
                messages_by_chat={
                    55: [
                        build_message(chat, 1, "first"),
                        build_message(chat, 2, "second"),
                    ]
                },
            )
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)
            service = SyncService(DummySettings(), fake_client, state_store, writer)

            first = asyncio.run(service.sync_chat(chat))
            second = asyncio.run(service.sync_chat(chat))

            state = json.loads(state_store.state_path(chat).read_text(encoding="utf-8"))
            raw_path = Path(temp_dir) / "telegram_messages.db"
            raw_payload = load_stored_messages(raw_path, 55)

            self.assertEqual(first.exported_messages, 2)
            self.assertEqual(second.exported_messages, 0)
            self.assertEqual(state["last_message_id"], 2)
            self.assertEqual(state["last_status"], "ok")
            self.assertEqual([item["text"] for item in raw_payload], ["first", "second"])

    def test_sync_all_continues_when_one_chat_errors(self):
        with TemporaryDirectory() as temp_dir:
            good_chat = ChatRecord(
                chat_id=1,
                chat_type=ChatType.GROUP,
                title="Good",
                username=None,
                slug="good",
            )
            bad_chat = ChatRecord(
                chat_id=2,
                chat_type=ChatType.GROUP,
                title="Bad",
                username=None,
                slug="bad",
            )

            class SometimesBrokenClient(FakeTelegramClient):
                async def iter_messages(self, chat, *, min_message_id=0, limit=None, reverse=True, offset_id=0):
                    if chat.chat_id == 2:
                        raise RuntimeError("boom")
                    async for message in super().iter_messages(
                        chat,
                        min_message_id=min_message_id,
                        limit=limit,
                        reverse=reverse,
                        offset_id=offset_id,
                    ):
                        yield message

            fake_client = SometimesBrokenClient(
                chats=[good_chat, bad_chat],
                messages_by_chat={1: [build_message(good_chat, 1, "ok")]},
            )
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)
            service = SyncService(DummySettings(), fake_client, state_store, writer)

            results = asyncio.run(service.sync_all())

            self.assertEqual([result.status for result in results], ["ok", "error"])

    def test_initial_sync_respects_since_date_cutoff(self):
        with TemporaryDirectory() as temp_dir:
            chat = ChatRecord(
                chat_id=77,
                chat_type=ChatType.CHANNEL,
                title="Recent Only",
                username="recentonly",
                slug="recentonly",
            )
            old_message = MessageRecord(
                chat=chat,
                message_id=1,
                posted_at=datetime(2025, 12, 31, 23, 59, 0, tzinfo=timezone.utc),
                edited_at=None,
                sender_id=999,
                sender_name="Alice",
                direction="incoming",
                reply_to_message_id=None,
                has_media=False,
                text="old",
            )
            new_message = MessageRecord(
                chat=chat,
                message_id=2,
                posted_at=datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc),
                edited_at=None,
                sender_id=999,
                sender_name="Alice",
                direction="incoming",
                reply_to_message_id=None,
                has_media=False,
                text="new",
            )
            fake_client = FakeTelegramClient(
                chats=[chat],
                messages_by_chat={77: [old_message, new_message]},
            )
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)

            class SinceDateSettings(DummySettings):
                since_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

            service = SyncService(SinceDateSettings(), fake_client, state_store, writer)

            result = asyncio.run(service.sync_chat(chat))

            self.assertEqual(result.exported_messages, 1)
            self.assertTrue((Path(temp_dir) / "telegram_messages.db").exists())
            self.assertFalse((Path(temp_dir) / "channel" / "recentonly_77" / "2025").exists())

    def test_repair_missing_media_updates_markdown_with_image_links(self):
        with TemporaryDirectory() as temp_dir:
            chat = ChatRecord(
                chat_id=88,
                chat_type=ChatType.CHANNEL,
                title="Image Channel",
                username="imagechannel",
                slug="imagechannel",
            )
            cached_message = build_message(chat, 1, "", has_media=True)
            repaired_message = build_message(
                chat,
                1,
                "",
                has_media=True,
                media_files=(
                    MediaRecord(
                        media_type="image",
                        relative_path="media/msg-1.jpg",
                        mime_type="image/jpeg",
                        file_name="msg-1.jpg",
                    ),
                ),
            )

            fake_client = FakeTelegramClient(chats=[chat], messages_by_chat={88: [repaired_message]})
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)
            service = SyncService(DummySettings(), fake_client, state_store, writer)

            writer.write_message(cached_message)
            before = load_stored_messages(Path(temp_dir) / "telegram_messages.db", 88)
            self.assertEqual(before[0]["media_files"], [])

            result = asyncio.run(service.repair_missing_media(chat))

            after = load_stored_messages(Path(temp_dir) / "telegram_messages.db", 88)

            self.assertEqual(result.scanned_messages, 1)
            self.assertEqual(result.repaired_messages, 1)
            self.assertEqual(after[0]["media_files"][0]["relative_path"], "media/msg-1.jpg")


if __name__ == "__main__":
    unittest.main()
