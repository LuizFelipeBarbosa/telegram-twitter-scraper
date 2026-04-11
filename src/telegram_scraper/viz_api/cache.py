from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from fastapi.encoders import jsonable_encoder

T = TypeVar("T")


class RedisResponseCache:
    def __init__(self, redis_url: str, *, namespace: str = "viz"):
        self.namespace = namespace
        self._client = None
        if not redis_url:
            return
        try:
            import redis
        except ImportError:  # pragma: no cover - runtime dependency guard
            return
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def _key(self, name: str, params: Mapping[str, Any]) -> str:
        digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"{self.namespace}:{name}:{digest}"

    def get_or_set(self, name: str, params: Mapping[str, Any], *, ttl_seconds: int, loader: Callable[[], T]) -> T:
        if self._client is None:
            return loader()
        key = self._key(name, params)
        try:
            cached = self._client.get(key)
            if cached is not None:
                return json.loads(cached)
        except Exception:
            return loader()

        value = loader()
        try:
            encoded = json.dumps(jsonable_encoder(value), sort_keys=True, default=str)
            self._client.setex(key, ttl_seconds, encoded)
        except Exception:
            return value
        return value
