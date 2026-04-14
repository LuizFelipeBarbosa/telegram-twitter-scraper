from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from telegram_scraper.config import ConfigError, load_dotenv
from telegram_scraper.models import MessageRecord
from telegram_scraper.utils import ensure_utc


_NON_LATIN_RE = re.compile(r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF]")
_EMBED_BATCH_SIZE = 100


@dataclass(frozen=True)
class NotebookSettings:
    openai_api_key: str
    embedding_model: str
    translation_model: str
    semantic_max_chars: int
    semantic_batch_size: int

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "NotebookSettings":
        env_path = Path(env_file)
        values = {**os.environ, **load_dotenv(env_path)}
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "NotebookSettings":
        return cls(
            openai_api_key=values.get("OPENAI_API_KEY", "").strip(),
            embedding_model=values.get("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            translation_model=values.get("KG_TRANSLATION_MODEL", "gpt-5-mini").strip(),
            semantic_max_chars=max(1000, int(values.get("KG_SEMANTIC_MAX_CHARS", "12000"))),
            semantic_batch_size=max(1, int(values.get("KG_SEMANTIC_BATCH_SIZE", "8"))),
        )

    def require_translation(self) -> None:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.translation_model:
            missing.append("KG_TRANSLATION_MODEL")
        if missing:
            raise ConfigError(f"missing required settings: {', '.join(missing)}")

    def require_embeddings(self) -> None:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.embedding_model:
            missing.append("EMBEDDING_MODEL")
        if missing:
            raise ConfigError(f"missing required settings: {', '.join(missing)}")


@dataclass(frozen=True)
class MediaRef:
    media_type: str
    storage_path: str | None
    mime_type: str | None = None
    file_name: str | None = None


@dataclass(frozen=True)
class RawMessage:
    channel_id: int
    message_id: int
    timestamp: datetime
    sender_id: int | None
    sender_name: str | None
    text: str | None
    media_refs: tuple[MediaRef, ...] = ()
    forwarded_from: int | None = None
    reply_to_message_id: int | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)
    english_text: str | None = None
    source_language: str | None = None
    translated_at: datetime | None = None

    @property
    def is_media_only(self) -> bool:
        return not (self.text or "").strip() and bool(self.media_refs)


def preferred_message_text(message: RawMessage) -> str:
    return (message.english_text or message.text or "").strip()


def safe_message_text(text: str, *, max_chars: int) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    head = max_chars // 2
    tail = max_chars - head - 1
    return stripped[:head].rstrip() + "\n" + stripped[-tail:].lstrip()


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


def _media_refs_from_message(message: MessageRecord) -> tuple[MediaRef, ...]:
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
        media_refs=_media_refs_from_message(message),
        forwarded_from=_extract_forwarded_from(payload),
        reply_to_message_id=message.reply_to_message_id,
        raw_json=payload,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_translation_text(text: str, *, max_chars: int) -> str:
    return safe_message_text(text, max_chars=max_chars)


