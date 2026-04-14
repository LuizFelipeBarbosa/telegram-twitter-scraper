from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

DEFAULT_MEDIA_COLOR = "#1f77b4"
DEFAULT_TEXT_ONLY_COLOR = "#ff7f0e"
DEFAULT_TERM_EXTRA_STOPWORDS = {
    "presstv",
    "press",
    "tv",
    "via",
    "also",
    "said",
    "says",
    "say",
    "report",
    "reports",
    "reported",
    "breaking",
    "watch",
    "video",
    "videos",
    "footage",
    "image",
    "images",
    "photo",
    "photos",
    "channel",
    "telegram",
}

_TEXT_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_TEXT_MENTION_RE = re.compile(r"@\w+")
_TEXT_TRAILING_DELIMITER_RE = re.compile(r"(?:\s*\n?---\s*)+$")
_TEXT_NON_ALPHA_RE = re.compile(r"[^a-z\s-]")

_SEGMENT_SUMMARY_COLUMNS = [
    "segment_label",
    "message_count",
    "message_share_pct",
    "text_messages",
    "text_message_share_pct",
    "media_only_messages",
    "mean_text_length",
    "median_text_length",
    "mean_sentiment_score",
    "median_sentiment_score",
    "messages_with_topics",
    "messages_with_frames",
]
_STAT_TEST_COLUMNS = [
    "metric",
    "test_type",
    "group_a",
    "group_b",
    "group_a_n",
    "group_b_n",
    "category_count",
    "statistic",
    "degrees_of_freedom",
    "p_value",
    "effect_size",
    "group_a_median",
    "group_b_median",
    "significant_0_05",
]
_HOURLY_DISTRIBUTION_COLUMNS = ["segment_label", "hour", "message_count", "message_share_pct"]
_TOPIC_DISTRIBUTION_COLUMNS = [
    "topic_label",
    "segment_label",
    "message_count",
    "segment_total",
    "message_share_pct",
    "total_count",
    "share_gap_pct_points",
    "sort_order",
]
_FRAME_DISTRIBUTION_COLUMNS = [
    "dominant_frame",
    "segment_label",
    "message_count",
    "segment_total",
    "message_share_pct",
    "total_count",
    "share_gap_pct_points",
    "sort_order",
]
_TFIDF_TERM_COLUMNS = [
    "segment_label",
    "rank",
    "term",
    "mean_tfidf",
    "other_segment_mean_tfidf",
    "lift_vs_other",
]
_ENTITY_DISTRIBUTION_COLUMNS = [
    "entity",
    "segment_label",
    "message_count",
    "segment_total",
    "message_share_pct",
    "total_count",
    "share_gap_pct_points",
    "sort_order",
]


@dataclass(frozen=True)
class MediaTextComparisonConfig:
    top_topics: int = 8
    top_frames: int = 8
    top_terms: int = 15
    top_entities: int = 15
    tfidf_max_features: int = 500
    term_ngram_range: tuple[int, int] = (1, 1)
    density_grid_points: int = 240
    density_bw_method: str | float | None = None
    media_label: str = "Media"
    text_only_label: str = "Text-only"
    media_color: str = DEFAULT_MEDIA_COLOR
    text_only_color: str = DEFAULT_TEXT_ONLY_COLOR
    violin_inner: str = "quart"
    extra_stopwords: set[str] = field(default_factory=lambda: set(DEFAULT_TERM_EXTRA_STOPWORDS))


@dataclass(frozen=True)
class MediaTextComparisonResult:
    media_text_messages_df: pd.DataFrame
    media_text_segment_summary_df: pd.DataFrame
    media_text_stat_tests_df: pd.DataFrame
    media_text_hourly_distribution_df: pd.DataFrame
    media_text_topic_distribution_df: pd.DataFrame
    media_text_frame_distribution_df: pd.DataFrame
    media_text_tfidf_terms_df: pd.DataFrame
    media_text_entity_distribution_df: pd.DataFrame
    media_text_summary_df: pd.DataFrame
    media_text_dashboard_fig: Any
    media_text_violin_fig: Any
    media_text_hour_density_fig: Any
    media_text_topic_fig: Any
    media_text_frame_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "media_text_messages_df": self.media_text_messages_df,
            "media_text_segment_summary_df": self.media_text_segment_summary_df,
            "media_text_stat_tests_df": self.media_text_stat_tests_df,
            "media_text_hourly_distribution_df": self.media_text_hourly_distribution_df,
            "media_text_topic_distribution_df": self.media_text_topic_distribution_df,
            "media_text_frame_distribution_df": self.media_text_frame_distribution_df,
            "media_text_tfidf_terms_df": self.media_text_tfidf_terms_df,
            "media_text_entity_distribution_df": self.media_text_entity_distribution_df,
            "media_text_summary_df": self.media_text_summary_df,
            "media_text_dashboard_fig": self.media_text_dashboard_fig,
            "media_text_violin_fig": self.media_text_violin_fig,
            "media_text_hour_density_fig": self.media_text_hour_density_fig,
            "media_text_topic_fig": self.media_text_topic_fig,
            "media_text_frame_fig": self.media_text_frame_fig,
        }


