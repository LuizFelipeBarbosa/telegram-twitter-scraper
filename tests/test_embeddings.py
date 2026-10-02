import sys
import types

import numpy as np
import pandas as pd
import pytest

from telegram_scraper.analysis.embeddings import LocalEmbedder, embed_frame


class FakeSentenceTransformer:
    instances = 0
    encoded_batches: list = []

    def __init__(self, model_name):
        type(self).instances += 1
        self.model_name = model_name

    def encode(self, texts, batch_size, normalize_embeddings, show_progress_bar, convert_to_numpy):
        type(self).encoded_batches.append(list(texts))
        vectors = np.array([[len(text), sum(map(ord, text)) % 97, 1.0] for text in texts], dtype=np.float32)
        if normalize_embeddings:
            vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors


@pytest.fixture(autouse=True)
def fake_sentence_transformers(monkeypatch):
    FakeSentenceTransformer.instances = 0
    FakeSentenceTransformer.encoded_batches = []
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)


def test_embed_texts_lazy_load_and_normalised():
    embedder = LocalEmbedder()
    assert FakeSentenceTransformer.instances == 0
    vectors = embedder.embed_texts(["hello", "world!", "hello"])
    assert FakeSentenceTransformer.instances == 1
    assert vectors.shape == (3, 3)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    assert np.array_equal(vectors[0], vectors[2])
    # duplicates are only encoded once
    assert FakeSentenceTransformer.encoded_batches == [["hello", "world!"]]


def test_embed_frame_aligned_and_handles_missing_text():
    df = pd.DataFrame({"text": ["a", None, "ccc"]}, index=[10, 20, 30])
    vectors = LocalEmbedder().embed_frame(df)
    assert vectors.shape[0] == 3
    assert np.array_equal(embed_frame(df, embedder=LocalEmbedder()), vectors)


def test_disk_cache_reuses_vectors_without_loading_model(tmp_path):
    first = LocalEmbedder(cache_dir=tmp_path)
    expected = first.embed_texts(["alpha", "beta"])
    assert first.cache_path.exists()

    FakeSentenceTransformer.instances = 0
    FakeSentenceTransformer.encoded_batches = []
    second = LocalEmbedder(cache_dir=tmp_path)
    again = second.embed_texts(["beta", "alpha"])
    assert FakeSentenceTransformer.instances == 0
    assert np.array_equal(again, expected[::-1])

    mixed = second.embed_texts(["alpha", "gamma"])
    assert FakeSentenceTransformer.encoded_batches == [["gamma"]]
    assert np.array_equal(mixed[0], expected[0])

    third = LocalEmbedder(cache_dir=tmp_path)  # new instance sees the updated cache
    FakeSentenceTransformer.encoded_batches = []
    third.embed_texts(["gamma"])
    assert FakeSentenceTransformer.encoded_batches == []


def test_cache_is_keyed_by_model(tmp_path):
    LocalEmbedder("model-a", cache_dir=tmp_path).embed_texts(["x"])
    FakeSentenceTransformer.encoded_batches = []
    LocalEmbedder("model-b", cache_dir=tmp_path).embed_texts(["x"])
    assert FakeSentenceTransformer.encoded_batches == [["x"]]


def test_empty_input():
    assert LocalEmbedder().embed_texts([]).shape[0] == 0
