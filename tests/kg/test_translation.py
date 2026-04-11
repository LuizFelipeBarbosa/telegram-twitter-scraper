from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from telegram_scraper.kg.models import RawMessage
from telegram_scraper.kg.translation import OpenAIMessageTranslator


def build_message(message_id: int, text: str, *, translated: bool = False) -> RawMessage:
    return RawMessage(
        channel_id=-100,
        message_id=message_id,
        timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
        sender_id=None,
        sender_name=None,
        text=text,
        raw_json={"id": message_id},
        english_text=text if translated else None,
        source_language="en" if translated else None,
        translated_at=datetime(2026, 4, 10, 12, 1, tzinfo=timezone.utc) if translated else None,
    )


class FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output_text = self.outputs.pop(0)
        return type("Response", (), {"output_text": output_text})()


class FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = FakeResponses(outputs)


class TranslationTests(unittest.TestCase):
    def test_translate_messages_mirrors_probably_english_text_without_api_call(self):
        translator = OpenAIMessageTranslator(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        translator._thread_local.client = FakeClient([])

        results = translator.translate_messages([build_message(1, "This is already English")])

        self.assertEqual(results[0].english_text, "This is already English")
        self.assertEqual(results[0].source_language, "en")
        self.assertEqual(translator._thread_local.client.responses.calls, [])

    def test_translate_messages_uses_api_for_non_english_text(self):
        translator = OpenAIMessageTranslator(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        fake_client = FakeClient(
            [
                json.dumps(
                    {
                        "-100:2": {
                            "source_language": "fa",
                            "english_text": "Hello world",
                        }
                    }
                )
            ]
        )
        translator._thread_local.client = fake_client

        results = translator.translate_messages([build_message(2, "سلام دنیا")])

        self.assertEqual(results[0].english_text, "Hello world")
        self.assertEqual(results[0].source_language, "fa")
        self.assertEqual(len(fake_client.responses.calls), 1)

    def test_translate_messages_skips_cached_rows(self):
        translator = OpenAIMessageTranslator(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        translator._thread_local.client = FakeClient([])
        cached = build_message(3, "Stored English", translated=True)

        results = translator.translate_messages([cached])

        self.assertEqual(results[0].translated_at, cached.translated_at)
        self.assertEqual(translator._thread_local.client.responses.calls, [])


if __name__ == "__main__":
    unittest.main()
