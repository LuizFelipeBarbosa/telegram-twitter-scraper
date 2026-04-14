from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from telegram_scraper.kg.extraction import OpenAISemanticExtractor
from telegram_scraper.kg.models import RawMessage


def _build_message(message_id: int, text: str, *, english_text: str | None = None) -> RawMessage:
    return RawMessage(
        channel_id=100,
        message_id=message_id,
        timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
        sender_id=1,
        sender_name="Alice",
        text=text,
        english_text=english_text,
        raw_json={"id": message_id},
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


class ExtractionTests(unittest.TestCase):
    def test_extract_message_returns_extraction_with_correct_ids(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        extractor._thread_local.client = FakeClient(
            [json.dumps({"people": [{"name": "Alice", "summary": "", "aliases": [], "start_at": None, "end_at": None}]})]
        )
        message = _build_message(42, "Alice spoke at the summit.")

        result = extractor.extract_message(message)

        self.assertEqual(result.channel_id, 100)
        self.assertEqual(result.message_id, 42)
        self.assertEqual(result.people[0].name, "Alice")

    def test_extract_message_falls_back_on_malformed_output(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        extractor._thread_local.client = FakeClient(["not json"])
        message = _build_message(1, "Some text.")

        result = extractor.extract_message(message)

        self.assertEqual(result.channel_id, 100)
        self.assertEqual(result.message_id, 1)
        self.assertEqual(result.people, ())

    def test_extract_messages_returns_results_in_input_order(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        fake_client = FakeClient(
            [
                json.dumps({"people": [{"name": "Alice", "summary": "", "aliases": [], "start_at": None, "end_at": None}]}),
                json.dumps({"people": [{"name": "Bob", "summary": "", "aliases": [], "start_at": None, "end_at": None}]}),
            ]
        )
        extractor._thread_local.client = fake_client
        messages = [_build_message(1, "Alice text"), _build_message(2, "Bob text")]

        results = extractor.extract_messages(messages, max_workers=1)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].message_id, 1)
        self.assertEqual(results[0].people[0].name, "Alice")
        self.assertEqual(results[1].message_id, 2)
        self.assertEqual(results[1].people[0].name, "Bob")

    def test_extract_message_prefers_english_text(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        fake_client = FakeClient(
            [json.dumps({"people": [{"name": "Alice", "summary": "", "aliases": [], "start_at": None, "end_at": None}]})]
        )
        extractor._thread_local.client = fake_client
        message = _build_message(1, "سلام دنیا", english_text="Hello world")

        extractor.extract_message(message)

        request_payload = fake_client.responses.calls[0]["input"][1]["content"]
        self.assertIn("Hello world", request_payload)
        self.assertNotIn("سلام دنیا", request_payload)


if __name__ == "__main__":
    unittest.main()
