import numpy as np
import pandas as pd
import pytest

pytest.importorskip("umap")
pytest.importorskip("hdbscan")

from telegram_scraper.analysis import topics
from telegram_scraper.analysis.topics import (
    TopicModelingConfig,
    fit_joint_topics,
    label_topics,
    stability_summary,
    topic_stability,
)

CONFIG = TopicModelingConfig(min_cluster_size=10, min_samples=3, umap_neighbors=10, keywords_per_topic=5)
VOCAB = {0: "ceasefire hostages talks", 1: "missile strike drone", 2: "election coalition knesset"}


def blob_data():
    rng = np.random.default_rng(0)
    centers = rng.normal(0, 6, size=(3, 16))
    vectors, rows = [], []
    for blob in range(3):
        for index in range(60):
            vectors.append(centers[blob] + rng.normal(0, 0.5, 16))
            channel = "alpha" if index % 3 else "beta"  # blob content is shared by both channels
            rows.append({"channel_slug": channel, "blob": blob, "text": f"{VOCAB[blob]} update {index}"})
    return pd.DataFrame(rows, index=np.arange(1000, 1180)), np.asarray(vectors, dtype=np.float32)


def test_fit_joint_topics_recovers_blobs():
    df, embeddings = blob_data()
    result = fit_joint_topics(df, embeddings, config=CONFIG)

    assert result.n_topics == 3
    assignments = result.assignments_df
    assert assignments.index.equals(df.index)
    assert list(assignments.columns) == ["topic_id", "topic_label", "probability", "x2d", "y2d"]
    # each true blob maps to exactly one topic
    crosstab = pd.crosstab(df["blob"], assignments["topic_id"])
    assert (crosstab.gt(0).sum(axis=1) == 1).all()

    summary = result.topic_summary_df
    assert {"topic_id", "label", "top_keywords", "n", "share"} <= set(summary.columns)
    assert summary["n"].sum() == len(df)
    assert summary["share"].sum() == pytest.approx(1.0)
    all_keywords = " ".join(summary["top_keywords"])
    assert "ceasefire" in all_keywords and "missile" in all_keywords and "knesset" in all_keywords

    share = result.share_by_group_df
    per_group = share.groupby("channel_slug")["share"].sum()
    assert per_group.to_numpy() == pytest.approx(1.0)
    assert share.groupby("channel_slug")["n"].sum().to_dict() == {"alpha": 120, "beta": 60}
    assert (share["group_n"] == share.groupby("channel_slug")["n"].transform("sum")).all()
    clustered = share[share["topic_id"] != -1].groupby("channel_slug")["share_of_clustered"].sum()
    assert clustered.to_numpy() == pytest.approx(1.0)
    noise = result.noise_share_by_group.set_index("channel_slug")
    assert set(noise.index) == {"alpha", "beta"}
    assert (noise["n"] == pd.Series({"alpha": 120, "beta": 60})).all()


def test_same_seed_gives_identical_assignments():
    df, embeddings = blob_data()
    first = fit_joint_topics(df, embeddings, config=CONFIG)
    second = fit_joint_topics(df, embeddings, config=CONFIG)
    pd.testing.assert_frame_equal(first.assignments_df, second.assignments_df)


def test_hdbscan_never_sees_plot_coordinates(monkeypatch):
    import hdbscan

    seen_dims = []
    original = hdbscan.HDBSCAN.fit_predict

    def spy(self, X, *args, **kwargs):
        seen_dims.append(np.asarray(X).shape[1])
        return original(self, X, *args, **kwargs)

    monkeypatch.setattr(hdbscan.HDBSCAN, "fit_predict", spy)
    df, embeddings = blob_data()
    result = fit_joint_topics(df, embeddings, config=CONFIG)
    assert seen_dims == [CONFIG.cluster_dims] and CONFIG.cluster_dims != 2
    assert result.assignments_df[["x2d", "y2d"]].shape[1] == 2

    seen_dims.clear()
    fit_joint_topics(df, embeddings, config=TopicModelingConfig(**{**CONFIG.__dict__, "cluster_dims": 2}))
    assert seen_dims == [2]


def test_topic_stability_blobs_are_stable():
    df, embeddings = blob_data()
    stability = topic_stability(df, embeddings, config=CONFIG, seeds=(0, 1, 2))
    assert len(stability) == 3
    assert set(stability.columns) >= {"seed_a", "seed_b", "ari", "n_topics_a", "n_topics_b", "n_shared"}
    assert (stability["ari"] > 0.95).all()
    summary = stability.attrs["summary"]
    assert summary == stability_summary(stability)
    assert summary["min_ari"] <= summary["mean_ari"] <= 1.0
    assert summary["min_topics"] == summary["max_topics"] == 3
    again = topic_stability(df, embeddings, config=CONFIG, seeds=(0, 1, 2))
    pd.testing.assert_frame_equal(stability, again)


def test_shape_mismatch_and_seed_validation():
    df, embeddings = blob_data()
    with pytest.raises(ValueError):
        fit_joint_topics(df, embeddings[:-1], config=CONFIG)
    with pytest.raises(ValueError):
        topic_stability(df, embeddings, config=CONFIG, seeds=(0,))


def test_label_topics_overrides():
    summary = pd.DataFrame({"topic_id": [0, 1, -1], "label": ["Topic 0: a", "Topic 1: b", "Noise / Mixed"], "n": [5, 4, 1]})
    relabeled = label_topics(summary, {1: "Missiles"})
    assert relabeled["label"].tolist() == ["Topic 0: a", "Missiles", "Noise / Mixed"]
    assert summary["label"].tolist()[1] == "Topic 1: b"  # input untouched
    with pytest.raises(KeyError):
        label_topics(summary, {9: "nope"})
    long_df = pd.DataFrame({"topic_id": [0, 1], "topic_label": ["x", "y"]})
    assert label_topics(long_df, {0: "Z"})["topic_label"].tolist() == ["Z", "y"]


def test_config_defaults_backward_compatible():
    config = TopicModelingConfig()
    assert (config.cluster_dims, config.random_state, config.cluster_selection_method) == (5, 42, "eom")
    assert hasattr(topics, "run_topic_modeling_analysis")


def test_run_topic_modeling_analysis_still_works_and_clusters_in_cluster_dims(monkeypatch):
    pytest.importorskip("plotly")
    from datetime import datetime, timedelta, timezone

    import hdbscan

    from telegram_scraper.analysis import run_topic_modeling_analysis
    from telegram_scraper.notebook_pipeline import RawMessage

    df, embeddings = blob_data()
    start = datetime(2026, 4, 6, tzinfo=timezone.utc)
    messages = [
        RawMessage(
            channel_id=1,
            message_id=position,
            timestamp=start + timedelta(hours=position),
            sender_id=None,
            sender_name=None,
            text=row.text,
        )
        for position, row in enumerate(df.itertuples())
    ]
    lookup = {(1, position): embeddings[position] for position in range(len(messages))}

    seen_dims = []
    original = hdbscan.HDBSCAN.fit_predict
    monkeypatch.setattr(
        hdbscan.HDBSCAN,
        "fit_predict",
        lambda self, X, *a, **k: (seen_dims.append(np.asarray(X).shape[1]), original(self, X, *a, **k))[1],
    )
    result = run_topic_modeling_analysis(messages, lookup, channel_label="Test", config=CONFIG)
    assert seen_dims == [CONFIG.cluster_dims]
    assert {"umap_x", "umap_y", "topic_id"} <= set(result.topic_messages_df.columns)
    assert (result.topic_summary_df["topic_id"] != -1).sum() == 3
