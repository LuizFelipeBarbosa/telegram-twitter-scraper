from __future__ import annotations

import unittest
from datetime import datetime, timezone

from telegram_scraper.kg.models import ChannelProfile, DelimiterPattern, MediaRef, RawMessage
from telegram_scraper.kg.segmentation import StorySegmenter


def build_message(
    message_id: int,
    minute: int,
    text: str | None,
    *,
    second: int = 0,
    media: bool = False,
) -> RawMessage:
    return RawMessage(
        channel_id=123,
        message_id=message_id,
        timestamp=datetime(2026, 4, 9, 12, minute, second, tzinfo=timezone.utc),
        sender_id=1,
        sender_name="Alice",
        text=text,
        media_refs=(MediaRef(media_type="photo", storage_path=f"media/{message_id}.jpg"),) if media else (),
        raw_json={"id": message_id},
    )


class StorySegmenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.segmenter = StorySegmenter()
        self.profile = ChannelProfile(
            channel_id=123,
            delimiter_patterns=(DelimiterPattern(kind="prefix", pattern="Breaking:"),),
            time_gap_minutes=10,
            similarity_merge_threshold=0.7,
            media_group_window_seconds=60,
        )

    def test_build_candidates_uses_delimiters_and_time_gaps(self) -> None:
        messages = [
            build_message(1, 0, "alpha bulletin"),
            build_message(2, 1, "alpha details"),
            build_message(3, 2, "Breaking: beta headline"),
            build_message(4, 3, "beta details"),
            build_message(5, 20, "gamma update"),
        ]

        candidates = self.segmenter.build_candidates(messages, self.profile)

        self.assertEqual(len(candidates), 3)
        self.assertEqual([message.message_id for message in candidates[0]], [1, 2])
        self.assertEqual([message.message_id for message in candidates[1]], [3, 4])
        self.assertEqual([message.message_id for message in candidates[2]], [5])

    def test_merge_candidates_merges_semantically_similar_groups(self) -> None:
        candidates = [
            [build_message(1, 0, "alpha bulletin")],
            [build_message(2, 1, "alpha followup")],
            [build_message(3, 2, "beta bulletin")],
        ]
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.95, 0.05, 0.0],
            [0.0, 1.0, 0.0],
        ]

        merged = self.segmenter.merge_candidates(candidates, embeddings, self.profile)

        self.assertEqual(len(merged), 2)
        self.assertEqual([message.message_id for message in merged[0]], [1, 2])
        self.assertEqual([message.message_id for message in merged[1]], [3])

    def test_create_story_attaches_nearby_media_only_messages_and_is_deterministic(self) -> None:
        messages = [
            build_message(10, 0, "alpha bulletin"),
            build_message(11, 0, None, second=30, media=True),
            build_message(12, 2, None, media=True),
        ]

        first = self.segmenter.create_story(messages, profile=self.profile)
        second = self.segmenter.create_story(messages, profile=self.profile)

        self.assertEqual(first.story_id, second.story_id)
        self.assertEqual(first.message_ids, (10, 11, 12))
        self.assertEqual(len(first.media_refs), 1)
        self.assertEqual(first.media_refs[0].storage_path, "media/11.jpg")


if __name__ == "__main__":
    unittest.main()
