from __future__ import annotations

import re
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

DEFAULT_TOPIC_EXTRA_STOPWORDS = {
    "presstv",
    "press",
    "tv",
    "via",
    "also",
    "one",
    "two",
    "says",
    "said",
    "say",
    "report",
    "reports",
    "reported",
    "breaking",
    "video",
    "footage",
    "image",
    "images",
    "photo",
    "photos",
    "telegram",
    "channel",
}

_TOPIC_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_TOPIC_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)
_TOPIC_TRAILING_DELIMITER_RE = re.compile(r"(?:\s*\n?---\s*)+$")


@dataclass(frozen=True)
class TopicModelingConfig:
    umap_neighbors: int = 15
    umap_min_dist: float = 0.1
    min_cluster_size: int = 15
    min_samples: int = 5
    keywords_per_topic: int = 10
    label_keywords: int = 3
    ngram_range: tuple[int, int] = (1, 2)
    label_overrides: dict[int, str] = field(default_factory=dict)
    extra_stopwords: set[str] = field(default_factory=lambda: set(DEFAULT_TOPIC_EXTRA_STOPWORDS))


@dataclass(frozen=True)
class TopicModelingResult:
    topic_messages_df: pd.DataFrame
    topic_keyword_df: pd.DataFrame
    topic_summary_df: pd.DataFrame
    topic_prevalence_df: pd.DataFrame
    topic_daily_share_df: pd.DataFrame
    topic_daily_share_long_df: pd.DataFrame
    topic_example_messages_df: pd.DataFrame
    topic_prep_summary_df: pd.DataFrame
    topic_scatter_fig: Any
    topic_prevalence_fig: Any
    topic_time_fig: Any
    topic_label_lookup: dict[int, str]
    topic_color_map: dict[str, str]
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "topic_messages_df": self.topic_messages_df,
            "topic_keyword_df": self.topic_keyword_df,
            "topic_summary_df": self.topic_summary_df,
            "topic_prevalence_df": self.topic_prevalence_df,
            "topic_daily_share_df": self.topic_daily_share_df,
            "topic_daily_share_long_df": self.topic_daily_share_long_df,
            "topic_example_messages_df": self.topic_example_messages_df,
            "topic_prep_summary_df": self.topic_prep_summary_df,
            "topic_scatter_fig": self.topic_scatter_fig,
            "topic_prevalence_fig": self.topic_prevalence_fig,
            "topic_time_fig": self.topic_time_fig,
            "topic_label_lookup": self.topic_label_lookup,
            "topic_color_map": self.topic_color_map,
        }


def clean_topic_text(text: str) -> str:
    cleaned = _TOPIC_URL_RE.sub(" ", text or "")
    cleaned = _TOPIC_TRAILING_DELIMITER_RE.sub(" ", cleaned)
    cleaned = _TOPIC_EMOJI_RE.sub(" ", cleaned)
    cleaned = re.sub(r"@\w+", " ", cleaned)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"^[\s\-–—•▪●▶►◆◇■□▲△▼▽:|]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -–—•:|")