def _empty_df(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _segment_order(config: MediaTextComparisonConfig) -> list[str]:
    return [config.media_label, config.text_only_label]


def _segment_palette(config: MediaTextComparisonConfig) -> dict[str, str]:
    return {
        config.media_label: config.media_color,
        config.text_only_label: config.text_only_color,
    }


def _placeholder_axis(ax: Any, *, title: str, message: str) -> None:
    ax.set_title(title)
    ax.axis("off")
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        fontsize=10,
        color="#555555",
        wrap=True,
        transform=ax.transAxes,
    )


def _clean_term_text(text: str) -> str:
    cleaned = _TEXT_URL_RE.sub(" ", text or "")
    cleaned = _TEXT_MENTION_RE.sub(" ", cleaned)
    cleaned = _TEXT_TRAILING_DELIMITER_RE.sub(" ", cleaned)
    cleaned = cleaned.lower()
    cleaned = _TEXT_NON_ALPHA_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _prepare_media_text_messages(
    messages: Sequence[RawMessage],
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for message in messages:
        timestamp = pd.to_datetime(message.timestamp, utc=True)
        text = (preferred_message_text(message) or "").strip()
        has_media = bool(message.media_refs)
        records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "hour": timestamp.hour,
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "has_media": has_media,
                "segment_label": config.media_label if has_media else config.text_only_label,
                "is_media_only": bool(message.is_media_only),
                "text": text,
                "has_text": bool(text),
                "text_length": len(text),
                "raw_text": (message.text or "").strip(),
                "english_text": (message.english_text or "").strip(),
            }
        )

    media_text_messages_df = pd.DataFrame(records).sort_values(["timestamp", "message_id"]).reset_index(drop=True)
    if media_text_messages_df.empty:
        raise RuntimeError("No messages are available for the media-vs-text comparison. Run Section 3 first.")

    media_text_messages_df["segment_label"] = pd.Categorical(
        media_text_messages_df["segment_label"],
        categories=_segment_order(config),
        ordered=True,
    )
    return media_text_messages_df


def _merge_optional_columns(
    media_text_messages_df: pd.DataFrame,
    *,
    sentiment_emotion_df: pd.DataFrame | None,
    topic_messages_df: pd.DataFrame | None,
    rhetoric_messages_df: pd.DataFrame | None,
) -> pd.DataFrame:
    merged_df = media_text_messages_df.copy()

    if sentiment_emotion_df is not None and not sentiment_emotion_df.empty:
        sentiment_columns = [
            column
            for column in [
                "channel_id",
                "message_id",
                "sentiment_score",
                "dominant_sentiment",
                "dominant_emotion",
                "sentiment_confidence",
                "emotion_confidence",
            ]
            if column in sentiment_emotion_df.columns
        ]
        if {"channel_id", "message_id"}.issubset(sentiment_columns):
            merged_df = merged_df.merge(
                sentiment_emotion_df[sentiment_columns].drop_duplicates(subset=["channel_id", "message_id"]),
                on=["channel_id", "message_id"],
                how="left",
            )

    if topic_messages_df is not None and not topic_messages_df.empty:
        topic_columns = [
            column
            for column in [
                "channel_id",
                "message_id",
                "topic_id",
                "topic_label",
                "topic_keywords",
                "cluster_probability",
            ]
            if column in topic_messages_df.columns
        ]
        if {"channel_id", "message_id"}.issubset(topic_columns):
            merged_df = merged_df.merge(
                topic_messages_df[topic_columns].drop_duplicates(subset=["channel_id", "message_id"]),
                on=["channel_id", "message_id"],
                how="left",
            )
            if "topic_label" in merged_df.columns:
                merged_df["dominant_topic"] = merged_df["topic_label"]

    if rhetoric_messages_df is not None and not rhetoric_messages_df.empty:
        rhetoric_columns = [
            column
            for column in [
                "channel_id",
                "message_id",
                "dominant_frame",
                "dominant_frame_slug",
                "confidence",
            ]
            if column in rhetoric_messages_df.columns
        ]
        if {"channel_id", "message_id"}.issubset(rhetoric_columns):
            rhetoric_merge_df = rhetoric_messages_df[rhetoric_columns].drop_duplicates(subset=["channel_id", "message_id"]).rename(
                columns={"confidence": "frame_confidence"}
            )
            merged_df = merged_df.merge(
                rhetoric_merge_df,
                on=["channel_id", "message_id"],
                how="left",
            )

    default_columns: dict[str, Any] = {
        "sentiment_score": float("nan"),
        "dominant_sentiment": pd.NA,
        "dominant_emotion": pd.NA,
        "sentiment_confidence": float("nan"),
        "emotion_confidence": float("nan"),
        "topic_id": pd.NA,
        "topic_label": pd.NA,
        "topic_keywords": pd.NA,
        "cluster_probability": float("nan"),
        "dominant_topic": pd.NA,
        "dominant_frame": pd.NA,
        "dominant_frame_slug": pd.NA,
        "frame_confidence": float("nan"),
    }
    for column, default_value in default_columns.items():
        if column not in merged_df.columns:
            merged_df[column] = default_value

    return merged_df


