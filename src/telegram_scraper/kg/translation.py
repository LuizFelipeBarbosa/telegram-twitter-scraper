from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Sequence

from telegram_scraper.kg.models import RawMessage


_NON_LATIN_RE = re.compile(r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF]")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_translation_text(text: str, *, max_chars: int) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    head = max_chars // 2
    tail = max_chars - head - 1
    return stripped[:head].rstrip() + "\n" + stripped[-tail:].lstrip()


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
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError("openai is not installed. Install project dependencies before using KG commands.") from exc
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
        try:
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
            payload = _parse_json_object(response.output_text or "")
            return RawMessage(
                **{
                    **message.__dict__,
                    "english_text": _coerce_string(payload.get("english_text")) or prepared_text,
                    "source_language": _coerce_string(payload.get("source_language")) or "und",
                    "translated_at": _utc_now(),
                }
            )
        except Exception:
            return RawMessage(
                **{
                    **message.__dict__,
                    "english_text": prepared_text,
                    "source_language": None,
                    "translated_at": _utc_now(),
                }
            )


def _restore_message_order(source: Sequence[RawMessage], resolved: Sequence[RawMessage]) -> list[RawMessage]:
    resolved_by_key = {_message_cache_key(message): message for message in resolved}
    return [resolved_by_key[_message_cache_key(message)] for message in source]
