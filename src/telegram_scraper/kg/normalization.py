from __future__ import annotations

from typing import Any, Mapping

from telegram_scraper.models import MessageRecord
from telegram_scraper.utils import ensure_utc

from telegram_scraper.kg.models import MediaRef, RawMessage


def _extract_forwarded_from(raw_json: Mapping[str, Any]) -> int | None:
    forwarded = raw_json.get("fwd_from")
    if not isinstance(forwarded, Mapping):
        return None
    from_id = forwarded.get("from_id")
    if isinstance(from_id, Mapping):
        for key in ("channel_id", "chat_id", "user_id"):
            value = from_id.get(key)
            if value is not None:
                return int(value)
    for key in ("from_id", "channel_id", "saved_from_peer"):
        value = forwarded.get(key)
        if isinstance(value, int):
            return value
    return None


def _fallback_raw_json(message: MessageRecord) -> dict[str, Any]:
    return {
        "id": message.message_id,
        "date": message.posted_at.isoformat(),
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "reply_to_msg_id": message.reply_to_message_id,
        "message": message.text,
        "has_media": message.has_media,
    }


def media_refs_from_message(message: MessageRecord) -> tuple[MediaRef, ...]:
    return tuple(
        MediaRef(
            media_type=media.media_type,
            storage_path=media.relative_path,
            mime_type=media.mime_type,
            file_name=media.file_name,
        )
        for media in message.media_files
    )


def normalize_message_record(message: MessageRecord, *, raw_json: Mapping[str, Any] | None = None) -> RawMessage:
    payload = dict(raw_json or _fallback_raw_json(message))
    timestamp = ensure_utc(message.posted_at)
    if timestamp is None:
        raise ValueError("message timestamp is required")
    text = message.text.strip() or None
    return RawMessage(
        channel_id=message.chat.chat_id,
        message_id=message.message_id,
        timestamp=timestamp,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        text=text,
        media_refs=media_refs_from_message(message),
        forwarded_from=_extract_forwarded_from(payload),
        reply_to_message_id=message.reply_to_message_id,
        raw_json=payload,
    )
