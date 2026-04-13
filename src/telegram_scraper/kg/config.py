from __future__ import annotations

import json as _json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from telegram_scraper.config import ConfigError, load_dotenv
from telegram_scraper.kg.heat_phase import (
    DEFAULT_EVENT_HEAT_THRESHOLDS,
    DEFAULT_THEME_HEAT_THRESHOLDS,
    HeatPhaseThresholds,
)


def _parse_heat_thresholds(
    values: Mapping[str, str],
    kind_prefix: str,
    defaults: HeatPhaseThresholds,
) -> HeatPhaseThresholds | None:
    enabled_key = f"KG_{kind_prefix}_HEAT_PHASE_ENABLED"
    if values.get(enabled_key, "1").strip() == "0":
        return None
    json_key = f"KG_{kind_prefix}_HEAT_THRESHOLDS_JSON"
    raw_json = values.get(json_key, "").strip()
    if not raw_json:
        return defaults
    parsed = _json.loads(raw_json)
    return HeatPhaseThresholds(**parsed)


@dataclass(frozen=True)
class KGSettings:
    database_url: str
    redis_url: str
    pinecone_api_key: str
    pinecone_index_story: str
    pinecone_index_theme: str
    pinecone_index_event: str
    openai_api_key: str
    embedding_model: str
    semantic_model: str
    translation_model: str
    stream_key: str
    consumer_group: str
    cross_channel_threshold: float
    vector_dimension: int
    segment_batch_size: int
    stream_retention_ms: int
    semantic_max_chars: int
    semantic_batch_size: int
    historical_extraction_workers: int
    theme_match_threshold: float
    event_match_threshold: float
    event_match_window_days: int
    theme_heat_thresholds: HeatPhaseThresholds | None
    event_heat_thresholds: HeatPhaseThresholds | None

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "KGSettings":
        env_path = Path(env_file)
        values = {**os.environ, **load_dotenv(env_path)}
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "KGSettings":
        deprecated_topic_index = values.get("PINECONE_INDEX_TOPIC", "").strip()
        return cls(
            database_url=values.get("DATABASE_URL", "").strip(),
            redis_url=values.get("REDIS_URL", "").strip(),
            pinecone_api_key=values.get("PINECONE_API_KEY", "").strip(),
            pinecone_index_story=values.get("PINECONE_INDEX_STORY", "story-embeddings").strip(),
            pinecone_index_theme=values.get("PINECONE_INDEX_THEME", deprecated_topic_index or "theme-centroids").strip(),
            pinecone_index_event=values.get("PINECONE_INDEX_EVENT", "event-centroids").strip(),
            openai_api_key=values.get("OPENAI_API_KEY", "").strip(),
            embedding_model=values.get("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            semantic_model=values.get("KG_SEMANTIC_MODEL", "gpt-5-mini").strip(),
            translation_model=values.get("KG_TRANSLATION_MODEL", "gpt-5-mini").strip(),
            stream_key=values.get("KG_STREAM_KEY", "telegram:raw").strip(),
            consumer_group=values.get("KG_CONSUMER_GROUP", "segmentation-workers").strip(),
            cross_channel_threshold=float(values.get("KG_CROSS_CHANNEL_THRESHOLD", "0.85")),
            vector_dimension=int(values.get("KG_VECTOR_DIMENSION", "1536")),
            segment_batch_size=int(values.get("KG_SEGMENT_BATCH_SIZE", "25")),
            stream_retention_ms=int(values.get("KG_STREAM_RETENTION_MS", str(48 * 60 * 60 * 1000))),
            semantic_max_chars=int(values.get("KG_SEMANTIC_MAX_CHARS", "12000")),
            semantic_batch_size=max(1, int(values.get("KG_SEMANTIC_BATCH_SIZE", "8"))),
            historical_extraction_workers=max(1, int(values.get("KG_HISTORICAL_EXTRACTION_WORKERS", "4"))),
            theme_match_threshold=float(values.get("KG_THEME_MATCH_THRESHOLD", "0.78")),
            event_match_threshold=float(values.get("KG_EVENT_MATCH_THRESHOLD", "0.80")),
            event_match_window_days=int(values.get("KG_EVENT_MATCH_WINDOW_DAYS", "14")),
            theme_heat_thresholds=_parse_heat_thresholds(values, "THEME", DEFAULT_THEME_HEAT_THRESHOLDS),
            event_heat_thresholds=_parse_heat_thresholds(values, "EVENT", DEFAULT_EVENT_HEAT_THRESHOLDS),
        )

    def require_database(self) -> None:
        if not self.database_url:
            raise ConfigError("missing required settings: DATABASE_URL")

    def require_stream(self) -> None:
        if not self.redis_url:
            raise ConfigError("missing required settings: REDIS_URL")

    def require_vector_store(self) -> None:
        missing: list[str] = []
        if not self.pinecone_api_key:
            missing.append("PINECONE_API_KEY")
        if not self.pinecone_index_story:
            missing.append("PINECONE_INDEX_STORY")
        if not self.pinecone_index_theme:
            missing.append("PINECONE_INDEX_THEME")
        if not self.pinecone_index_event:
            missing.append("PINECONE_INDEX_EVENT")
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

    def require_semantic_extraction(self) -> None:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.semantic_model:
            missing.append("KG_SEMANTIC_MODEL")
        if missing:
            raise ConfigError(f"missing required settings: {', '.join(missing)}")

    def require_translation(self) -> None:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.translation_model:
            missing.append("KG_TRANSLATION_MODEL")
        if missing:
            raise ConfigError(f"missing required settings: {', '.join(missing)}")
