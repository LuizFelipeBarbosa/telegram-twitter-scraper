from __future__ import annotations

import re
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

SENTIMENT_LABEL_ORDER = ["negative", "neutral", "positive"]
EMOTION_LABEL_ORDER = ["anger", "disgust", "fear", "joy", "sadness", "surprise", "neutral"]
DEFAULT_SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
DEFAULT_EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"
DEFAULT_EMOTION_COLORS = {
    "anger": "crimson",
    "disgust": "darkgreen",
    "fear": "darkorange",
    "joy": "gold",
    "sadness": "steelblue",
    "surprise": "mediumpurple",
    "neutral": "gray",
    "no_data": "white",
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMOJI_RE = re.compile(
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
_TRAILING_DELIMITER_RE = re.compile(r"(?:\s*\n?---\s*)+$")


@dataclass(frozen=True)
class SentimentEmotionConfig:
    window_freq: str = "6h"
    heatmap_freq: str = "1h"
    rolling_windows: int = 3
    text_max_chars: int = 512
    model_batch_size: int = 16
    sentiment_model: str = DEFAULT_SENTIMENT_MODEL
    emotion_model: str = DEFAULT_EMOTION_MODEL
    emotion_colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_EMOTION_COLORS))


@dataclass(frozen=True)
class SentimentEmotionResult:
    df_text: pd.DataFrame
    sentiment_emotion_df: pd.DataFrame
    sentiment_window_df: pd.DataFrame
    emotion_window_df: pd.DataFrame
    hourly_sentiment_df: pd.DataFrame
    hourly_emotion_counts_df: pd.DataFrame
    hourly_dominant_emotion_df: pd.DataFrame
    candidate_events_df: pd.DataFrame
    event_annotations_df: pd.DataFrame
    sentiment_label_counts_df: pd.DataFrame
    emotion_label_counts_df: pd.DataFrame
    overall_summary_df: pd.DataFrame
    most_extreme_hour: pd.Series
    sentiment_over_time_fig: Any
    emotion_heatmap_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "df_text": self.df_text,
            "sentiment_emotion_df": self.sentiment_emotion_df,
            "sentiment_window_df": self.sentiment_window_df,
            "emotion_window_df": self.emotion_window_df,
            "hourly_sentiment_df": self.hourly_sentiment_df,
            "hourly_emotion_counts_df": self.hourly_emotion_counts_df,
            "hourly_dominant_emotion_df": self.hourly_dominant_emotion_df,
            "candidate_events_df": self.candidate_events_df,
            "event_annotations_df": self.event_annotations_df,
            "sentiment_label_counts_df": self.sentiment_label_counts_df,
            "emotion_label_counts_df": self.emotion_label_counts_df,
            "overall_summary_df": self.overall_summary_df,
            "most_extreme_hour": self.most_extreme_hour,
            "sentiment_over_time_fig": self.sentiment_over_time_fig,
            "emotion_heatmap_fig": self.emotion_heatmap_fig,
        }


def clean_analysis_text(text: str) -> str:
    cleaned = _URL_RE.sub("", text or "")
    cleaned = _EMOJI_RE.sub("", cleaned)
    cleaned = _TRAILING_DELIMITER_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def score_map(scores: Sequence[Mapping[str, float]], label_order: Sequence[str]) -> dict[str, float]:
    lookup = {str(item["label"]).lower(): float(item["score"]) for item in scores}
    return {label: lookup.get(label, 0.0) for label in label_order}


def _prepare_text_messages(messages: Sequence[RawMessage]) -> pd.DataFrame:
    analysis_records: list[dict[str, Any]] = []
    for message in messages:
        timestamp = pd.to_datetime(message.timestamp, utc=True)
        cleaned_text = clean_analysis_text(preferred_message_text(message))
        if not cleaned_text:
            continue
        analysis_records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.date(),
                "hour": timestamp.hour,
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "text": cleaned_text,
                "raw_text": (message.text or "").strip(),
                "english_text": (message.english_text or "").strip(),
                "has_media": bool(message.media_refs),
            }
        )

    df_text = pd.DataFrame(analysis_records).sort_values("timestamp").reset_index(drop=True)
    if df_text.empty:
        raise RuntimeError("No text-bearing messages are available after cleaning. Run Sections 3-4 first.")

    df_text["day_name"] = df_text["timestamp"].dt.day_name()
    df_text["text_length"] = df_text["text"].str.len()
    return df_text


