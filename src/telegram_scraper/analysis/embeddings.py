from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def _text_key(model_name: str, text: str) -> str:
    return hashlib.sha1(f"{model_name}\x00{text}".encode("utf-8")).hexdigest()


class LocalEmbedder:
    """Local sentence-transformers embedder with an optional on-disk cache.

    The cache is a single ``.npz`` per model inside ``cache_dir`` holding sha1(model + text)
    keys and their vectors, so reruns reuse stored vectors and stay deterministic.
    The sentence-transformers model is only loaded when uncached texts need embedding.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL,
        batch_size: int = 64,
        normalize: bool = True,
        cache_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize = normalize
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._model: Any = None
        self._cache: dict[str, np.ndarray] | None = None

    # -- model -----------------------------------------------------------------
    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - exercised in notebook env
                raise ImportError(
                    "Local embeddings require sentence-transformers. Install with: pip install sentence-transformers"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        model = self._load_model()
        vectors = model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)

    # -- cache -----------------------------------------------------------------
    @property
    def cache_path(self) -> Path | None:
        if self.cache_dir is None:
            return None
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", self.model_name)
        suffix = "norm" if self.normalize else "raw"
        return self.cache_dir / f"embeddings_{slug}_{suffix}.npz"

    def _load_cache(self) -> dict[str, np.ndarray]:
        if self._cache is not None:
            return self._cache
        self._cache = {}
        path = self.cache_path
        if path is not None and path.exists():
            with np.load(path, allow_pickle=False) as data:
                keys = [str(key) for key in data["keys"]]
                vectors = data["vectors"]
            self._cache = {key: vectors[index] for index, key in enumerate(keys)}
        return self._cache

    def _save_cache(self) -> None:
        path = self.cache_path
        if path is None or not self._cache:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        keys = sorted(self._cache)
        vectors = np.stack([self._cache[key] for key in keys]).astype(np.float32)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".npz")
        os.close(fd)
        try:
            np.savez_compressed(tmp_name, keys=np.asarray(keys), vectors=vectors)
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)

    # -- public API ------------------------------------------------------------
    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        texts = ["" if text is None else str(text) for text in texts]
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        use_cache = self.cache_dir is not None
        cache = self._load_cache() if use_cache else {}
        keys = [_text_key(self.model_name, text) for text in texts]

        missing: dict[str, str] = {}
        for key, text in zip(keys, texts):
            if key not in cache and key not in missing:
                missing[key] = text

        fresh: dict[str, np.ndarray] = {}
        if missing:
            encoded = self._encode(list(missing.values()))
            fresh = {key: encoded[index] for index, key in enumerate(missing)}
            if use_cache:
                cache.update(fresh)
                self._save_cache()

        lookup = {**cache, **fresh}
        return np.stack([lookup[key] for key in keys]).astype(np.float32)

    def embed_frame(self, df: pd.DataFrame, text_col: str = "text") -> np.ndarray:
        return self.embed_texts(df[text_col].fillna("").astype(str).tolist())


def embed_frame(
    df: pd.DataFrame,
    text_col: str = "text",
    *,
    embedder: LocalEmbedder | None = None,
) -> np.ndarray:
    """Embed ``df[text_col]`` row-aligned with ``df`` using ``embedder`` (default bge-small)."""
    return (embedder or LocalEmbedder()).embed_frame(df, text_col=text_col)
