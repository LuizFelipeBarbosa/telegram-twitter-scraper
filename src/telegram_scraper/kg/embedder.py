from __future__ import annotations

from typing import Sequence


_EMBED_BATCH_SIZE = 100


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
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError("openai is not installed. Install project dependencies before using KG commands.") from exc
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