def _score_messages(df_text: pd.DataFrame, config: SentimentEmotionConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Sentiment analysis requires transformers plus a backend such as torch. "
            "Install notebook extras like: pip install transformers torch matplotlib seaborn numpy"
        ) from exc

    sentiment_pipe = pipeline("sentiment-analysis", model=config.sentiment_model, top_k=None)
    emotion_pipe = pipeline("text-classification", model=config.emotion_model, top_k=None)

    analysis_texts = df_text["text"].str.slice(0, config.text_max_chars).tolist()
    sentiment_outputs = sentiment_pipe(analysis_texts, batch_size=config.model_batch_size, truncation=True)
    emotion_outputs = emotion_pipe(analysis_texts, batch_size=config.model_batch_size, truncation=True)

    sentiment_score_maps = [score_map(scores, SENTIMENT_LABEL_ORDER) for scores in sentiment_outputs]
    emotion_score_maps = [score_map(scores, EMOTION_LABEL_ORDER) for scores in emotion_outputs]

    sentiment_emotion_df = df_text.copy()
    for label in SENTIMENT_LABEL_ORDER:
        sentiment_emotion_df[f"sentiment_{label}"] = [scores[label] for scores in sentiment_score_maps]

    sentiment_emotion_df["sentiment_score"] = (
        sentiment_emotion_df["sentiment_positive"] - sentiment_emotion_df["sentiment_negative"]
    )
    sentiment_emotion_df["dominant_sentiment"] = sentiment_emotion_df[
        [f"sentiment_{label}" for label in SENTIMENT_LABEL_ORDER]
    ].idxmax(axis=1).str.removeprefix("sentiment_")
    sentiment_emotion_df["sentiment_confidence"] = sentiment_emotion_df[
        [f"sentiment_{label}" for label in SENTIMENT_LABEL_ORDER]
    ].max(axis=1)

    for label in EMOTION_LABEL_ORDER:
        sentiment_emotion_df[f"emotion_{label}"] = [scores[label] for scores in emotion_score_maps]

    sentiment_emotion_df["dominant_emotion"] = sentiment_emotion_df[
        [f"emotion_{label}" for label in EMOTION_LABEL_ORDER]
    ].idxmax(axis=1).str.removeprefix("emotion_")
    sentiment_emotion_df["emotion_confidence"] = sentiment_emotion_df[
        [f"emotion_{label}" for label in EMOTION_LABEL_ORDER]
    ].max(axis=1)

    sentiment_label_counts_df = (
        sentiment_emotion_df["dominant_sentiment"]
        .value_counts()
        .rename_axis("dominant_sentiment")
        .reset_index(name="message_count")
    )
    emotion_label_counts_df = (
        sentiment_emotion_df["dominant_emotion"]
        .value_counts()
        .rename_axis("dominant_emotion")
        .reset_index(name="message_count")
    )
    return sentiment_emotion_df, sentiment_label_counts_df, emotion_label_counts_df


