from __future__ import annotations

import json
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from telegram_scraper.kg.models import (
    ExtractedSemanticNode,
    MessageSemanticExtraction,
    RawMessage,
)


# ============================================================
# Text helpers for message extraction.
# ============================================================


def preferred_message_text(message: RawMessage) -> str:
    return (message.english_text or message.text or "").strip()


def safe_message_text(text: str, *, max_chars: int) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    head = max_chars // 2
    tail = max_chars - head - 1
    return stripped[:head].rstrip() + "\n" + stripped[-tail:].lstrip()



# ============================================================
# JSON Schema for structured extraction output.
# Used with OpenAI's `response_format={"type": "json_schema", ...}` mode.
# Guarantees the model returns a JSON object matching the schema —
# eliminates the free-form JSON parsing fallback.
# ============================================================


def _entity_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "summary", "aliases", "start_at", "end_at"],
        "properties": {
            "name": {"type": "string", "description": "Canonical name of the entity as mentioned in the text."},
            "summary": {
                "type": ["string", "null"],
                "description": "One-sentence description. Null if the text lacks enough context.",
            },
            "aliases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Other names, abbreviations, or spellings for this entity from the text.",
            },
            "start_at": {
                "type": ["string", "null"],
                "description": "ISO-8601 timestamp if the text specifies when the entity started/occurred; otherwise null.",
            },
            "end_at": {
                "type": ["string", "null"],
                "description": "ISO-8601 timestamp if the text specifies when the entity ended; otherwise null.",
            },
        },
    }


MESSAGE_EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "name": "message_semantic_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["events", "people", "nations", "orgs", "places", "themes", "primary_event"],
        "properties": {
            "events": {"type": "array", "items": _entity_schema()},
            "people": {"type": "array", "items": _entity_schema()},
            "nations": {"type": "array", "items": _entity_schema()},
            "orgs": {"type": "array", "items": _entity_schema()},
            "places": {"type": "array", "items": _entity_schema()},
            "themes": {"type": "array", "items": _entity_schema()},
            "primary_event": {
                "type": ["string", "null"],
                "description": (
                    "Name of the most important event in the message. "
                    "Must match exactly one of the names in `events`. "
                    "Null if there are no events."
                ),
            },
        },
    },
}


MESSAGE_EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured semantic information from a single Telegram news post. "
    "Output entities actually mentioned or strongly implied — do not invent details. "
    "Categorize entities precisely: "
    "events (discrete occurrences like strikes, speeches, launches, operations); "
    "people (named individuals); "
    "nations (countries or nation-states); "
    "orgs (military, governmental, corporate, or militant organizations); "
    "places (cities, regions, facilities); "
    "themes (ongoing narratives or abstract topics, e.g. 'Israel-Hamas conflict'). "
    "If the post has no meaningful entities of a category, return an empty array for that category. "
    "For primary_event: if the post describes events, pick the single most important one and return its exact name; otherwise return null. "
    "Use ISO-8601 for timestamps when the text provides them; otherwise use null. "
    "Aliases should be other names or spellings present in the text, not your own generated variants."
)


# ============================================================
# Extractor class — message-atomic API.
# ============================================================


class OpenAISemanticExtractor:
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

    def extract_message(self, message: RawMessage) -> MessageSemanticExtraction:
        """Extract entities from a single message using OpenAI structured output."""
        prepared_text = safe_message_text(
            preferred_message_text(message) or "(media only telegram message)",
            max_chars=self.max_chars,
        )
        try:
            payload = self._call_structured(prepared_text)
        except Exception:
            return MessageSemanticExtraction(
                channel_id=message.channel_id,
                message_id=message.message_id,
            )
        return _message_extraction_from_payload(
            channel_id=message.channel_id,
            message_id=message.message_id,
            payload=payload,
        )

    def extract_messages(
        self,
        messages: Sequence[RawMessage],
        *,
        max_workers: int | None = None,
    ) -> list[MessageSemanticExtraction]:
        """Extract entities from many messages in parallel.

        Each message is an independent OpenAI call (structured output).
        Parallelism is bounded by ``max_workers`` (defaults to ``batch_size``).
        """
        if not messages:
            return []
        workers = max(1, max_workers if max_workers is not None else self.batch_size)
        if workers == 1 or len(messages) == 1:
            return [self.extract_message(m) for m in messages]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self.extract_message, messages))

    def _call_structured(self, prepared_text: str) -> dict[str, Any]:
        """Call OpenAI with JSON schema structured output. Returns parsed dict.

        Uses the Responses API with response_format=json_schema to guarantee
        schema-conformant output. No fallback JSON parsing needed.
        """
        client = self._client()
        response = client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": MESSAGE_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prepared_text},
            ],
            response_format={"type": "json_schema", "json_schema": MESSAGE_EXTRACTION_JSON_SCHEMA},
        )
        # With strict JSON schema, output_text is guaranteed to be a valid JSON object
        # matching the schema. json.loads is safe.
        return json.loads(response.output_text or "{}")


# ============================================================
# Payload parsers.
# ============================================================


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


def _message_extraction_from_payload(
    *,
    channel_id: int,
    message_id: int,
    payload: Any,
) -> MessageSemanticExtraction:
    try:
        payload_dict = payload if isinstance(payload, dict) else {}
        return MessageSemanticExtraction(
            channel_id=channel_id,
            message_id=message_id,
            events=_load_nodes(payload_dict.get("events")),
            people=_load_nodes(payload_dict.get("people")),
            nations=_load_nodes(payload_dict.get("nations")),
            orgs=_load_nodes(payload_dict.get("orgs")),
            places=_load_nodes(payload_dict.get("places")),
            themes=_load_nodes(payload_dict.get("themes")),
            primary_event=_coerce_string(payload_dict.get("primary_event")),
        )
    except Exception:
        return MessageSemanticExtraction(channel_id=channel_id, message_id=message_id)


def _load_nodes(payload: Any) -> tuple[ExtractedSemanticNode, ...]:
    if not isinstance(payload, list):
        return ()
    nodes: list[ExtractedSemanticNode] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = _coerce_string(item.get("name"))
        if not name:
            continue
        aliases = item.get("aliases")
        nodes.append(
            ExtractedSemanticNode(
                name=name,
                summary=_coerce_string(item.get("summary")),
                aliases=tuple(alias for alias in (_coerce_string(value) for value in aliases or []) if alias),
                start_at=_coerce_datetime(item.get("start_at")),
                end_at=_coerce_datetime(item.get("end_at")),
            )
        )
    return tuple(nodes)


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_datetime(value: Any) -> datetime | None:
    text = _coerce_string(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
