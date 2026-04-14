from __future__ import annotations

import unittest
from datetime import datetime, timezone

from telegram_scraper.models import ChatRecord, ChatType, MediaRecord, MessageRecord
from telegram_scraper.notebook_pipeline import (
    NotebookSettings,
    normalize_message_record,
    preferred_message_text,
    safe_message_text,
)


def build_chat() -> ChatRecord:
    return ChatRecord(
        chat_id=55,
        chat_type=ChatType.CHANNEL,
        title="Notebook Channel",
        username="notebookchannel",
        slug="notebookchannel",
    )


def build_message(*, text: str) -> MessageRecord:
    chat = build_chat()
    return MessageRecord(
        chat=chat,
        message_id=101,
        posted_at=datetime(2026, 4, 7, 18, 0, 0, tzinfo=timezone.utc),
        edited_at=None,
        sender_id=999,
        sender_name="Alice Smith",
        direction="incoming",
        reply_to_message_id=100,
        has_media=True,
        text=text,
        media_files=(
            MediaRecord(
                media_type="image",
                relative_path="media/msg-101.jpg",
                mime_type="image/jpeg",
                file_name="msg-101.jpg",
            ),
        ),
    )


class NotebookSettingsTests(unittest.TestCase):
    def test_settings_defaults_from_mapping(self):
        settings = NotebookSettings.from_mapping({"OPENAI_API_KEY": "test-key"})

        self.assertEqual(settings.openai_api_key, "test-key")
        self.assertEqual(settings.embedding_model, "text-embedding-3-small")
        self.assertEqual(settings.translation_model, "gpt-5-mini")
        self.assertEqual(settings.semantic_max_chars, 12000)
        self.assertEqual(settings.semantic_batch_size, 8)


class NotebookPipelineTests(unittest.TestCase):
    def test_preferred_message_text_prefers_english_text(self):
        raw_message = normalize_message_record(build_message(text="Original text"))
        translated = raw_message.__class__(
            **{
                **raw_message.__dict__,
                "english_text": "Translated text",
            }
        )

        self.assertEqual(preferred_message_text(translated), "Translated text")

    def test_safe_message_text_truncates_long_messages(self):
        text = "a" * 20 + "b" * 20

        trimmed = safe_message_text(text, max_chars=21)

        self.assertLessEqual(len(trimmed), 21)
        self.assertIn("\n", trimmed)

    def test_normalize_message_record_maps_media_and_forwarded_from(self):
        message = build_message(text="hello")

        normalized = normalize_message_record(
            message,
            raw_json={
                "fwd_from": {
                    "from_id": {
                        "channel_id": 777,
                    }
                }
            },
        )

        self.assertEqual(normalized.channel_id, 55)
        self.assertEqual(normalized.message_id, 101)
        self.assertEqual(normalized.reply_to_message_id, 100)
        self.assertEqual(normalized.forwarded_from, 777)
        self.assertEqual(normalized.media_refs[0].storage_path, "media/msg-101.jpg")


if __name__ == "__main__":
    unittest.main()