def _aggregate_windows(
    sentiment_emotion_df: pd.DataFrame,
    config: SentimentEmotionConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Sentiment analysis requires numpy, matplotlib, and seaborn. "
            "Install notebook extras like: pip install numpy matplotlib seaborn"
        ) from exc

    window_start = sentiment_emotion_df["timestamp"].min().floor(config.window_freq)
    window_end = sentiment_emotion_df["timestamp"].max().ceil(config.window_freq)
    window_index = pd.date_range(window_start, window_end, freq=config.window_freq, tz="UTC")

    sentiment_window_df = (
        sentiment_emotion_df.groupby(pd.Grouper(key="timestamp", freq=config.window_freq))
        .agg(
            message_count=("message_id", "size"),
            sentiment_mean=("sentiment_score", "mean"),
            sentiment_std=("sentiment_score", "std"),
        )
        .reindex(window_index)
        .rename_axis("timestamp")
        .reset_index()
    )
    sentiment_window_df["message_count"] = sentiment_window_df["message_count"].fillna(0).astype(int)
    sentiment_window_df["sentiment_std"] = sentiment_window_df["sentiment_std"].fillna(0.0)
    sentiment_window_df["sentiment_se"] = sentiment_window_df["sentiment_std"] / np.sqrt(
        sentiment_window_df["message_count"].clip(lower=1)
    )
    sentiment_window_df["sentiment_ci95"] = 1.96 * sentiment_window_df["sentiment_se"]
    sentiment_window_df["sentiment_rolling_mean"] = sentiment_window_df["sentiment_mean"].rolling(
        config.rolling_windows,
        min_periods=1,
    ).mean()

    emotion_window_counts_df = (
        sentiment_emotion_df.groupby([pd.Grouper(key="timestamp", freq=config.window_freq), "dominant_emotion"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=EMOTION_LABEL_ORDER, fill_value=0)
        .reindex(window_index, fill_value=0)
    )
    emotion_window_df = emotion_window_counts_df.div(
        emotion_window_counts_df.sum(axis=1).replace(0, pd.NA),
        axis=0,
    ).fillna(0.0)
    emotion_window_df.index.name = "timestamp"
    emotion_window_df = emotion_window_df.reset_index()

    hourly_index = pd.date_range(
        sentiment_emotion_df["timestamp"].min().floor(config.heatmap_freq),
        sentiment_emotion_df["timestamp"].max().ceil(config.heatmap_freq),
        freq=config.heatmap_freq,
        tz="UTC",
    )

    hourly_sentiment_df = (
        sentiment_emotion_df.assign(hour_bucket=sentiment_emotion_df["timestamp"].dt.floor(config.heatmap_freq))
        .groupby("hour_bucket")
        .agg(
            message_count=("message_id", "size"),
            sentiment_mean=("sentiment_score", "mean"),
        )
        .reindex(hourly_index)
        .rename_axis("timestamp")
        .reset_index()
    )
    hourly_sentiment_df["message_count"] = hourly_sentiment_df["message_count"].fillna(0).astype(int)
    hourly_sentiment_df["sentiment_mean"] = hourly_sentiment_df["sentiment_mean"].fillna(0.0)
    hourly_sentiment_df["sentiment_abs_mean"] = hourly_sentiment_df["sentiment_mean"].abs()
    hourly_sentiment_df["sentiment_change"] = hourly_sentiment_df["sentiment_mean"].diff().abs().fillna(0.0)

    hourly_extreme_rows = (
        sentiment_emotion_df.assign(
            hour_bucket=sentiment_emotion_df["timestamp"].dt.floor(config.heatmap_freq),
            abs_sentiment=sentiment_emotion_df["sentiment_score"].abs(),
        )
        .sort_values(["hour_bucket", "abs_sentiment"], ascending=[True, False])
        .drop_duplicates("hour_bucket")
        .set_index("hour_bucket")
    )
    hourly_sentiment_df = hourly_sentiment_df.merge(
        hourly_extreme_rows[["message_id", "dominant_emotion", "sentiment_score", "text"]].rename(
            columns={
                "dominant_emotion": "representative_emotion",
                "sentiment_score": "representative_sentiment_score",
                "text": "representative_text",
            }
        ),
        left_on="timestamp",
        right_index=True,
        how="left",
    )

    candidate_events_df = (
        pd.concat(
            [
                hourly_sentiment_df.nlargest(5, "message_count"),
                hourly_sentiment_df.nlargest(5, "sentiment_abs_mean"),
                hourly_sentiment_df.nlargest(5, "sentiment_change"),
            ],
            ignore_index=True,
        )
        .dropna(subset=["timestamp"])
        .drop_duplicates(subset=["timestamp"])
        .sort_values(["message_count", "sentiment_abs_mean", "sentiment_change"], ascending=False)
        .head(10)
        .copy()
    )
    candidate_events_df["representative_text"] = candidate_events_df["representative_text"].fillna("").map(
        lambda text: textwrap.shorten(text.replace("\n", " "), width=100, placeholder="...")
    )
    candidate_events_df = candidate_events_df[
        [
            "timestamp",
            "message_count",
            "sentiment_mean",
            "sentiment_change",
            "representative_emotion",
            "representative_text",
        ]
    ].reset_index(drop=True)

    most_extreme_hour = hourly_sentiment_df.loc[hourly_sentiment_df["sentiment_abs_mean"].idxmax()].copy()

    hourly_emotion_counts_df = (
        sentiment_emotion_df.assign(hour_bucket=sentiment_emotion_df["timestamp"].dt.floor(config.heatmap_freq))
        .groupby(["hour_bucket", "dominant_emotion"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=EMOTION_LABEL_ORDER, fill_value=0)
        .reindex(hourly_index, fill_value=0)
    )

    hourly_dominant_emotion_df = hourly_emotion_counts_df.idxmax(axis=1).to_frame("dominant_emotion")
    hourly_dominant_emotion_df["message_count"] = hourly_emotion_counts_df.sum(axis=1)
    hourly_dominant_emotion_df.loc[
        hourly_dominant_emotion_df["message_count"] == 0,
        "dominant_emotion",
    ] = "no_data"
    hourly_dominant_emotion_df = hourly_dominant_emotion_df.reset_index().rename(columns={"index": "timestamp"})
    hourly_dominant_emotion_df["date"] = hourly_dominant_emotion_df["timestamp"].dt.date
    hourly_dominant_emotion_df["hour"] = hourly_dominant_emotion_df["timestamp"].dt.hour

    overall_summary_df = pd.DataFrame(
        [
            {
                "messages_scored": len(sentiment_emotion_df),
                "start": sentiment_emotion_df["timestamp"].min(),
                "end": sentiment_emotion_df["timestamp"].max(),
                "mean_sentiment": round(float(sentiment_emotion_df["sentiment_score"].mean()), 3),
                "dominant_emotion": sentiment_emotion_df["dominant_emotion"].mode().iat[0],
            }
        ]
    )

    return (
        sentiment_window_df,
        emotion_window_df,
        hourly_sentiment_df,
        hourly_emotion_counts_df.reset_index().rename(columns={"hour_bucket": "timestamp"}),
        hourly_dominant_emotion_df,
        most_extreme_hour,
        candidate_events_df,
        overall_summary_df,
    )


def _build_event_annotations(
    candidate_events_df: pd.DataFrame,
    event_annotations: Sequence[Mapping[str, Any]] | None,
) -> pd.DataFrame:
    if event_annotations:
        event_annotations_df = pd.DataFrame(event_annotations)
        event_annotations_df["timestamp"] = pd.to_datetime(event_annotations_df["timestamp"], utc=True)
        return event_annotations_df.sort_values("timestamp").reset_index(drop=True)

    event_annotations_df = candidate_events_df[["timestamp", "representative_text"]].head(5).copy()
    event_annotations_df["label"] = [
        f"Candidate {index + 1}: {textwrap.shorten(text, width=60, placeholder='...')}"
        for index, text in enumerate(event_annotations_df["representative_text"].fillna(""))
    ]
    return event_annotations_df[["timestamp", "label"]]


def _build_sentiment_over_time_figure(
    sentiment_window_df: pd.DataFrame,
    emotion_window_df: pd.DataFrame,
    event_annotations_df: pd.DataFrame,
    most_extreme_hour: pd.Series,
    *,
    channel_label: str,
    config: SentimentEmotionConfig,
) -> Any:
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Sentiment plotting requires matplotlib. Install notebook extras like: pip install matplotlib seaborn numpy"
        ) from exc

    emotion_area_df = emotion_window_df.set_index("timestamp")[EMOTION_LABEL_ORDER]

    fig = plt.figure(figsize=(18, 9))
    grid = gridspec.GridSpec(2, 1, height_ratios=[1, 5], hspace=0.02)
    ax_ann = fig.add_subplot(grid[0])
    ax1 = fig.add_subplot(grid[1], sharex=ax_ann)
    ax2 = ax1.twinx()

    ax2.stackplot(
        emotion_area_df.index.to_pydatetime(),
        *[emotion_area_df[label].to_numpy() for label in EMOTION_LABEL_ORDER],
        colors=[config.emotion_colors[label] for label in EMOTION_LABEL_ORDER],
        alpha=0.3,
    )
    ax2.set_ylim(0, 1)
    ax2.set_ylabel(f"Dominant emotion share per {config.window_freq} window")

    ax1.plot(
        sentiment_window_df["timestamp"],
        sentiment_window_df["sentiment_mean"],
        color="#4a4a4a",
        linewidth=1.25,
        alpha=0.6,
    )
    ax1.plot(
        sentiment_window_df["timestamp"],
        sentiment_window_df["sentiment_rolling_mean"],
        color="black",
        linewidth=2.5,
    )
    ax1.fill_between(
        sentiment_window_df["timestamp"],
        sentiment_window_df["sentiment_mean"] - sentiment_window_df["sentiment_ci95"],
        sentiment_window_df["sentiment_mean"] + sentiment_window_df["sentiment_ci95"],
        color="#7f7f7f",
        alpha=0.15,
    )
    ax1.axhline(0, color="#666666", linestyle=":", linewidth=1)
    ax1.set_ylim(-1.05, 1.05)
    ax1.set_ylabel("Sentiment score (-1 to +1)")
    ax1.set_xlabel("Timestamp (UTC)")

    ax_ann.set_title(f"{channel_label} Telegram - Sentiment and Emotion Over Time", fontsize=13, fontweight="bold")
    ax_ann.set_ylim(0, 1)
    ax_ann.axis("off")

    stagger_heights = [0.25, 0.65]
    for index, (_, row) in enumerate(event_annotations_df.iterrows()):
        timestamp = row["timestamp"]
        y_pos = stagger_heights[index % 2]
        short_label = textwrap.shorten(str(row["label"]), width=60, placeholder="…")

        ax1.axvline(timestamp, color="#999999", linestyle="--", linewidth=0.8, alpha=0.4)
        ax_ann.axvline(timestamp, color="#999999", linestyle="--", linewidth=0.8, alpha=0.4)
        ax_ann.plot(timestamp, y_pos, "o", color="#3366cc", markersize=14, zorder=5)
        ax_ann.text(
            timestamp,
            y_pos,
            str(index + 1),
            ha="center",
            va="center",
            fontsize=7.5,
            fontweight="bold",
            color="white",
            zorder=6,
        )
        ax_ann.annotate(
            short_label,
            xy=(timestamp, y_pos),
            xytext=(8, 0),
            textcoords="offset points",
            fontsize=7.5,
            va="center",
            ha="left",
            color="#222222",
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8},
        )

    extreme_hour_x = most_extreme_hour["timestamp"]
    extreme_hour_y = float(most_extreme_hour["sentiment_mean"])
    extreme_text = most_extreme_hour.get("representative_text", "")
    if not isinstance(extreme_text, str) or not extreme_text.strip():
        extreme_text = "(no text available)"
    callout_text = textwrap.fill(textwrap.shorten(extreme_text, width=120, placeholder="…"), width=48)

    ax1.scatter(
        [extreme_hour_x],
        [extreme_hour_y],
        facecolors="white",
        edgecolors="black",
        linewidths=1.5,
        s=70,
        zorder=6,
    )
    ax1.annotate(
        "Most extreme hour (1h mean)\n"
        f"{most_extreme_hour['timestamp']:%Y-%m-%d %H:%M UTC}\n"
        f"1h mean sentiment: {most_extreme_hour['sentiment_mean']:.2f}\n"
        f"{callout_text}",
        xy=(extreme_hour_x, extreme_hour_y),
        xytext=(20, -110 if extreme_hour_y > 0 else 30),
        textcoords="offset points",
        arrowprops={"arrowstyle": "->", "color": "black"},
        bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": "black", "alpha": 0.9},
        fontsize=8.5,
    )

    legend_handles = [
        Line2D([0], [0], color="#4a4a4a", linewidth=1.25, alpha=0.6, label="Window mean sentiment"),
        Line2D(
            [0],
            [0],
            color="black",
            linewidth=2.5,
            label=f"{config.rolling_windows}-window rolling mean",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor="white",
            markeredgecolor="black",
            markersize=7,
            label="Most extreme 1h mean",
        ),
        Patch(facecolor="#7f7f7f", alpha=0.15, label="95% CI"),
    ]
    legend_handles.extend(
        Patch(facecolor=config.emotion_colors[label], alpha=0.3, label=label.title())
        for label in EMOTION_LABEL_ORDER
    )
    ax1.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=5,
        frameon=True,
        fontsize=8.5,
    )

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    plt.setp(ax_ann.get_xticklabels(), visible=False)
    fig.tight_layout()
    return fig


