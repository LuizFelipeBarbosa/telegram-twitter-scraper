from __future__ import annotations

import math
from typing import Any

import pandas as pd

from telegram_scraper.notebook_pipeline import RawMessage


UNKNOWN_LANGUAGE = "und"


def channel_label(chat: Any) -> str:
    title = getattr(chat, "title", None)
    username = getattr(chat, "username", None)
    chat_id = getattr(chat, "chat_id", None)
    return title or username or str(chat_id or chat)


def message_used_translation(message: RawMessage) -> bool:
    original = (message.text or "").strip()
    english = (message.english_text or "").strip()
    return bool(english and english != original)


def to_utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def subplot_grid(panel_count: int, *, max_cols: int = 2) -> tuple[int, int]:
    if panel_count <= 0:
        return 1, 1
    cols = min(max_cols, panel_count)
    rows = int(math.ceil(panel_count / cols))
    return rows, cols
