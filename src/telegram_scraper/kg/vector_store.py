from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Sequence

from telegram_scraper.kg.models import NodeCentroidRecord, NodeMatch, StoryEmbeddingRecord, StoryMatch


_FETCH_BATCH_SIZE = 200
_UPSERT_MAX_BYTES = 3_500_000


class PineconeVectorStore:
    def __init__(self, *, api_key: str, story_index: str, theme_index: str, event_index: str):
        self.api_key = api_key
        self.story_index_name = story_index
        self.theme_index_name = theme_index
        self.event_index_name = event_index
        self._cached_client = None
        self._cached_story_index = None
        self._cached_theme_index = None
        self._cached_event_index = None

    def _client(self):
        if self._cached_client is not None:
            return self._cached_client
        try:
            from pinecone import Pinecone
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError("pinecone is not installed. Install project dependencies before using KG commands.") from exc
        self._cached_client = Pinecone(api_key=self.api_key)
        return self._cached_client

    def _story_index(self):
        if self._cached_story_index is None:
            self._cached_story_index = self._client().Index(self.story_index_name)
        return self._cached_story_index

    def _theme_index(self):
        if self._cached_theme_index is None:
            self._cached_theme_index = self._client().Index(self.theme_index_name)
        return self._cached_theme_index

    def _event_index(self):
        if self._cached_event_index is None:
            self._cached_event_index = self._client().Index(self.event_index_name)
        return self._cached_event_index

    def upsert_story_embeddings(self, records: Sequence[StoryEmbeddingRecord]) -> None:
        if not records:
            return
        vectors = [
            {
                "id": str(record.story_id),
                "values": record.embedding,
                "metadata": {
                    "channel_id": record.channel_id,
                    "timestamp_start": int(record.timestamp_start.timestamp()),
                    "node_ids": _stringify_ids(record.node_ids),
                },
            }
            for record in records
        ]
        index = self._story_index()
        for batch in _chunk_vectors_by_bytes(vectors, max_bytes=_UPSERT_MAX_BYTES):
            index.upsert(vectors=batch)

    def update_story_node_ids(self, story_id: str, node_ids: Sequence[str]) -> None:
        self._story_index().update(id=str(story_id), set_metadata={"node_ids": _stringify_ids(node_ids)})

    def fetch_story_embeddings(self, story_ids: Sequence[str]) -> dict[str, list[float]]:
        if not story_ids:
            return {}
        vectors: dict[str, list[float]] = {}
        index = self._story_index()
        for batch in _chunked(_stringify_ids(story_ids), _FETCH_BATCH_SIZE):
            response = index.fetch(ids=list(batch))
            payload = _field(response, "vectors", {})
            vectors.update({str(story_id): list(_field(vector, "values", [])) for story_id, vector in payload.items()})
        return vectors

    def query_story_embeddings(
        self,
        embedding: list[float],
        *,
        top_k: int,
        exclude_channel_id: int | None = None,
        timestamp_gte: datetime | None = None,
    ) -> list[StoryMatch]:
        filters: dict[str, Any] = {}
        if exclude_channel_id is not None:
            filters["channel_id"] = {"$ne": exclude_channel_id}
        if timestamp_gte is not None:
            filters["timestamp_start"] = {"$gte": int(timestamp_gte.timestamp())}
        response = self._story_index().query(
            vector=embedding,
            top_k=top_k,
            filter=filters or None,
            include_metadata=True,
        )
        matches = _field(response, "matches", [])
        return [
            StoryMatch(
                story_id=str(_field(match, "id", "")),
                similarity_score=float(_field(match, "score", 0.0)),
                metadata=dict(_field(match, "metadata", {}) or {}),
            )
            for match in matches
        ]

    def upsert_theme_centroids(self, records: Sequence[NodeCentroidRecord]) -> None:
        self._upsert_centroids(self._theme_index(), records)

    def fetch_theme_centroids(self, node_ids: Sequence[str]) -> dict[str, list[float]]:
        return self._fetch_centroids(self._theme_index(), node_ids)

    def query_theme_centroids(self, embedding: list[float], *, top_k: int) -> list[NodeMatch]:
        return self._query_centroids(self._theme_index(), embedding, top_k=top_k)

    def upsert_event_centroids(self, records: Sequence[NodeCentroidRecord]) -> None:
        self._upsert_centroids(self._event_index(), records)

    def fetch_event_centroids(self, node_ids: Sequence[str]) -> dict[str, list[float]]:
        return self._fetch_centroids(self._event_index(), node_ids)

    def query_event_centroids(self, embedding: list[float], *, top_k: int) -> list[NodeMatch]:
        return self._query_centroids(self._event_index(), embedding, top_k=top_k)

    def delete_story_embeddings(self, story_ids: Sequence[str]) -> None:
        if not story_ids:
            return
        for batch in _chunked(_stringify_ids(story_ids), _FETCH_BATCH_SIZE):
            self._story_index().delete(ids=list(batch))

    def delete_theme_centroids(self, node_ids: Sequence[str]) -> None:
        self._delete_centroids(self._theme_index(), node_ids)

    def delete_event_centroids(self, node_ids: Sequence[str]) -> None:
        self._delete_centroids(self._event_index(), node_ids)

    def _upsert_centroids(self, index, records: Sequence[NodeCentroidRecord]) -> None:
        if not records:
            return
        vectors = [
            {
                "id": str(record.node_id),
                "values": record.embedding,
                "metadata": _compact_metadata(
                    {
                        "kind": record.kind,
                        "display_name": record.display_name,
                        "normalized_name": record.normalized_name,
                        "event_start_at": int(record.event_start_at.timestamp()) if record.event_start_at is not None else None,
                        "event_end_at": int(record.event_end_at.timestamp()) if record.event_end_at is not None else None,
                    }
                ),
            }
            for record in records
        ]
        index.upsert(vectors=vectors)

    def _fetch_centroids(self, index, node_ids: Sequence[str]) -> dict[str, list[float]]:
        if not node_ids:
            return {}
        vectors: dict[str, list[float]] = {}
        for batch in _chunked(_stringify_ids(node_ids), _FETCH_BATCH_SIZE):
            response = index.fetch(ids=list(batch))
            payload = _field(response, "vectors", {})
            vectors.update({str(node_id): list(_field(vector, "values", [])) for node_id, vector in payload.items()})
        return vectors

    def _query_centroids(self, index, embedding: list[float], *, top_k: int) -> list[NodeMatch]:
        response = index.query(vector=embedding, top_k=top_k, include_metadata=True)
        matches = _field(response, "matches", [])
        return [
            NodeMatch(
                node_id=str(_field(match, "id", "")),
                similarity_score=float(_field(match, "score", 0.0)),
                metadata=dict(_field(match, "metadata", {}) or {}),
            )
            for match in matches
        ]

    def _delete_centroids(self, index, node_ids: Sequence[str]) -> None:
        if not node_ids:
            return
        for batch in _chunked(_stringify_ids(node_ids), _FETCH_BATCH_SIZE):
            index.delete(ids=list(batch))


def _field(value: Any, name: str, default: Any) -> Any:
    if hasattr(value, name):
        return getattr(value, name)
    if isinstance(value, dict):
        return value.get(name, default)
    return default


def _chunked(items: Sequence[str], size: int) -> list[Sequence[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _compact_metadata(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _stringify_ids(values: Sequence[object]) -> list[str]:
    return [str(value) for value in values]


def _chunk_vectors_by_bytes(vectors: Sequence[dict[str, Any]], *, max_bytes: int) -> list[list[dict[str, Any]]]:
    if not vectors:
        return []
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_bytes = 0
    for vector in vectors:
        vector_bytes = len(json.dumps(vector, separators=(",", ":")))
        if current and current_bytes + vector_bytes > max_bytes:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(vector)
        current_bytes += vector_bytes
    if current:
        batches.append(current)
    return batches
