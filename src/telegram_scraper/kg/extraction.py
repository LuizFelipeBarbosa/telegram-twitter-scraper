from __future__ import annotations

import json
from datetime import datetime
import threading
from typing import Any, Sequence

from telegram_scraper.kg.models import ExtractedSemanticNode, StorySemanticExtraction, StoryUnit


def preferred_story_text(story: StoryUnit) -> str:
    return (story.english_combined_text or story.combined_text or "").strip()


def safe_story_text(text: str, *, max_chars: int) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    head = max_chars // 2
    tail = max_chars - head - 1
    return stripped[:head].rstrip() + "\n" + stripped[-tail:].lstrip()


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

    def extract_story(self, story: StoryUnit) -> StorySemanticExtraction:
        return self.extract_stories([story])[0]

    def extract_stories(self, stories: Sequence[StoryUnit]) -> list[StorySemanticExtraction]:
        if not stories:
            return []
        results: list[StorySemanticExtraction] = []
        for batch in _batch_story_payloads(stories, max_chars=self.max_chars, max_batch_size=self.batch_size):
            try:
                results.extend(self._extract_batch(batch))
            except Exception:
                results.extend(self._extract_batch_fallback(batch))
        return results

    def _extract_batch(self, batch: Sequence[tuple[StoryUnit, str]]) -> list[StorySemanticExtraction]:
        client = self._client()
        story_payload = {
            str(story.story_id): {
                "story_id": str(story.story_id),
                "text": prepared_text,
            }
            for story, prepared_text in batch
        }
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract semantic nodes from each news story. "
                        "Return strict JSON keyed by story_id. "
                        "Each value must be an object with keys events, people, nations, orgs, places, themes, primary_event. "
                        "Each list item must be an object with name, summary, aliases, start_at, end_at. "
                        "Use null for unknown values. "
                        "If events are present, primary_event must equal exactly one event name."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(story_payload, ensure_ascii=True),
                },
            ],
        )
        payload = _parse_json_object(response.output_text or "")
        extraction_map = _load_story_extractions(payload)
        results: list[StorySemanticExtraction] = []
        for story, _prepared_text in batch:
            story_id = str(story.story_id)
            if story_id not in extraction_map:
                raise ValueError(f"missing extraction payload for story {story_id}")
            results.append(_story_extraction_from_payload(story_id, extraction_map[story_id]))
        return results

    def _extract_batch_fallback(self, batch: Sequence[tuple[StoryUnit, str]]) -> list[StorySemanticExtraction]:
        return [self._extract_single_story(story, prepared_text=prepared_text) for story, prepared_text in batch]

    def _extract_single_story(self, story: StoryUnit, *, prepared_text: str | None = None) -> StorySemanticExtraction:
        prepared_text = prepared_text or safe_story_text(
            preferred_story_text(story) or "(media only telegram story)",
            max_chars=self.max_chars,
        )
        try:
            client = self._client()
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Extract semantic nodes from a news story. "
                            "Return strict JSON with keys events, people, nations, orgs, places, themes, primary_event. "
                            "Each list item must be an object with name, summary, aliases, start_at, end_at. "
                            "Use null for unknown values. "
                            "If events are present, primary_event must equal exactly one event name."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Story ID: {story.story_id}\n\nStory text:\n{prepared_text}",
                    },
                ],
            )
            return _story_extraction_from_payload(story.story_id, _parse_json_object(response.output_text or ""))
        except Exception:
            return StorySemanticExtraction(story_id=story.story_id)


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


def _story_extraction_from_payload(story_id: str, payload: Any) -> StorySemanticExtraction:
    try:
        payload_dict = payload if isinstance(payload, dict) else {}
        return StorySemanticExtraction(
            story_id=str(story_id),
            events=_load_nodes(payload_dict.get("events")),
            people=_load_nodes(payload_dict.get("people")),
            nations=_load_nodes(payload_dict.get("nations")),
            orgs=_load_nodes(payload_dict.get("orgs")),
            places=_load_nodes(payload_dict.get("places")),
            themes=_load_nodes(payload_dict.get("themes")),
            primary_event=_coerce_string(payload_dict.get("primary_event")),
        )
    except Exception:
        return StorySemanticExtraction(story_id=str(story_id))


def _load_story_extractions(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    if "stories" in payload and isinstance(payload["stories"], dict):
        payload = payload["stories"]
    results: dict[str, dict[str, Any]] = {}
    for story_id, extraction_payload in payload.items():
        if isinstance(extraction_payload, dict):
            results[str(story_id)] = extraction_payload
    return results


def _batch_story_payloads(
    stories: Sequence[StoryUnit],
    *,
    max_chars: int,
    max_batch_size: int,
) -> list[list[tuple[StoryUnit, str]]]:
    max_total_chars = max_chars * max_batch_size
    batches: list[list[tuple[StoryUnit, str]]] = []
    current: list[tuple[StoryUnit, str]] = []
    current_chars = 0
    for story in stories:
        prepared_text = safe_story_text(preferred_story_text(story) or "(media only telegram story)", max_chars=max_chars)
        story_chars = len(prepared_text)
        if current and (len(current) >= max_batch_size or current_chars + story_chars > max_total_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append((story, prepared_text))
        current_chars += story_chars
    if current:
        batches.append(current)
    return batches


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