def _looks_probably_english(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _NON_LATIN_RE.search(stripped):
        return False
    alpha_chars = [char for char in stripped if char.isalpha()]
    if not alpha_chars:
        return True
    ascii_alpha = sum(1 for char in alpha_chars if char.isascii())
    return (ascii_alpha / len(alpha_chars)) >= 0.9


def _message_cache_key(message: RawMessage) -> str:
    return f"{message.channel_id}:{message.message_id}"


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            payload = json.loads(stripped[start : end + 1])
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


def _batch_message_payloads(
    messages: Sequence[RawMessage],
    *,
    max_chars: int,
    max_batch_size: int,
) -> list[list[tuple[RawMessage, str]]]:
    max_total_chars = max_chars * max_batch_size
    batches: list[list[tuple[RawMessage, str]]] = []
    current: list[tuple[RawMessage, str]] = []
    current_chars = 0
    for message in messages:
        prepared_text = safe_translation_text(message.text or "", max_chars=max_chars)
        message_chars = len(prepared_text)
        if current and (len(current) >= max_batch_size or current_chars + message_chars > max_total_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append((message, prepared_text))
        current_chars += message_chars
    if current:
        batches.append(current)
    return batches


def _restore_message_order(source: Sequence[RawMessage], resolved: Sequence[RawMessage]) -> list[RawMessage]:
    resolved_by_key = {_message_cache_key(message): message for message in resolved}
    return [resolved_by_key[_message_cache_key(message)] for message in source]


class OpenAIMessageTranslator:
    def __init__(self, *, api_key: str, model: str, max_chars: int = 12000, batch_size: int = 8):
        self.api_key = api_key
        self.model = model
        self.max_chars = max(1000, max_chars)
        self.batch_size = max(1, batch_size)
        self._thread_local = threading.local()

    def _client(self):
        client = getattr(self._thread_local, "client", None)
        if client is not None:
            return client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai is not installed. Install project dependencies before using notebook helpers.") from exc
        client = OpenAI(api_key=self.api_key)
        self._thread_local.client = client
        return client

    def translate_messages(self, messages: Sequence[RawMessage]) -> list[RawMessage]:
        if not messages:
            return []
        translated: list[RawMessage] = []
        pending: list[RawMessage] = []
        now = _utc_now()
        for message in messages:
            if message.translated_at is not None and (message.english_text is not None or message.source_language is not None):
                translated.append(message)
                continue
            stripped = (message.text or "").strip()
            if not stripped:
                translated.append(
                    RawMessage(
                        **{
                            **message.__dict__,
                            "english_text": None,
                            "source_language": "und",
                            "translated_at": now,
                        }
                    )
                )
                continue
            if _looks_probably_english(stripped):
                translated.append(
                    RawMessage(
                        **{
                            **message.__dict__,
                            "english_text": stripped,
                            "source_language": "en",
                            "translated_at": now,
                        }
                    )
                )
                continue
            pending.append(message)

        if not pending:
            return _restore_message_order(messages, translated)

        results_by_key: dict[str, RawMessage] = {
            _message_cache_key(message): message for message in translated
        }
        for batch in _batch_message_payloads(pending, max_chars=self.max_chars, max_batch_size=self.batch_size):
            try:
                translated_batch = self._translate_batch(batch)
            except Exception:
                translated_batch = [self._translate_single(message, prepared_text=text) for message, text in batch]
            for message in translated_batch:
                results_by_key[_message_cache_key(message)] = message
        return [results_by_key[_message_cache_key(message)] for message in messages]

    def _translate_batch(self, batch: Sequence[tuple[RawMessage, str]]) -> list[RawMessage]:
        client = self._client()
        payload = {
            _message_cache_key(message): {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "text": prepared_text,
            }
            for message, prepared_text in batch
        }
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Translate Telegram messages into English. "
                        "Return strict JSON keyed by '<channel_id>:<message_id>'. "
                        "Each value must contain source_language and english_text. "
                        "If a message is already English, set source_language to 'en' and english_text to the original text. "
                        "Do not summarize or omit details."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=True),
                },
            ],
        )
        translation_payload = _parse_json_object(response.output_text or "")
        results: list[RawMessage] = []
        now = _utc_now()
        for message, prepared_text in batch:
            key = _message_cache_key(message)
            item = translation_payload.get(key)
            if not isinstance(item, dict):
                raise ValueError(f"missing translation payload for message {key}")
            results.append(
                RawMessage(
                    **{
                        **message.__dict__,
                        "english_text": _coerce_string(item.get("english_text")) or prepared_text,
                        "source_language": _coerce_string(item.get("source_language")) or "und",
                        "translated_at": now,
                    }
                )
            )
        return results

    def _translate_single(self, message: RawMessage, *, prepared_text: str | None = None) -> RawMessage:
        prepared_text = prepared_text or safe_translation_text(message.text or "", max_chars=self.max_chars)
        client = self._client()
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Translate a Telegram message into English. "
                        "Return strict JSON with keys source_language and english_text. "
                        "If the message is already English, use source_language='en' and mirror the original text."
                    ),
                },
                {
                    "role": "user",
                    "content": prepared_text,
                },
            ],
        )
        item = _parse_json_object(response.output_text or "")
        return RawMessage(
            **{
                **message.__dict__,
                "english_text": _coerce_string(item.get("english_text")) or prepared_text,
                "source_language": _coerce_string(item.get("source_language")) or "und",
                "translated_at": _utc_now(),
            }
        )


class OpenAIEmbedder:
    def __init__(self, *, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._cached_client = None

    def _client(self):
        if self._cached_client is not None:
            return self._cached_client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai is not installed. Install project dependencies before using notebook helpers.") from exc
        self._cached_client = OpenAI(api_key=self.api_key)
        return self._cached_client

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._client()
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = list(texts[start : start + _EMBED_BATCH_SIZE])
            response = client.embeddings.create(model=self.model, input=batch)
            embeddings.extend(list(item.embedding) for item in response.data)
        return embeddings