def _build_segment_summary(
    media_text_messages_df: pd.DataFrame,
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total_messages = max(1, len(media_text_messages_df))

    for segment_label in _segment_order(config):
        segment_df = media_text_messages_df.loc[media_text_messages_df["segment_label"] == segment_label].copy()
        message_count = int(len(segment_df))
        text_df = segment_df.loc[segment_df["has_text"]].copy()
        sentiment_series = text_df["sentiment_score"].dropna() if "sentiment_score" in text_df.columns else pd.Series(dtype=float)
        rows.append(
            {
                "segment_label": segment_label,
                "message_count": message_count,
                "message_share_pct": round(100 * message_count / total_messages, 1),
                "text_messages": int(text_df.shape[0]),
                "text_message_share_pct": round(100 * len(text_df) / max(1, message_count), 1),
                "media_only_messages": int(segment_df["is_media_only"].sum()),
                "mean_text_length": round(float(text_df["text_length"].mean()), 1) if not text_df.empty else float("nan"),
                "median_text_length": round(float(text_df["text_length"].median()), 1) if not text_df.empty else float("nan"),
                "mean_sentiment_score": round(float(sentiment_series.mean()), 3) if not sentiment_series.empty else float("nan"),
                "median_sentiment_score": round(float(sentiment_series.median()), 3) if not sentiment_series.empty else float("nan"),
                "messages_with_topics": int(segment_df["dominant_topic"].notna().sum()),
                "messages_with_frames": int(segment_df["dominant_frame"].notna().sum()),
            }
        )

    return pd.DataFrame(rows, columns=_SEGMENT_SUMMARY_COLUMNS)


def _build_stat_tests(
    media_text_messages_df: pd.DataFrame,
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    try:
        from scipy.stats import chi2_contingency, mannwhitneyu
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text comparison requires scipy. "
            "Install notebook extras like: pip install scipy matplotlib seaborn"
        ) from exc

    rows: list[dict[str, Any]] = []
    segment_order = _segment_order(config)

    def add_mann_whitney(metric: str, *, metric_label: str, filter_mask: pd.Series | None = None) -> None:
        mask = filter_mask if filter_mask is not None else pd.Series(True, index=media_text_messages_df.index)
        media_values = media_text_messages_df.loc[
            mask & media_text_messages_df["has_media"],
            metric,
        ].dropna()
        text_values = media_text_messages_df.loc[
            mask & ~media_text_messages_df["has_media"],
            metric,
        ].dropna()
        if media_values.empty or text_values.empty:
            return

        statistic, p_value = mannwhitneyu(media_values, text_values, alternative="two-sided")
        denominator = max(1, len(media_values) * len(text_values))
        rank_biserial = 1.0 - (2.0 * float(statistic) / denominator)
        rows.append(
            {
                "metric": metric_label,
                "test_type": "Mann-Whitney U",
                "group_a": segment_order[0],
                "group_b": segment_order[1],
                "group_a_n": int(len(media_values)),
                "group_b_n": int(len(text_values)),
                "category_count": pd.NA,
                "statistic": round(float(statistic), 3),
                "degrees_of_freedom": pd.NA,
                "p_value": round(float(p_value), 6),
                "effect_size": round(float(rank_biserial), 4),
                "group_a_median": round(float(media_values.median()), 3),
                "group_b_median": round(float(text_values.median()), 3),
                "significant_0_05": bool(p_value < 0.05),
            }
        )

    def add_chi_square(column: str, *, metric_label: str) -> None:
        subset_df = media_text_messages_df.loc[media_text_messages_df[column].notna(), ["has_media", column]].copy()
        if subset_df.empty:
            return

        contingency = pd.crosstab(subset_df["has_media"], subset_df[column])
        if contingency.shape[0] < 2 or contingency.shape[1] < 2:
            return

        chi2, p_value, degrees_of_freedom, _ = chi2_contingency(contingency)
        observation_count = contingency.to_numpy().sum()
        effect_denom = max(1, min(contingency.shape[0] - 1, contingency.shape[1] - 1))
        cramers_v = math.sqrt(float(chi2) / max(1, observation_count * effect_denom))
        rows.append(
            {
                "metric": metric_label,
                "test_type": "Chi-square",
                "group_a": segment_order[0],
                "group_b": segment_order[1],
                "group_a_n": int(subset_df["has_media"].sum()),
                "group_b_n": int((~subset_df["has_media"]).sum()),
                "category_count": int(contingency.shape[1]),
                "statistic": round(float(chi2), 3),
                "degrees_of_freedom": int(degrees_of_freedom),
                "p_value": round(float(p_value), 6),
                "effect_size": round(float(cramers_v), 4),
                "group_a_median": pd.NA,
                "group_b_median": pd.NA,
                "significant_0_05": bool(p_value < 0.05),
            }
        )

    add_mann_whitney("text_length", metric_label="Text length", filter_mask=media_text_messages_df["has_text"])
    add_mann_whitney("sentiment_score", metric_label="Sentiment score")

    add_chi_square("hour", metric_label="Posting hour distribution")
    add_chi_square("dominant_sentiment", metric_label="Dominant sentiment")
    add_chi_square("dominant_emotion", metric_label="Dominant emotion")
    add_chi_square("dominant_topic", metric_label="Dominant topic")
    add_chi_square("dominant_frame", metric_label="Dominant frame")

    return pd.DataFrame(rows, columns=_STAT_TEST_COLUMNS)


def _build_hourly_distribution(
    media_text_messages_df: pd.DataFrame,
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    counts_df = (
        media_text_messages_df.groupby(["segment_label", "hour"], observed=False)
        .size()
        .rename("message_count")
        .reset_index()
    )

    base_index = pd.MultiIndex.from_product(
        [_segment_order(config), range(24)],
        names=["segment_label", "hour"],
    )
    counts_df = (
        counts_df.set_index(["segment_label", "hour"])
        .reindex(base_index, fill_value=0)
        .reset_index()
    )
    segment_totals = counts_df.groupby("segment_label", observed=False)["message_count"].transform("sum")
    counts_df["message_share_pct"] = (
        100 * counts_df["message_count"] / segment_totals.replace(0, pd.NA)
    ).fillna(0.0).round(3)
    return counts_df[_HOURLY_DISTRIBUTION_COLUMNS].copy()


def _build_distribution_table(
    media_text_messages_df: pd.DataFrame,
    *,
    column: str,
    top_n: int,
    config: MediaTextComparisonConfig,
    output_columns: Sequence[str],
) -> pd.DataFrame:
    subset_df = media_text_messages_df.loc[media_text_messages_df[column].notna(), ["segment_label", column]].copy()
    if subset_df.empty:
        return _empty_df(output_columns)

    counts_df = (
        subset_df.groupby([column, "segment_label"], observed=False)
        .size()
        .rename("message_count")
        .reset_index()
    )
    value_order = counts_df.groupby(column, observed=False)["message_count"].sum().sort_values(ascending=False)
    value_order = value_order.head(top_n).index.tolist()
    if not value_order:
        return _empty_df(output_columns)

    base_index = pd.MultiIndex.from_product(
        [value_order, _segment_order(config)],
        names=[column, "segment_label"],
    )
    counts_df = counts_df.set_index([column, "segment_label"]).reindex(base_index, fill_value=0).reset_index()

    segment_totals = counts_df.groupby("segment_label", observed=False)["message_count"].transform("sum")
    counts_df["segment_total"] = segment_totals.astype(int)
    counts_df["message_share_pct"] = (
        100 * counts_df["message_count"] / segment_totals.replace(0, pd.NA)
    ).fillna(0.0)

    summary_df = (
        counts_df.pivot(index=column, columns="segment_label", values="message_share_pct")
        .reindex(index=value_order, columns=_segment_order(config), fill_value=0.0)
    )
    summary_df["total_count"] = counts_df.groupby(column, observed=False)["message_count"].sum().reindex(value_order).to_numpy()
    summary_df["share_gap_pct_points"] = summary_df[_segment_order(config)[0]] - summary_df[_segment_order(config)[1]]
    summary_df["sort_order"] = range(len(summary_df))
    summary_df = summary_df.reset_index()

    counts_df = counts_df.merge(
        summary_df[[column, "total_count", "share_gap_pct_points", "sort_order"]],
        on=column,
        how="left",
    )
    counts_df["message_share_pct"] = counts_df["message_share_pct"].round(3)
    counts_df["share_gap_pct_points"] = counts_df["share_gap_pct_points"].round(3)
    counts_df["sort_order"] = counts_df["sort_order"].astype(int)

    if column == "dominant_topic" and "topic_label" in output_columns and "topic_label" not in counts_df.columns:
        counts_df = counts_df.rename(columns={"dominant_topic": "topic_label"})
    return counts_df[list(output_columns)].copy()


def _build_tfidf_terms(
    media_text_messages_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    try:
        from sklearn.feature_extraction import text as sklearn_text
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text top-term comparison requires scikit-learn. "
            "Install notebook extras like: pip install scipy seaborn matplotlib scikit-learn"
        ) from exc

    text_df = media_text_messages_df.loc[media_text_messages_df["has_text"], ["segment_label", "text"]].copy()
    if text_df.empty or text_df["segment_label"].nunique() < 2:
        return _empty_df(_TFIDF_TERM_COLUMNS)

    text_df["clean_text"] = text_df["text"].map(_clean_term_text)
    text_df = text_df.loc[text_df["clean_text"].str.len() > 0].copy()
    if text_df.empty or text_df["segment_label"].nunique() < 2:
        return _empty_df(_TFIDF_TERM_COLUMNS)

    channel_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z]+", channel_label or "")
        if len(token) > 2
    }
    stop_words = sorted(set(sklearn_text.ENGLISH_STOP_WORDS).union(config.extra_stopwords).union(channel_tokens))
    vectorizer = TfidfVectorizer(
        stop_words=stop_words,
        max_features=config.tfidf_max_features,
        ngram_range=config.term_ngram_range,
        token_pattern=r"(?u)\b[a-z][a-z-]{2,}\b",
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(text_df["clean_text"].tolist())
    except ValueError:
        return _empty_df(_TFIDF_TERM_COLUMNS)

    feature_names = vectorizer.get_feature_names_out()
    if len(feature_names) == 0:
        return _empty_df(_TFIDF_TERM_COLUMNS)

    tfidf_scores_df = pd.DataFrame(tfidf_matrix.toarray(), columns=feature_names)
    tfidf_scores_df.insert(0, "segment_label", text_df["segment_label"].to_numpy())
    mean_scores_df = tfidf_scores_df.groupby("segment_label", observed=False).mean().reindex(_segment_order(config), fill_value=0.0)

    rows: list[dict[str, Any]] = []
    media_label, text_only_label = _segment_order(config)
    other_lookup = {
        media_label: text_only_label,
        text_only_label: media_label,
    }
    epsilon = 1e-9
    for segment_label in _segment_order(config):
        other_segment_label = other_lookup[segment_label]
        segment_scores = mean_scores_df.loc[segment_label]
        other_scores = mean_scores_df.loc[other_segment_label]
        top_terms = segment_scores[segment_scores > 0].sort_values(ascending=False).head(config.top_terms)
        for rank, (term, mean_tfidf) in enumerate(top_terms.items(), start=1):
            other_score = float(other_scores.get(term, 0.0))
            rows.append(
                {
                    "segment_label": segment_label,
                    "rank": rank,
                    "term": term,
                    "mean_tfidf": round(float(mean_tfidf), 6),
                    "other_segment_mean_tfidf": round(other_score, 6),
                    "lift_vs_other": round(float((float(mean_tfidf) + epsilon) / (other_score + epsilon)), 3),
                }
            )

    return pd.DataFrame(rows, columns=_TFIDF_TERM_COLUMNS)


def _build_entity_distribution(
    media_text_messages_df: pd.DataFrame,
    *,
    entity_mentions_df: pd.DataFrame | None,
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    if entity_mentions_df is None or entity_mentions_df.empty:
        return _empty_df(_ENTITY_DISTRIBUTION_COLUMNS)
    required_columns = {"channel_id", "message_id", "entity"}
    if not required_columns.issubset(entity_mentions_df.columns):
        return _empty_df(_ENTITY_DISTRIBUTION_COLUMNS)

    segment_lookup_df = media_text_messages_df[["channel_id", "message_id", "segment_label", "has_text"]].copy()
    entity_df = (
        entity_mentions_df[["channel_id", "message_id", "entity"]]
        .dropna(subset=["entity"])
        .drop_duplicates(subset=["channel_id", "message_id", "entity"])
        .merge(segment_lookup_df, on=["channel_id", "message_id"], how="inner")
    )
    if entity_df.empty:
        return _empty_df(_ENTITY_DISTRIBUTION_COLUMNS)

    counts_df = (
        entity_df.groupby(["entity", "segment_label"], observed=False)["message_id"]
        .nunique()
        .rename("message_count")
        .reset_index()
    )
    entity_order = counts_df.groupby("entity", observed=False)["message_count"].sum().sort_values(ascending=False).head(config.top_entities).index.tolist()
    if not entity_order:
        return _empty_df(_ENTITY_DISTRIBUTION_COLUMNS)

    base_index = pd.MultiIndex.from_product(
        [entity_order, _segment_order(config)],
        names=["entity", "segment_label"],
    )
    counts_df = counts_df.set_index(["entity", "segment_label"]).reindex(base_index, fill_value=0).reset_index()

    segment_totals_lookup = (
        media_text_messages_df.loc[media_text_messages_df["has_text"]]
        .groupby("segment_label", observed=False)["message_id"]
        .nunique()
        .reindex(_segment_order(config), fill_value=0)
        .to_dict()
    )
    counts_df["segment_total"] = counts_df["segment_label"].map(lambda label: int(segment_totals_lookup.get(str(label), 0)))
    counts_df["message_share_pct"] = (
        100 * counts_df["message_count"] / counts_df["segment_total"].replace(0, pd.NA)
    ).fillna(0.0)

    share_summary_df = (
        counts_df.pivot(index="entity", columns="segment_label", values="message_share_pct")
        .reindex(index=entity_order, columns=_segment_order(config), fill_value=0.0)
    )
    share_summary_df["total_count"] = counts_df.groupby("entity", observed=False)["message_count"].sum().reindex(entity_order).to_numpy()
    share_summary_df["share_gap_pct_points"] = share_summary_df[_segment_order(config)[0]] - share_summary_df[_segment_order(config)[1]]
    share_summary_df["sort_order"] = range(len(share_summary_df))
    share_summary_df = share_summary_df.reset_index()

    counts_df = counts_df.merge(
        share_summary_df[["entity", "total_count", "share_gap_pct_points", "sort_order"]],
        on="entity",
        how="left",
    )
    counts_df["message_share_pct"] = counts_df["message_share_pct"].round(3)
    counts_df["share_gap_pct_points"] = counts_df["share_gap_pct_points"].round(3)
    counts_df["sort_order"] = counts_df["sort_order"].astype(int)
    return counts_df[_ENTITY_DISTRIBUTION_COLUMNS].copy()


def _top_value_for_segment(media_text_messages_df: pd.DataFrame, segment_label: str, column: str) -> str:
    subset = media_text_messages_df.loc[
        (media_text_messages_df["segment_label"] == segment_label) & media_text_messages_df[column].notna(),
        column,
    ]
    if subset.empty:
        return ""
    top_value = subset.value_counts().sort_values(ascending=False, kind="mergesort").index[0]
    return str(top_value)


def _build_summary(
    media_text_messages_df: pd.DataFrame,
    *,
    channel_label: str,
    entity_distribution_df: pd.DataFrame,
    config: MediaTextComparisonConfig,
) -> pd.DataFrame:
    media_label, text_only_label = _segment_order(config)
    return pd.DataFrame(
        [
            {
                "channel": channel_label,
                "messages_analyzed": len(media_text_messages_df),
                "start": media_text_messages_df["timestamp"].min(),
                "end": media_text_messages_df["timestamp"].max(),
                "media_messages": int(media_text_messages_df["has_media"].sum()),
                "text_only_messages": int((~media_text_messages_df["has_media"]).sum()),
                "media_share_pct": round(float(media_text_messages_df["has_media"].mean() * 100), 1),
                "text_bearing_messages": int(media_text_messages_df["has_text"].sum()),
                "sentiment_available": bool(media_text_messages_df["sentiment_score"].notna().any()),
                "topic_available": bool(media_text_messages_df["dominant_topic"].notna().any()),
                "frame_available": bool(media_text_messages_df["dominant_frame"].notna().any()),
                "entity_available": bool(not entity_distribution_df.empty),
                "top_media_topic": _top_value_for_segment(media_text_messages_df, media_label, "dominant_topic"),
                "top_text_only_topic": _top_value_for_segment(media_text_messages_df, text_only_label, "dominant_topic"),
                "top_media_frame": _top_value_for_segment(media_text_messages_df, media_label, "dominant_frame"),
                "top_text_only_frame": _top_value_for_segment(media_text_messages_df, text_only_label, "dominant_frame"),
            }
        ]
    )


def _violin_metrics(media_text_messages_df: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    metrics: list[tuple[str, str, pd.Series]] = []
    if media_text_messages_df["sentiment_score"].notna().any():
        metrics.append(("sentiment_score", "Sentiment Distribution", media_text_messages_df["sentiment_score"].notna()))
    metrics.append(("text_length", "Text Length Distribution", media_text_messages_df["has_text"]))
    return metrics


def _draw_violin_axes(
    axes: Sequence[Any],
    media_text_messages_df: pd.DataFrame,
    *,
    config: MediaTextComparisonConfig,
) -> None:
    try:
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text violin plots require seaborn. Install notebook extras like: pip install seaborn matplotlib scipy"
        ) from exc

    palette = _segment_palette(config)
    segment_order = _segment_order(config)
    metrics = _violin_metrics(media_text_messages_df)

    if not metrics:
        _placeholder_axis(
            axes[0],
            title="Distribution comparison unavailable",
            message="No continuous variables are available for the media-vs-text violin comparison.",
        )
        for extra_ax in axes[1:]:
            extra_ax.set_visible(False)
        return

    for ax, (column, title, mask) in zip(axes, metrics):
        plot_df = media_text_messages_df.loc[mask, ["segment_label", column]].copy()
        if plot_df.empty:
            _placeholder_axis(
                ax,
                title=title,
                message="This metric has no observations in the current notebook state.",
            )
            continue

        sns.violinplot(
            data=plot_df,
            x="segment_label",
            y=column,
            order=segment_order,
            hue="segment_label",
            hue_order=segment_order,
            palette=palette,
            legend=False,
            inner=config.violin_inner,
            cut=0,
            linewidth=1.0,
            ax=ax,
        )
        counts = plot_df["segment_label"].value_counts().to_dict()
        ax.set_xlabel("")
        ax.set_title(title)
        ax.set_xticks(range(len(segment_order)))
        ax.set_xticklabels(
            [f"{label}\n(n={int(counts.get(label, 0))})" for label in segment_order],
            rotation=0,
        )
        if column == "sentiment_score":
            ax.axhline(0.0, color="#777777", linestyle=":", linewidth=1.0)
            ax.set_ylabel("Sentiment score")
            ax.set_ylim(-1.05, 1.05)
        else:
            ax.set_ylabel("Characters")
        ax.grid(axis="y", alpha=0.18)

    for extra_ax in axes[len(metrics) :]:
        extra_ax.set_visible(False)


def _build_violin_figure(
    media_text_messages_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MediaTextComparisonConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn scipy"
        ) from exc

    sns.set_theme(style="whitegrid")
    metrics = _violin_metrics(media_text_messages_df)
    panel_count = max(1, len(metrics))
    fig, axes = plt.subplots(1, panel_count, figsize=(7.5 * panel_count, 5.6), constrained_layout=True)
    if not isinstance(axes, (list, tuple)):
        try:
            axes = list(axes.flatten())
        except AttributeError:
            axes = [axes]
    _draw_violin_axes(axes, media_text_messages_df, config=config)
    fig.suptitle(f"{channel_label} Telegram - Media vs. Text-Only Distributions", fontsize=15, y=1.02)
    return fig


def _draw_hour_density_axis(
    ax: Any,
    media_text_messages_df: pd.DataFrame,
    hourly_distribution_df: pd.DataFrame,
    *,
    config: MediaTextComparisonConfig,
) -> None:
    try:
        import numpy as np
        from scipy.stats import gaussian_kde
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text hour-density plots require numpy and scipy. "
            "Install notebook extras like: pip install scipy matplotlib seaborn"
        ) from exc

    palette = _segment_palette(config)
    x_grid = np.linspace(0, 23, config.density_grid_points)
    has_any_density = False

    for segment_label in _segment_order(config):
        values = media_text_messages_df.loc[
            media_text_messages_df["segment_label"] == segment_label,
            "hour",
        ].astype(float)
        if values.empty:
            continue

        unique_hours = values.nunique(dropna=True)
        if len(values) >= 3 and unique_hours >= 2:
            density = gaussian_kde(values.to_numpy(), bw_method=config.density_bw_method)(x_grid)
        else:
            fallback_df = hourly_distribution_df.loc[
                hourly_distribution_df["segment_label"] == segment_label
            ].sort_values("hour")
            if fallback_df.empty or fallback_df["message_share_pct"].sum() <= 0:
                continue
            density = fallback_df["message_share_pct"].to_numpy(dtype=float) / 100.0
            density = density / max(1e-9, float(np.trapz(density, fallback_df["hour"].to_numpy(dtype=float))))
            x_values = fallback_df["hour"].to_numpy(dtype=float)
            ax.plot(x_values, density, color=palette[segment_label], linewidth=2.4, label=segment_label)
            ax.fill_between(x_values, density, color=palette[segment_label], alpha=0.22)
            has_any_density = True
            continue

        ax.plot(x_grid, density, color=palette[segment_label], linewidth=2.6, label=segment_label)
        ax.fill_between(x_grid, density, color=palette[segment_label], alpha=0.22)
        has_any_density = True

    if not has_any_density:
        _placeholder_axis(
            ax,
            title="Posting-hour density comparison",
            message="No hour-level observations are available for the current messages.",
        )
        return

    ax.set_title("Posting Hour Density")
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Density")
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 2))
    ax.grid(axis="y", alpha=0.18)
    ax.legend(title="Message type", frameon=True)


