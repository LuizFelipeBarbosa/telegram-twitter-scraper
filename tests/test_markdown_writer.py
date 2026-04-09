from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_scraper.markdown_writer import MarkdownWriter
from telegram_scraper.models import ChatRecord, ChatType, MediaRecord, MessageRecord
from telegram_scraper.state_store import StateStore


def build_chat() -> ChatRecord:
    return ChatRecord(
        chat_id=55,
        chat_type=ChatType.GROUP,
        title="Market Research",
        username="marketresearch",
        slug="marketresearch",
    )


def build_message(
    message_id: int,
    *,
    year: int = 2026,
    month: int = 4,
    day: int = 7,
    hour: int,
    minute: int,
    second: int,
    text: str,
    reply_to_message_id: int | None = None,
    has_media: bool = False,
    media_files: tuple[MediaRecord, ...] = (),
) -> MessageRecord:
    chat = build_chat()
    return MessageRecord(
        chat=chat,
        message_id=message_id,
        posted_at=datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc),
        edited_at=None,
        sender_id=999,
        sender_name="Alice Smith",
        direction="incoming",
        reply_to_message_id=reply_to_message_id,
        has_media=has_media or bool(media_files),
        text=text,
        media_files=media_files,
    )


class MarkdownWriterTests(unittest.TestCase):
    def test_markdown_writer_creates_chat_level_raw_cache(self):
        with TemporaryDirectory() as temp_dir:
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)
            message = build_message(1043, hour=18, minute=14, second=55, text="Telegram message text goes here.")

            path = writer.write_message(message)
            payload = json.loads(path.read_text(encoding="utf-8"))

            expected = Path(temp_dir) / "group" / "marketresearch_55" / "_messages.json"
            self.assertEqual(path, expected)
            self.assertEqual(payload["message_count"], 1)
            self.assertEqual(payload["chat_id"], 55)
            self.assertEqual(payload["messages"][0]["message_id"], 1043)
            self.assertFalse((expected.parent / "2026").exists())

    def test_markdown_writer_merges_new_messages_into_existing_chat_cache(self):
        with TemporaryDirectory() as temp_dir:
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)

            writer.write_message(build_message(2, hour=18, minute=1, second=0, text="second"))
            writer.write_message(build_message(1, hour=18, minute=0, second=0, text="first"))
            writer.write_message(build_message(2, hour=18, minute=2, second=0, text="second updated"))

            payload = json.loads(
                (Path(temp_dir) / "group" / "marketresearch_55" / "_messages.json").read_text(encoding="utf-8")
            )

            self.assertEqual(payload["message_count"], 2)
            self.assertEqual([item["message_id"] for item in payload["messages"]], [2, 1])
            self.assertEqual([item["text"] for item in payload["messages"]], ["second updated", "first"])

    def test_markdown_writer_ignores_legacy_day_cache_when_root_cache_absent(self):
        with TemporaryDirectory() as temp_dir:
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)
            chat_dir = Path(temp_dir) / "group" / "marketresearch_55"
            day_dir = chat_dir / "2026" / "2026-04" / "2026-04-07"
            day_dir.mkdir(parents=True, exist_ok=True)
            legacy_message = build_message(1, hour=18, minute=0, second=0, text="legacy")
            day_dir.joinpath("_messages.json").write_text(
                json.dumps(
                    {
                        "chat_id": 55,
                        "chat_slug": "marketresearch",
                        "chat_type": "group",
                        "date": "2026-04-07",
                        "message_count": 1,
                        "messages": [
                            {
                                "message_id": legacy_message.message_id,
                                "posted_at": "2026-04-07T18:00:00Z",
                                "edited_at": None,
                                "sender_id": legacy_message.sender_id,
                                "sender_name": legacy_message.sender_name,
                                "direction": legacy_message.direction,
                                "reply_to_message_id": None,
                                "has_media": False,
                                "text": legacy_message.text,
                                "media_files": [],
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            writer.write_message(build_message(2, hour=18, minute=5, second=0, text="fresh"))
            payload = json.loads((chat_dir / "_messages.json").read_text(encoding="utf-8"))

            self.assertEqual(payload["message_count"], 1)
            self.assertEqual([item["message_id"] for item in payload["messages"]], [2])

    def test_markdown_writer_preserves_media_metadata_in_root_cache(self):
        with TemporaryDirectory() as temp_dir:
            state_store = StateStore(Path(temp_dir))
            writer = MarkdownWriter(state_store)
            message = build_message(
                1043,
                hour=18,
                minute=14,
                second=55,
                text="",
                media_files=(
                    MediaRecord(
                        media_type="image",
                        relative_path="media/msg-1043.jpg",
                        mime_type="image/jpeg",
                        file_name="msg-1043.jpg",
                    ),
                ),
            )

            path = writer.write_message(message)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertTrue(payload["messages"][0]["has_media"])
            self.assertEqual(payload["messages"][0]["media_files"][0]["relative_path"], "media/msg-1043.jpg")


if __name__ == "__main__":
    unittest.main()
