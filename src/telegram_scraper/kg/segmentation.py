from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta
from typing import Iterable, Sequence
from uuid import NAMESPACE_URL, uuid5

from telegram_scraper.kg.math_utils import average_vectors, cosine_similarity
from telegram_scraper.kg.models import ChannelProfile, DelimiterPattern, RawMessage, StoryUnit


def _message_text(message: RawMessage) -> str:
    return (message.text or "").strip()


def _message_english_text(message: RawMessage) -> str:
    return (message.english_text or message.text or "").strip()


def default_channel_profile(channel_id: int) -> ChannelProfile:
    return ChannelProfile(channel_id=channel_id)


def parse_delimiter_patterns(payload: Iterable[dict[str, object] | DelimiterPattern]) -> tuple[DelimiterPattern, ...]:
    patterns: list[DelimiterPattern] = []
    for item in payload:
        if isinstance(item, DelimiterPattern):
            patterns.append(item)
            continue
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        pattern = str(item.get("pattern") or "").strip()
        if not kind or not pattern:
            continue
        patterns.append(
            DelimiterPattern(
                kind=kind,
                pattern=pattern,
                case_sensitive=bool(item.get("case_sensitive", False)),
            )
        )
    return tuple(patterns)


def matches_delimiter(text: str | None, patterns: Sequence[DelimiterPattern]) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    for pattern in patterns:
        haystack = value if pattern.case_sensitive else value.lower()
        needle = pattern.pattern if pattern.case_sensitive else pattern.pattern.lower()
        if pattern.kind == "regex":
            flags = 0 if pattern.case_sensitive else re.IGNORECASE
            if re.search(pattern.pattern, value, flags):
                return True
        elif pattern.kind == "keyword" and needle in haystack:
            return True
        elif pattern.kind == "prefix" and haystack.startswith(needle):
            return True
        elif pattern.kind == "emoji" and haystack.startswith(needle):
            return True
        elif pattern.kind == "hashtag":
            hashtag = needle if needle.startswith("#") else f"#{needle}"
            if haystack.startswith(hashtag):
                return True
    return False


class StorySegmenter:
    def build_candidates(self, messages: Sequence[RawMessage], profile: ChannelProfile) -> list[list[RawMessage]]:
        ordered = sorted(messages, key=lambda item: (item.timestamp, item.message_id))
        if not ordered:
            return []

        gap_threshold = timedelta(minutes=profile.time_gap_minutes)
        candidates: list[list[RawMessage]] = []
        current: list[RawMessage] = []

        for message in ordered:
            if not current:
                current = [message]
                continue

            previous = current[-1]
            should_split = matches_delimiter(message.text, profile.delimiter_patterns)
            if not should_split:
                should_split = (message.timestamp - previous.timestamp) > gap_threshold

            if should_split:
                candidates.append(current)
                current = [message]
            else:
                current.append(message)

        if current:
            candidates.append(current)
        return candidates

    def merge_candidates(
        self,
        candidates: Sequence[Sequence[RawMessage]],
        embeddings: Sequence[Sequence[float]],
        profile: ChannelProfile,
    ) -> list[list[RawMessage]]:
        if not candidates:
            return []

        merged: list[list[RawMessage]] = [list(candidates[0])]
        merged_embeddings: list[list[float]] = [list(embeddings[0]) if embeddings else []]
        gap_threshold = timedelta(minutes=profile.time_gap_minutes)

        for index in range(1, len(candidates)):
            current = list(candidates[index])
            current_embedding = list(embeddings[index]) if index < len(embeddings) else []
            previous = merged[-1]
            previous_embedding = merged_embeddings[-1]
            gap = current[0].timestamp - previous[-1].timestamp
            similarity = cosine_similarity(previous_embedding, current_embedding)

            if gap <= gap_threshold and similarity >= profile.similarity_merge_threshold:
                previous.extend(current)
                merged_embeddings[-1] = average_vectors([previous_embedding, current_embedding])
            else:
                merged.append(current)
                merged_embeddings.append(current_embedding)

        return merged

    def should_append_to_existing(
        self,
        existing_story: StoryUnit | None,
        existing_embedding: Sequence[float] | None,
        first_candidate: Sequence[RawMessage] | None,
        first_candidate_embedding: Sequence[float] | None,
        profile: ChannelProfile,
    ) -> bool:
        if existing_story is None or not first_candidate:
            return False
        if matches_delimiter(first_candidate[0].text, profile.delimiter_patterns):
            return False
        gap = first_candidate[0].timestamp - existing_story.timestamp_end
        if gap < timedelta(0) or gap > timedelta(minutes=profile.time_gap_minutes):
            return False
        return cosine_similarity(existing_embedding or [], first_candidate_embedding or []) >= profile.similarity_merge_threshold

    def create_story(
        self,
        messages: Sequence[RawMessage],
        *,
        existing_story_id: str | None = None,
        existing_created_at=None,
        profile: ChannelProfile | None = None,
    ) -> StoryUnit:
        ordered = sorted(messages, key=lambda item: (item.timestamp, item.message_id))
        if not ordered:
            raise ValueError("cannot create a story from an empty message list")
        story_id = existing_story_id or str(uuid5(NAMESPACE_URL, f"telegram-story:{ordered[0].channel_id}:{ordered[0].message_id}"))
        media_window_seconds = (profile.media_group_window_seconds if profile is not None else 60)
        text_timestamps = [message.timestamp for message in ordered if _message_text(message)]
        media_refs = []
        for message in ordered:
            if not message.media_refs:
                continue
            if message.is_media_only and text_timestamps:
                if not any(abs((message.timestamp - timestamp).total_seconds()) <= media_window_seconds for timestamp in text_timestamps):
                    continue
            media_refs.extend(message.media_refs)

        return StoryUnit(
            story_id=story_id,
            channel_id=ordered[0].channel_id,
            timestamp_start=ordered[0].timestamp,
            timestamp_end=ordered[-1].timestamp,
            message_ids=tuple(message.message_id for message in ordered),
            combined_text="\n".join(_message_text(message) for message in ordered if _message_text(message)),
            english_combined_text="\n".join(_message_english_text(message) for message in ordered if _message_english_text(message)) or None,
            media_refs=tuple(media_refs),
            created_at=existing_created_at,
            translation_updated_at=max(
                (message.translated_at for message in ordered if message.translated_at is not None),
                default=None,
            ),
        )

    def preview(self, messages: Sequence[RawMessage], profile: ChannelProfile) -> list[StoryUnit]:
        candidates = self.build_candidates(messages, profile)
        return [self.create_story(candidate, profile=profile) for candidate in candidates]