def _build_emotion_heatmap_figure(
    hourly_dominant_emotion_df: pd.DataFrame,
    *,
    channel_label: str,
    config: SentimentEmotionConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        import seaborn as sns
        from matplotlib.colors import BoundaryNorm, ListedColormap
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Emotion heatmap plotting requires matplotlib, seaborn, and numpy. "
            "Install notebook extras like: pip install matplotlib seaborn numpy"
        ) from exc

    sns.set_theme(style="whitegrid")
    emotion_code_order = ["no_data", *EMOTION_LABEL_ORDER]
    emotion_code_lookup = {label: index for index, label in enumerate(emotion_code_order)}
    heatmap_matrix = (
        hourly_dominant_emotion_df.assign(
            emotion_code=hourly_dominant_emotion_df["dominant_emotion"].map(emotion_code_lookup)
        )
        .pivot(index="date", columns="hour", values="emotion_code")
        .sort_index()
    )

    cmap = ListedColormap([config.emotion_colors[label] for label in emotion_code_order])
    norm = BoundaryNorm(np.arange(len(emotion_code_order) + 1) - 0.5, len(emotion_code_order))

    fig, ax = plt.subplots(figsize=(18, max(4.5, len(heatmap_matrix) * 0.65)))
    sns.heatmap(
        heatmap_matrix,
        cmap=cmap,
        norm=norm,
        linewidths=0.5,
        linecolor="#e6e6e6",
        cbar=True,
        ax=ax,
    )

    colorbar = ax.collections[0].colorbar
    colorbar.set_ticks(range(len(emotion_code_order)))
    colorbar.set_ticklabels([label.replace("_", " ").title() for label in emotion_code_order])
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Date")
    ax.set_title(f"{channel_label} Telegram - Dominant Emotion by Hour")
    ax.set_xticklabels([f"{hour:02d}" for hour in heatmap_matrix.columns], rotation=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    fig.tight_layout()
    return fig


def run_sentiment_emotion_analysis(
    translated_messages: Sequence[RawMessage],
    *,
    channel_label: str,
    event_annotations: Sequence[Mapping[str, Any]] | None = None,
    config: SentimentEmotionConfig | None = None,
) -> SentimentEmotionResult:
    config = config or SentimentEmotionConfig()
    started_at = time.monotonic()

    df_text = _prepare_text_messages(translated_messages)
    sentiment_emotion_df, sentiment_label_counts_df, emotion_label_counts_df = _score_messages(df_text, config)
    (
        sentiment_window_df,
        emotion_window_df,
        hourly_sentiment_df,
        hourly_emotion_counts_df,
        hourly_dominant_emotion_df,
        most_extreme_hour,
        candidate_events_df,
        overall_summary_df,
    ) = _aggregate_windows(sentiment_emotion_df, config)
    event_annotations_df = _build_event_annotations(candidate_events_df, event_annotations)
    sentiment_over_time_fig = _build_sentiment_over_time_figure(
        sentiment_window_df,
        emotion_window_df,
        event_annotations_df,
        most_extreme_hour,
        channel_label=channel_label,
        config=config,
    )
    emotion_heatmap_fig = _build_emotion_heatmap_figure(
        hourly_dominant_emotion_df,
        channel_label=channel_label,
        config=config,
    )

    return SentimentEmotionResult(
        df_text=df_text,
        sentiment_emotion_df=sentiment_emotion_df,
        sentiment_window_df=sentiment_window_df,
        emotion_window_df=emotion_window_df,
        hourly_sentiment_df=hourly_sentiment_df,
        hourly_emotion_counts_df=hourly_emotion_counts_df,
        hourly_dominant_emotion_df=hourly_dominant_emotion_df,
        candidate_events_df=candidate_events_df,
        event_annotations_df=event_annotations_df,
        sentiment_label_counts_df=sentiment_label_counts_df,
        emotion_label_counts_df=emotion_label_counts_df,
        overall_summary_df=overall_summary_df,
        most_extreme_hour=most_extreme_hour,
        sentiment_over_time_fig=sentiment_over_time_fig,
        emotion_heatmap_fig=emotion_heatmap_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