def _build_hour_density_figure(
    media_text_messages_df: pd.DataFrame,
    hourly_distribution_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MediaTextComparisonConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn scipy"
        ) from exc

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(12, 5.6), constrained_layout=True)
    _draw_hour_density_axis(ax, media_text_messages_df, hourly_distribution_df, config=config)
    fig.suptitle(f"{channel_label} Telegram - Media vs. Text-Only Posting Hour Density", fontsize=15, y=1.02)
    return fig


def _draw_topic_axis(
    ax: Any,
    topic_distribution_df: pd.DataFrame,
    *,
    config: MediaTextComparisonConfig,
) -> None:
    try:
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text topic comparison plots require seaborn. "
            "Install notebook extras like: pip install seaborn matplotlib scipy"
        ) from exc

    if topic_distribution_df.empty:
        _placeholder_axis(
            ax,
            title="Topic mix comparison",
            message="Run Section 7 first if you want the grouped topic bar chart.",
        )
        return

    plot_df = topic_distribution_df.copy()
    topic_order = (
        plot_df[["topic_label", "sort_order"]]
        .drop_duplicates()
        .sort_values("sort_order")
        ["topic_label"]
        .tolist()
    )
    sns.barplot(
        data=plot_df,
        y="topic_label",
        x="message_share_pct",
        hue="segment_label",
        order=list(reversed(topic_order)),
        hue_order=_segment_order(config),
        palette=_segment_palette(config),
        orient="h",
        ax=ax,
    )
    ax.set_title("Topic Share by Message Type")
    ax.set_xlabel("Share of segment messages (%)")
    ax.set_ylabel("Topic")
    ax.grid(axis="x", alpha=0.18)
    ax.legend(title="Message type", frameon=True)