def _compute_topic_keywords(topic_frame: pd.DataFrame, config: TopicModelingConfig) -> tuple[dict[int, list[str]], pd.DataFrame]:
    try:
        import numpy as np
        from sklearn.feature_extraction import text as sklearn_text
        from sklearn.feature_extraction.text import CountVectorizer
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Topic keyword extraction requires scikit-learn and numpy. "
            "Install notebook extras like: pip install umap-learn hdbscan plotly scikit-learn"
        ) from exc

    clustered = topic_frame.loc[topic_frame["topic_id"] != -1, ["topic_id", "topic_text"]].copy()
    if clustered.empty:
        return {}, pd.DataFrame(columns=["topic_id", "rank", "keyword", "score"])

    per_topic_docs = clustered.groupby("topic_id")["topic_text"].apply(lambda values: " ".join(values)).sort_index()
    stop_words = sorted(set(sklearn_text.ENGLISH_STOP_WORDS).union(config.extra_stopwords))
    vectorizer = CountVectorizer(
        stop_words=stop_words,
        ngram_range=config.ngram_range,
        max_features=5000,
        token_pattern=r"(?u)\b[a-z][a-z-]{1,}\b",
    )
    try:
        term_counts = vectorizer.fit_transform(per_topic_docs.tolist()).astype(float)
    except ValueError:
        return {}, pd.DataFrame(columns=["topic_id", "rank", "keyword", "score"])

    counts = term_counts.toarray()
    total_terms = counts.sum()
    words_per_topic = counts.sum(axis=1, keepdims=True)
    words_per_topic[words_per_topic == 0] = 1.0
    tf = counts / words_per_topic
    term_freq = counts.sum(axis=0, keepdims=True)
    idf = np.log((1 + total_terms) / (1 + term_freq)) + 1.0
    ctfidf = tf * idf
    features = vectorizer.get_feature_names_out()

    keyword_lookup: dict[int, list[str]] = {}
    keyword_rows: list[dict[str, Any]] = []
    for row_index, topic_id in enumerate(per_topic_docs.index):
        ranked_indices = np.argsort(ctfidf[row_index])[::-1]
        keywords = [features[idx] for idx in ranked_indices if ctfidf[row_index, idx] > 0][: config.keywords_per_topic]
        keyword_lookup[int(topic_id)] = keywords

        rank = 1
        for idx in ranked_indices:
            score = float(ctfidf[row_index, idx])
            if score <= 0:
                continue
            keyword_rows.append(
                {
                    "topic_id": int(topic_id),
                    "rank": rank,
                    "keyword": features[idx],
                    "score": score,
                }
            )
            rank += 1
            if rank > config.keywords_per_topic:
                break

    return keyword_lookup, pd.DataFrame(keyword_rows)


def _make_topic_label(topic_id: int, keyword_lookup: dict[int, list[str]], config: TopicModelingConfig) -> str:
    if topic_id == -1:
        return "Noise / Mixed"
    if topic_id in config.label_overrides:
        return config.label_overrides[topic_id]
    keywords = keyword_lookup.get(topic_id, [])[: config.label_keywords]
    return f"Topic {topic_id}: {', '.join(keywords)}" if keywords else f"Topic {topic_id}"


def _ordered_topic_ids(topic_frame: pd.DataFrame) -> list[int]:
    counts = topic_frame["topic_id"].value_counts()
    ordered = [int(topic_id) for topic_id in counts.index if int(topic_id) != -1]
    if -1 in counts.index:
        ordered.append(-1)
    return ordered


def _prepare_topic_messages(
    translated_messages: Sequence[RawMessage],
    embedding_lookup: dict[tuple[int, int], Sequence[float]],
) -> tuple[pd.DataFrame, Any]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Topic modeling requires numpy. Install notebook extras like: pip install umap-learn hdbscan plotly scikit-learn"
        ) from exc

    topic_records: list[dict[str, Any]] = []
    topic_vectors: list[Sequence[float]] = []
    for message in translated_messages:
        key = (message.channel_id, message.message_id)
        vector = embedding_lookup.get(key)
        if vector is None:
            continue

        original_text = (preferred_message_text(message) or "").strip()
        cleaned_topic_text = clean_topic_text(original_text)
        if not cleaned_topic_text:
            continue

        timestamp = pd.to_datetime(message.timestamp, utc=True)
        topic_records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "original_text": original_text,
                "topic_text": cleaned_topic_text,
                "message_length": len(original_text),
                "clean_text_length": len(cleaned_topic_text),
                "embedding_dim": len(vector),
            }
        )
        topic_vectors.append(vector)

    topic_messages_df = pd.DataFrame(topic_records).sort_values("timestamp").reset_index(drop=True)
    if topic_messages_df.empty:
        raise RuntimeError("No topic-ready messages are available. Run Sections 4-5 first.")
    if len(topic_messages_df) < 5:
        raise RuntimeError("Topic modeling needs at least 5 topic-ready messages to run UMAP and HDBSCAN.")

    topic_embedding_matrix = np.asarray(topic_vectors, dtype=np.float32)
    return topic_messages_df, topic_embedding_matrix


