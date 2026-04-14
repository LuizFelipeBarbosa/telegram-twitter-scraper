from __future__ import annotations

import re
from typing import Iterable, Sequence

from telegram_scraper.kg.models import ChannelProfile, DelimiterPattern, RawMessage


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