def _build_topic_figure(
    topic_distribution_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MediaTextComparisonConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn scipy"
        ) from exc

    sns.set_theme(style="whitegrid")
    fig_height = max(5.5, 0.7 * max(4, topic_distribution_df["topic_label"].nunique()) + 2.0) if not topic_distribution_df.empty else 5.5
    fig, ax = plt.subplots(figsize=(12, fig_height), constrained_layout=True)
    _draw_topic_axis(ax, topic_distribution_df, config=config)
    fig.suptitle(f"{channel_label} Telegram - Topic Mix: Media vs. Text-Only", fontsize=15, y=1.02)
    return fig


def _draw_frame_axis(
    ax: Any,
    frame_distribution_df: pd.DataFrame,
    *,
    config: MediaTextComparisonConfig,
) -> None:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text frame comparison plots require numpy. "
            "Install notebook extras like: pip install numpy matplotlib seaborn scipy"
        ) from exc

    if frame_distribution_df.empty:
        _placeholder_axis(
            ax,
            title="Rhetorical frame comparison",
            message="Run Section 11 first if you want the rhetoric comparison panel.",
        )
        return

    plot_df = frame_distribution_df.copy()
    frame_order = (
        plot_df[["dominant_frame", "sort_order"]]
        .drop_duplicates()
        .sort_values("sort_order")
        ["dominant_frame"]
        .tolist()
    )
    pivot_df = (
        plot_df.pivot(index="dominant_frame", columns="segment_label", values="message_count")
        .reindex(index=frame_order, columns=_segment_order(config), fill_value=0)
    )

    positions = np.arange(len(pivot_df), dtype=float)
    bottom = np.zeros(len(pivot_df), dtype=float)
    palette = _segment_palette(config)
    for segment_label in _segment_order(config):
        values = pivot_df[segment_label].to_numpy(dtype=float)
        ax.bar(
            positions,
            values,
            bottom=bottom,
            color=palette[segment_label],
            alpha=0.9,
            label=segment_label,
        )
        bottom += values

    ax.set_title("Rhetorical Frame Counts by Message Type")
    ax.set_xlabel("Rhetorical frame")
    ax.set_ylabel("Message count")
    ax.set_xticks(positions)
    ax.set_xticklabels(pivot_df.index.tolist(), rotation=32, ha="right")
    ax.grid(axis="y", alpha=0.18)
    ax.legend(title="Message type", frameon=True)


