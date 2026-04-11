from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from telegram_scraper.kg.extraction import OpenAISemanticExtractor, _batch_story_payloads
from telegram_scraper.kg.models import StoryUnit


def build_story(story_id: str, text: str, *, english_text: str | None = None) -> StoryUnit:
    timestamp = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    return StoryUnit(
        story_id=story_id,
        channel_id=100,
        timestamp_start=timestamp,
        timestamp_end=timestamp,
        message_ids=(1,),
        combined_text=text,
        english_combined_text=english_text,
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
    def test_extract_stories_preserves_input_order_when_batch_keys_are_unordered(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        extractor._thread_local.client = FakeClient(
            [
                json.dumps(
                    {
                        "story-b": {"people": [{"name": "Bob"}]},
                        "story-a": {"people": [{"name": "Alice"}]},
                    }
                )
            ]
        )
        stories = [build_story("story-a", "Alpha"), build_story("story-b", "Beta")]

        results = extractor.extract_stories(stories)

        self.assertEqual([result.story_id for result in results], ["story-a", "story-b"])
        self.assertEqual(results[0].people[0].name, "Alice")
        self.assertEqual(results[1].people[0].name, "Bob")

    def test_extract_stories_falls_back_to_per_story_when_batch_output_is_malformed(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        fake_client = FakeClient(
            [
                "not json",
                json.dumps({"people": [{"name": "Alice"}]}),
                json.dumps({"people": [{"name": "Bob"}]}),
            ]
        )
        extractor._thread_local.client = fake_client
        stories = [build_story("story-a", "Alpha"), build_story("story-b", "Beta")]

        results = extractor.extract_stories(stories)

        self.assertEqual(fake_client.responses.calls[0]["model"], "gpt-5-mini")
        self.assertEqual(len(fake_client.responses.calls), 3)
        self.assertEqual(results[0].people[0].name, "Alice")
        self.assertEqual(results[1].people[0].name, "Bob")

    def test_batch_story_payloads_split_by_batch_size_and_story_length_limit(self):
        stories = [
            build_story("story-a", "A" * 40),
            build_story("story-b", "B" * 40),
            build_story("story-c", "C" * 40),
        ]

        batches = _batch_story_payloads(stories, max_chars=12, max_batch_size=2)

        self.assertEqual([len(batch) for batch in batches], [2, 1])
        for batch in batches:
            for _story, prepared_text in batch:
                self.assertLessEqual(len(prepared_text), 12)

    def test_extract_stories_prefers_english_combined_text_when_present(self):
        extractor = OpenAISemanticExtractor(api_key="sk-test", model="gpt-5-mini", batch_size=4)
        fake_client = FakeClient([json.dumps({"story-a": {"people": [{"name": "Alice"}]}})])
        extractor._thread_local.client = fake_client
        story = build_story("story-a", "سلام دنیا", english_text="Hello world")

        extractor.extract_stories([story])

        request_payload = fake_client.responses.calls[0]["input"][1]["content"]
        self.assertIn("Hello world", request_payload)
        self.assertNotIn("سلام دنیا", request_payload)


if __name__ == "__main__":
    unittest.main()