def run_topic_modeling_analysis(
    translated_messages: Sequence[RawMessage],
    embedding_lookup: dict[tuple[int, int], Sequence[float]],
    *,
    channel_label: str,
    config: TopicModelingConfig | None = None,
) -> TopicModelingResult:
    config = config or TopicModelingConfig()
    started_at = time.monotonic()

    try:
        import hdbscan
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Topic modeling requires hdbscan. Install notebook extras like: pip install umap-learn hdbscan plotly scikit-learn"
        ) from exc
    try:
        import plotly.express as px
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Topic modeling requires plotly. Install notebook extras like: pip install umap-learn hdbscan plotly scikit-learn"
        ) from exc
    try:
        import umap
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Topic modeling requires umap-learn. Install notebook extras like: pip install umap-learn hdbscan plotly scikit-learn"
        ) from exc
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Topic modeling requires numpy. Install notebook extras like: pip install umap-learn hdbscan plotly scikit-learn"
        ) from exc

    topic_messages_df, topic_embedding_matrix = _prepare_topic_messages(translated_messages, embedding_lookup)

    effective_neighbors = min(config.umap_neighbors, max(2, len(topic_messages_df) - 1))
    effective_min_cluster_size = (
        config.min_cluster_size
        if len(topic_messages_df) >= config.min_cluster_size
        else max(2, len(topic_messages_df) // 2)
    )
    effective_min_samples = min(config.min_samples, max(1, effective_min_cluster_size - 1))

    topic_prep_summary_df = pd.DataFrame(
        [
            {
                "messages_ready": len(topic_messages_df),
                "embedding_dim": int(topic_embedding_matrix.shape[1]),
                "start": topic_messages_df["timestamp"].min(),
                "end": topic_messages_df["timestamp"].max(),
                "messages_using_translation": int(topic_messages_df["used_translation"].sum()),
            }
        ]
    )

    topic_umap_model = umap.UMAP(
        n_components=2,
        n_neighbors=effective_neighbors,
        min_dist=config.umap_min_dist,
        metric="cosine",
        random_state=42,
    )
    topic_coords_2d = topic_umap_model.fit_transform(topic_embedding_matrix)

    topic_clusterer = hdbscan.HDBSCAN(
        min_cluster_size=effective_min_cluster_size,
        min_samples=effective_min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    topic_labels = topic_clusterer.fit_predict(topic_coords_2d)
    topic_probabilities = getattr(topic_clusterer, "probabilities_", np.ones(len(topic_labels)))

    topic_messages_df = topic_messages_df.copy()
    topic_messages_df["umap_x"] = topic_coords_2d[:, 0]
    topic_messages_df["umap_y"] = topic_coords_2d[:, 1]
    topic_messages_df["topic_id"] = topic_labels.astype(int)
    topic_messages_df["cluster_probability"] = topic_probabilities.astype(float)

    topic_counts = topic_messages_df["topic_id"].value_counts()
    topic_messages_df["topic_message_count"] = topic_messages_df["topic_id"].map(topic_counts).astype(int)

    topic_keyword_lookup, topic_keyword_df = _compute_topic_keywords(topic_messages_df, config)
    topic_order_ids = _ordered_topic_ids(topic_messages_df)
    topic_label_lookup = {
        topic_id: _make_topic_label(topic_id, topic_keyword_lookup, config)
        for topic_id in topic_order_ids
    }
    topic_label_order = [topic_label_lookup[topic_id] for topic_id in topic_order_ids]

    topic_messages_df["topic_label"] = topic_messages_df["topic_id"].map(topic_label_lookup)
    topic_messages_df["topic_keywords"] = topic_messages_df["topic_id"].map(
        lambda topic_id: ", ".join(topic_keyword_lookup.get(int(topic_id), [])[: config.keywords_per_topic])
        if int(topic_id) != -1
        else "mixed / outlier"
    )
    topic_messages_df["topic_keyword_preview"] = topic_messages_df["topic_id"].map(
        lambda topic_id: ", ".join(topic_keyword_lookup.get(int(topic_id), [])[: config.label_keywords])
        if int(topic_id) != -1
        else "outlier / mixed"
    )
    topic_messages_df["timestamp_label"] = topic_messages_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M UTC")
    topic_messages_df["hover_text"] = topic_messages_df["original_text"].map(
        lambda text: textwrap.shorten((text or "").replace("\n", " "), width=100, placeholder="...")
    )

    topic_summary_df = (
        topic_messages_df.groupby(["topic_id", "topic_label"], as_index=False)
        .agg(
            message_count=("message_id", "size"),
            mean_cluster_probability=("cluster_probability", "mean"),
            mean_message_length=("message_length", "mean"),
            first_seen=("timestamp", "min"),
            last_seen=("timestamp", "max"),
        )
    )
    topic_summary_df["top_keywords"] = topic_summary_df["topic_id"].map(
        lambda topic_id: ", ".join(topic_keyword_lookup.get(int(topic_id), [])[: config.keywords_per_topic])
        if int(topic_id) != -1
        else ""
    )
    topic_summary_df["keyword_preview"] = topic_summary_df["topic_id"].map(
        lambda topic_id: ", ".join(topic_keyword_lookup.get(int(topic_id), [])[: config.label_keywords])
        if int(topic_id) != -1
        else "outlier / mixed"
    )
    topic_summary_df["mean_cluster_probability"] = topic_summary_df["mean_cluster_probability"].round(3)
    topic_summary_df["mean_message_length"] = topic_summary_df["mean_message_length"].round(1)
    topic_summary_df["topic_rank"] = topic_summary_df["topic_id"].map(
        {topic_id: rank for rank, topic_id in enumerate(topic_order_ids)}
    )
    topic_summary_df = topic_summary_df.sort_values("topic_rank").drop(columns="topic_rank").reset_index(drop=True)

    topic_prevalence_df = topic_summary_df[
        ["topic_id", "topic_label", "message_count", "keyword_preview", "top_keywords"]
    ].copy()

    topic_day_index = pd.date_range(
        topic_messages_df["timestamp"].min().floor("D"),
        topic_messages_df["timestamp"].max().floor("D"),
        freq="D",
        tz="UTC",
    )
    topic_daily_counts_df = (
        topic_messages_df.assign(day=topic_messages_df["timestamp"].dt.floor("D"))
        .groupby(["day", "topic_label"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=topic_day_index, columns=topic_label_order, fill_value=0)
    )
    topic_daily_share_df = topic_daily_counts_df.div(
        topic_daily_counts_df.sum(axis=1).replace(0, pd.NA),
        axis=0,
    ).fillna(0.0)
    topic_daily_share_long_df = (
        topic_daily_share_df.reset_index()
        .melt(id_vars="index", var_name="topic_label", value_name="share")
        .rename(columns={"index": "date"})
    )
    topic_daily_share_long_df["share_pct"] = 100 * topic_daily_share_long_df["share"]

    topic_example_messages_df = (
        topic_messages_df.sort_values(
            ["topic_id", "cluster_probability", "message_length"],
            ascending=[True, False, False],
        )
        .groupby("topic_id")
        .head(3)
        [["topic_label", "timestamp", "cluster_probability", "hover_text"]]
        .rename(columns={"hover_text": "message_preview"})
        .reset_index(drop=True)
    )

    topic_palette = (
        px.colors.qualitative.Safe
        + px.colors.qualitative.Bold
        + px.colors.qualitative.Vivid
        + px.colors.qualitative.Set3
    )
    topic_color_map: dict[str, str] = {}
    palette_index = 0
    for topic_id in topic_order_ids:
        label = topic_label_lookup[topic_id]
        if topic_id == -1:
            topic_color_map[label] = "#b0b0b0"
        else:
            topic_color_map[label] = topic_palette[palette_index % len(topic_palette)]
            palette_index += 1

    topic_scatter_fig = px.scatter(
        topic_messages_df,
        x="umap_x",
        y="umap_y",
        color="topic_label",
        size="message_length",
        size_max=22,
        opacity=0.82,
        category_orders={"topic_label": topic_label_order},
        color_discrete_map=topic_color_map,
        custom_data=[
            "topic_label",
            "timestamp_label",
            "topic_keyword_preview",
            "cluster_probability",
            "message_length",
            "hover_text",
        ],
        title=f"{channel_label} Telegram - Topic Modeling Landscape (UMAP + HDBSCAN)",
        template="plotly_white",
    )
    topic_scatter_fig.update_traces(
        marker={"line": {"width": 0.5, "color": "white"}},
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Timestamp: %{customdata[1]}<br>"
            "Keywords: %{customdata[2]}<br>"
            "Cluster probability: %{customdata[3]:.2f}<br>"
            "Message length: %{customdata[4]} chars<br><br>"
            "%{customdata[5]}<extra></extra>"
        ),
    )
    topic_scatter_fig.update_layout(
        legend_title_text="Topic",
        xaxis_title="UMAP 1",
        yaxis_title="UMAP 2",
        height=650,
        margin={"l": 30, "r": 30, "t": 70, "b": 30},
    )

    topic_prevalence_fig = px.bar(
        topic_prevalence_df,
        x="message_count",
        y="topic_label",
        orientation="h",
        color="topic_label",
        category_orders={"topic_label": topic_label_order},
        color_discrete_map=topic_color_map,
        text="keyword_preview",
        title=f"{channel_label} Telegram - Topic Prevalence",
        template="plotly_white",
    )
    topic_prevalence_fig.update_layout(
        showlegend=False,
        height=max(400, 120 + 45 * len(topic_prevalence_df)),
        yaxis={"categoryorder": "array", "categoryarray": list(reversed(topic_label_order))},
        margin={"l": 30, "r": 30, "t": 70, "b": 30},
    )
    topic_prevalence_fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Messages: %{x}<br>Keywords: %{text}<extra></extra>",
    )

    topic_time_fig = px.area(
        topic_daily_share_long_df,
        x="date",
        y="share_pct",
        color="topic_label",
        category_orders={"topic_label": topic_label_order},
        color_discrete_map=topic_color_map,
        title=f"{channel_label} Telegram - Topic Proportion Over Time",
        template="plotly_white",
    )
    topic_time_fig.update_layout(
        legend_title_text="Topic",
        xaxis_title="Date (UTC)",
        yaxis_title="Share of daily messages",
        height=500,
        margin={"l": 30, "r": 30, "t": 70, "b": 30},
    )
    topic_time_fig.update_yaxes(range=[0, 100], ticksuffix="%")
    topic_time_fig.update_traces(
        hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Share: %{y:.1f}%<extra></extra>"
    )

    return TopicModelingResult(
        topic_messages_df=topic_messages_df,
        topic_keyword_df=topic_keyword_df,
        topic_summary_df=topic_summary_df,
        topic_prevalence_df=topic_prevalence_df,
        topic_daily_share_df=topic_daily_share_df,
        topic_daily_share_long_df=topic_daily_share_long_df,
        topic_example_messages_df=topic_example_messages_df,
        topic_prep_summary_df=topic_prep_summary_df,
        topic_scatter_fig=topic_scatter_fig,
        topic_prevalence_fig=topic_prevalence_fig,
        topic_time_fig=topic_time_fig,
        topic_label_lookup=topic_label_lookup,
        topic_color_map=topic_color_map,
        analysis_seconds=time.monotonic() - started_at,
    )