def _build_frame_figure(
    frame_distribution_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MediaTextComparisonConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn scipy"
        ) from exc

    sns.set_theme(style="whitegrid")
    fig_width = max(12, 1.0 * max(4, frame_distribution_df["dominant_frame"].nunique()) + 5.0) if not frame_distribution_df.empty else 12
    fig, ax = plt.subplots(figsize=(fig_width, 6.2), constrained_layout=True)
    _draw_frame_axis(ax, frame_distribution_df, config=config)
    fig.suptitle(f"{channel_label} Telegram - Rhetorical Frames: Media vs. Text-Only", fontsize=15, y=1.02)
    return fig


def _build_dashboard_figure(
    media_text_messages_df: pd.DataFrame,
    hourly_distribution_df: pd.DataFrame,
    topic_distribution_df: pd.DataFrame,
    frame_distribution_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MediaTextComparisonConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Media-vs-text plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn scipy"
        ) from exc

    sns.set_theme(style="whitegrid")
    fig = plt.figure(figsize=(20, 12), constrained_layout=True)
    grid = fig.add_gridspec(2, 2)

    violin_metrics = _violin_metrics(media_text_messages_df)
    violin_count = max(1, len(violin_metrics))
    violin_grid = grid[0, 0].subgridspec(1, violin_count, wspace=0.3)
    violin_axes = [fig.add_subplot(violin_grid[0, index]) for index in range(violin_count)]
    _draw_violin_axes(violin_axes, media_text_messages_df, config=config)

    ax_density = fig.add_subplot(grid[0, 1])
    _draw_hour_density_axis(ax_density, media_text_messages_df, hourly_distribution_df, config=config)

    ax_topic = fig.add_subplot(grid[1, 0])
    _draw_topic_axis(ax_topic, topic_distribution_df, config=config)

    ax_frame = fig.add_subplot(grid[1, 1])
    _draw_frame_axis(ax_frame, frame_distribution_df, config=config)

    fig.suptitle(
        f"Media vs. Text-Only: How Visual Content Shapes {channel_label}'s Messaging",
        fontsize=18,
        y=1.02,
    )
    return fig


def run_media_text_comparison_analysis(
    messages: Sequence[RawMessage],
    *,
    channel_label: str,
    sentiment_emotion_df: pd.DataFrame | None = None,
    topic_messages_df: pd.DataFrame | None = None,
    rhetoric_messages_df: pd.DataFrame | None = None,
    entity_mentions_df: pd.DataFrame | None = None,
    config: MediaTextComparisonConfig | None = None,
) -> MediaTextComparisonResult:
    config = config or MediaTextComparisonConfig()
    started_at = time.monotonic()

    media_text_messages_df = _prepare_media_text_messages(messages, config)
    media_text_messages_df = _merge_optional_columns(
        media_text_messages_df,
        sentiment_emotion_df=sentiment_emotion_df,
        topic_messages_df=topic_messages_df,
        rhetoric_messages_df=rhetoric_messages_df,
    )

    media_text_segment_summary_df = _build_segment_summary(media_text_messages_df, config)
    media_text_stat_tests_df = _build_stat_tests(media_text_messages_df, config)
    media_text_hourly_distribution_df = _build_hourly_distribution(media_text_messages_df, config)
    media_text_topic_distribution_df = _build_distribution_table(
        media_text_messages_df,
        column="dominant_topic",
        top_n=config.top_topics,
        config=config,
        output_columns=_TOPIC_DISTRIBUTION_COLUMNS,
    ).rename(columns={"dominant_topic": "topic_label"})
    media_text_frame_distribution_df = _build_distribution_table(
        media_text_messages_df,
        column="dominant_frame",
        top_n=config.top_frames,
        config=config,
        output_columns=_FRAME_DISTRIBUTION_COLUMNS,
    )
    media_text_tfidf_terms_df = _build_tfidf_terms(
        media_text_messages_df,
        channel_label=channel_label,
        config=config,
    )
    media_text_entity_distribution_df = _build_entity_distribution(
        media_text_messages_df,
        entity_mentions_df=entity_mentions_df,
        config=config,
    )
    media_text_summary_df = _build_summary(
        media_text_messages_df,
        channel_label=channel_label,
        entity_distribution_df=media_text_entity_distribution_df,
        config=config,
    )

    media_text_violin_fig = _build_violin_figure(
        media_text_messages_df,
        channel_label=channel_label,
        config=config,
    )
    media_text_hour_density_fig = _build_hour_density_figure(
        media_text_messages_df,
        media_text_hourly_distribution_df,
        channel_label=channel_label,
        config=config,
    )
    media_text_topic_fig = _build_topic_figure(
        media_text_topic_distribution_df,
        channel_label=channel_label,
        config=config,
    )
    media_text_frame_fig = _build_frame_figure(
        media_text_frame_distribution_df,
        channel_label=channel_label,
        config=config,
    )
    media_text_dashboard_fig = _build_dashboard_figure(
        media_text_messages_df,
        media_text_hourly_distribution_df,
        media_text_topic_distribution_df,
        media_text_frame_distribution_df,
        channel_label=channel_label,
        config=config,
    )

    return MediaTextComparisonResult(
        media_text_messages_df=media_text_messages_df,
        media_text_segment_summary_df=media_text_segment_summary_df,
        media_text_stat_tests_df=media_text_stat_tests_df,
        media_text_hourly_distribution_df=media_text_hourly_distribution_df,
        media_text_topic_distribution_df=media_text_topic_distribution_df,
        media_text_frame_distribution_df=media_text_frame_distribution_df,
        media_text_tfidf_terms_df=media_text_tfidf_terms_df,
        media_text_entity_distribution_df=media_text_entity_distribution_df,
        media_text_summary_df=media_text_summary_df,
        media_text_dashboard_fig=media_text_dashboard_fig,
        media_text_violin_fig=media_text_violin_fig,
        media_text_hour_density_fig=media_text_hour_density_fig,
        media_text_topic_fig=media_text_topic_fig,
        media_text_frame_fig=media_text_frame_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
