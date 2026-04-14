from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation, subplot_grid, to_utc_timestamp
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

DEFAULT_TFIDF_STATUS_COLORS = {
    "baseline": "#1f77b4",
    "recurring": "#1f77b4",
    "new": "#2ca02c",
    "dropped": "#d62728",
}

DEFAULT_TFIDF_EXTRA_STOPWORDS = {
    "iran",
    "iranian",
    "says",
    "said",
    "also",
    "would",
    "new",
    "presstv",
    "press",
    "breaking",
    "video",
    "videos",
    "photo",
    "photos",
    "image",
    "images",
    "report",
    "reports",
    "reported",
    "channel",
    "telegram",
    "via",
}

_TFIDF_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_TFIDF_MENTION_RE = re.compile(r"@\w+")
_TFIDF_HASHTAG_RE = re.compile(r"#(\w+)")
_TFIDF_TRAILING_DELIMITER_RE = re.compile(r"(?:\s*\n?---\s*)+$")


@dataclass(frozen=True)
class LexicalShiftConfig:
    periods: int = 4
    max_features: int = 500
    top_terms: int = 15
    prior_top_k_for_new: int = 30
    prior_top_k_for_dropout: int = 15
    highlight_movers: int = 5
    mover_rank_cutoff: int = 30
    wordcloud_max_words: int = 120
    status_colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TFIDF_STATUS_COLORS))
    extra_stopwords: set[str] = field(default_factory=lambda: set(DEFAULT_TFIDF_EXTRA_STOPWORDS))


@dataclass(frozen=True)
class LexicalShiftResult:
    tfidf_messages_df: pd.DataFrame
    tfidf_period_docs_df: pd.DataFrame
    tfidf_score_df: pd.DataFrame
    tfidf_rank_df: pd.DataFrame
    tfidf_risers_df: pd.DataFrame
    tfidf_fallers_df: pd.DataFrame
    tfidf_movers_df: pd.DataFrame
    tfidf_top_terms_df: pd.DataFrame
    tfidf_bar_plot_df: pd.DataFrame
    tfidf_summary_df: pd.DataFrame
    tfidf_wordcloud_frequencies: dict[str, dict[str, float]]
    tfidf_bump_fig: Any
    tfidf_terms_fig: Any
    tfidf_wordcloud_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "tfidf_messages_df": self.tfidf_messages_df,
            "tfidf_period_docs_df": self.tfidf_period_docs_df,
            "tfidf_score_df": self.tfidf_score_df,
            "tfidf_rank_df": self.tfidf_rank_df,
            "tfidf_risers_df": self.tfidf_risers_df,
            "tfidf_fallers_df": self.tfidf_fallers_df,
            "tfidf_movers_df": self.tfidf_movers_df,
            "tfidf_top_terms_df": self.tfidf_top_terms_df,
            "tfidf_bar_plot_df": self.tfidf_bar_plot_df,
            "tfidf_summary_df": self.tfidf_summary_df,
            "tfidf_wordcloud_frequencies": self.tfidf_wordcloud_frequencies,
            "tfidf_bump_fig": self.tfidf_bump_fig,
            "tfidf_terms_fig": self.tfidf_terms_fig,
            "tfidf_wordcloud_fig": self.tfidf_wordcloud_fig,
        }


def _ensure_stopwords_loaded() -> set[str]:
    try:
        import nltk
        from nltk.corpus import stopwords
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "TF-IDF analysis requires nltk. Install notebook extras like: pip install nltk scikit-learn matplotlib wordcloud"
        ) from exc

    try:
        return set(stopwords.words("english"))
    except LookupError:
        nltk.download("stopwords", quiet=True)
        return set(stopwords.words("english"))


def format_period_label(start: Any, end: Any) -> str:
    start_ts = to_utc_timestamp(start)
    end_ts = to_utc_timestamp(end)
    if start_ts.date() == end_ts.date():
        return f"{start_ts.strftime('%b')} {start_ts.day} {start_ts.strftime('%H:%M')}–{end_ts.strftime('%H:%M')}"
    if start_ts.year == end_ts.year and start_ts.month == end_ts.month:
        return f"{start_ts.strftime('%b')} {start_ts.day}–{end_ts.day}"
    if start_ts.year == end_ts.year:
        return f"{start_ts.strftime('%b')} {start_ts.day}–{end_ts.strftime('%b')} {end_ts.day}"
    return f"{start_ts.strftime('%Y-%m-%d')}–{end_ts.strftime('%Y-%m-%d')}"


def build_period_labels(timestamp_series: pd.Series, period_count: int) -> tuple[pd.Categorical, list[str], pd.DatetimeIndex]:
    start = timestamp_series.min()
    end = timestamp_series.max()
    if start == end:
        end = start + pd.Timedelta(days=period_count)
    edges = pd.date_range(start, end, periods=period_count + 1, tz="UTC")
    labels = [format_period_label(edges[index], edges[index + 1]) for index in range(len(edges) - 1)]
    period_categories = pd.cut(
        timestamp_series,
        bins=edges,
        labels=labels,
        include_lowest=True,
        duplicates="drop",
    )
    return period_categories, labels, edges


def compute_rank_series(score_series: pd.Series) -> pd.Series:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "TF-IDF analysis requires numpy. Install notebook extras like: pip install nltk scikit-learn matplotlib wordcloud"
        ) from exc

    positive_scores = score_series[score_series > 0].sort_values(ascending=False, kind="mergesort")
    ranks = pd.Series(len(score_series) + 1, index=score_series.index, dtype=float)
    ranks.loc[positive_scores.index] = np.arange(1, len(positive_scores) + 1, dtype=float)
    return ranks


def _build_stopwords(channel_label: str, config: LexicalShiftConfig) -> set[str]:
    channel_stopwords = {
        token.lower()
        for token in re.findall(r"[A-Za-z]+", channel_label)
        if len(token) > 2
    }
    return _ensure_stopwords_loaded().union(config.extra_stopwords).union(channel_stopwords)


def clean_tfidf_text(text: str, stop_words: set[str]) -> str:
    cleaned = _TFIDF_URL_RE.sub(" ", text or "")
    cleaned = _TFIDF_MENTION_RE.sub(" ", cleaned)
    cleaned = _TFIDF_HASHTAG_RE.sub(r" \1 ", cleaned)
    cleaned = _TFIDF_TRAILING_DELIMITER_RE.sub(" ", cleaned)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^a-z\s-]", " ", cleaned)
    tokens = [token.strip("-") for token in cleaned.split()]
    tokens = [token for token in tokens if len(token) > 2 and token not in stop_words]
    return " ".join(tokens)


def run_tfidf_shift_analysis(
    translated_messages: Sequence[RawMessage],
    *,
    channel_label: str,
    config: LexicalShiftConfig | None = None,
) -> LexicalShiftResult:
    config = config or LexicalShiftConfig()
    started_at = time.monotonic()

    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from wordcloud import WordCloud
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "TF-IDF analysis requires nltk, scikit-learn, matplotlib, wordcloud, and numpy. "
            "Install notebook extras like: pip install nltk scikit-learn matplotlib wordcloud"
        ) from exc

    tfidf_stop_words = _build_stopwords(channel_label, config)
    tfidf_records: list[dict[str, Any]] = []
    for message in translated_messages:
        original_text = (preferred_message_text(message) or "").strip()
        cleaned_text = clean_tfidf_text(original_text, tfidf_stop_words)
        if not cleaned_text:
            continue

        timestamp = pd.to_datetime(message.timestamp, utc=True)
        tfidf_records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "text": original_text,
                "clean_text": cleaned_text,
                "token_count": len(cleaned_text.split()),
            }
        )

    tfidf_messages_df = pd.DataFrame(tfidf_records).sort_values("timestamp").reset_index(drop=True)
    if tfidf_messages_df.empty:
        raise RuntimeError("No text-bearing messages remain after TF-IDF cleaning. Run Sections 3-4 first.")

    tfidf_messages_df["period"], tfidf_period_labels, _ = build_period_labels(
        tfidf_messages_df["timestamp"],
        config.periods,
    )
    tfidf_messages_df["period"] = pd.Categorical(
        tfidf_messages_df["period"],
        categories=tfidf_period_labels,
        ordered=True,
    )
    tfidf_messages_df["period_index"] = tfidf_messages_df["period"].cat.codes + 1

    tfidf_pseudo_docs = (
        tfidf_messages_df.groupby("period", observed=False)["clean_text"]
        .apply(lambda values: " ".join(values))
        .reindex(tfidf_period_labels, fill_value="")
    )
    tfidf_message_counts = (
        tfidf_messages_df.groupby("period", observed=False)["message_id"]
        .size()
        .reindex(tfidf_period_labels, fill_value=0)
    )
    tfidf_token_counts = (
        tfidf_messages_df.groupby("period", observed=False)["token_count"]
        .sum()
        .reindex(tfidf_period_labels, fill_value=0)
    )
    tfidf_first_seen = (
        tfidf_messages_df.groupby("period", observed=False)["timestamp"]
        .min()
        .reindex(tfidf_period_labels)
    )
    tfidf_last_seen = (
        tfidf_messages_df.groupby("period", observed=False)["timestamp"]
        .max()
        .reindex(tfidf_period_labels)
    )

    tfidf_period_docs_df = pd.DataFrame(
        {
            "period_label": tfidf_period_labels,
            "message_count": tfidf_message_counts.to_numpy(),
            "token_count": tfidf_token_counts.to_numpy(),
            "first_seen": tfidf_first_seen.to_numpy(),
            "last_seen": tfidf_last_seen.to_numpy(),
            "pseudo_document": tfidf_pseudo_docs.to_numpy(),
        }
    )

    tfidf_vectorizer = TfidfVectorizer(max_features=config.max_features, ngram_range=(1, 1))
    tfidf_matrix = tfidf_vectorizer.fit_transform(tfidf_pseudo_docs.tolist())
    tfidf_feature_names = tfidf_vectorizer.get_feature_names_out()
    if len(tfidf_feature_names) == 0:
        raise RuntimeError("TF-IDF vocabulary is empty after preprocessing. Reduce the stopword list or inspect the text.")

    tfidf_score_df = pd.DataFrame(
        tfidf_matrix.toarray().T,
        index=tfidf_feature_names,
        columns=tfidf_period_labels,
    )
    tfidf_score_df.index.name = "term"

    tfidf_rank_df = pd.DataFrame({label: compute_rank_series(tfidf_score_df[label]) for label in tfidf_period_labels})
    tfidf_rank_df["first_rank"] = tfidf_rank_df[tfidf_period_labels[0]]
    tfidf_rank_df["last_rank"] = tfidf_rank_df[tfidf_period_labels[-1]]
    tfidf_rank_df["first_score"] = tfidf_score_df[tfidf_period_labels[0]]
    tfidf_rank_df["last_score"] = tfidf_score_df[tfidf_period_labels[-1]]
    tfidf_rank_df["best_rank"] = tfidf_rank_df[tfidf_period_labels].min(axis=1)
    tfidf_rank_df["max_score"] = tfidf_score_df.max(axis=1)
    tfidf_rank_df["delta"] = tfidf_rank_df[tfidf_period_labels[0]] - tfidf_rank_df[tfidf_period_labels[-1]]

    tfidf_mover_candidates_df = tfidf_rank_df.loc[
        (tfidf_rank_df["best_rank"] <= config.mover_rank_cutoff)
        & (tfidf_rank_df["max_score"] > 0)
    ].copy()
    tfidf_risers_df = (
        tfidf_mover_candidates_df.loc[
            (tfidf_mover_candidates_df["delta"] > 0)
            & (tfidf_mover_candidates_df["last_score"] > 0)
        ]
        .sort_values(["delta", "last_score", "best_rank"], ascending=[False, False, True])
        .head(config.highlight_movers)
        .reset_index()
        .rename(columns={"index": "term"})
    )
    tfidf_risers_df["mover_type"] = "riser"

    tfidf_fallers_df = (
        tfidf_mover_candidates_df.loc[
            (tfidf_mover_candidates_df["delta"] < 0)
            & (tfidf_mover_candidates_df["first_score"] > 0)
        ]
        .sort_values(["delta", "first_score", "best_rank"], ascending=[True, False, True])
        .head(config.highlight_movers)
        .reset_index()
        .rename(columns={"index": "term"})
    )
    tfidf_fallers_df["mover_type"] = "faller"

    tfidf_movers_df = pd.concat([tfidf_risers_df, tfidf_fallers_df], ignore_index=True)
    if not tfidf_movers_df.empty:
        tfidf_movers_df = tfidf_movers_df[
            [
                "term",
                "mover_type",
                "first_rank",
                "last_rank",
                "delta",
                "first_score",
                "last_score",
                "best_rank",
                "max_score",
            ]
        ].reset_index(drop=True)

    tfidf_top_term_rows: list[dict[str, Any]] = []
    for period_index, period_label in enumerate(tfidf_period_labels):
        current_scores = tfidf_score_df[period_label][tfidf_score_df[period_label] > 0].sort_values(ascending=False)
        current_top_terms = current_scores.head(config.top_terms)
        current_top_term_set = set(current_top_terms.index)

        if period_index == 0:
            prior_top_k_for_new = set()
            prior_top_k_for_dropout: list[str] = []
        else:
            prior_label = tfidf_period_labels[period_index - 1]
            prior_scores = tfidf_score_df[prior_label][tfidf_score_df[prior_label] > 0].sort_values(ascending=False)
            prior_top_k_for_new = set(prior_scores.head(config.prior_top_k_for_new).index)
            prior_top_k_for_dropout = prior_scores.head(config.prior_top_k_for_dropout).index.tolist()

        for rank, (term, score) in enumerate(current_top_terms.items(), start=1):
            status = "baseline" if period_index == 0 else ("new" if term not in prior_top_k_for_new else "recurring")
            tfidf_top_term_rows.append(
                {
                    "period_label": period_label,
                    "display_rank": rank,
                    "term": term,
                    "term_label": term,
                    "plot_score": float(score),
                    "current_period_score": float(score),
                    "prior_period_score": np.nan,
                    "status": status,
                    "score_source": "current_period",
                    "is_current_top_term": True,
                }
            )

        if period_index > 0:
            dropped_terms = [term for term in prior_top_k_for_dropout if term not in current_top_term_set]
            for drop_offset, term in enumerate(dropped_terms[: config.highlight_movers], start=1):
                prior_score = float(tfidf_score_df.loc[term, prior_label])
                current_score = float(tfidf_score_df.loc[term, period_label])
                tfidf_top_term_rows.append(
                    {
                        "period_label": period_label,
                        "display_rank": config.top_terms + drop_offset,
                        "term": term,
                        "term_label": f"{term} ↓",
                        "plot_score": prior_score,
                        "current_period_score": current_score,
                        "prior_period_score": prior_score,
                        "status": "dropped",
                        "score_source": f"prior_period:{prior_label}",
                        "is_current_top_term": False,
                    }
                )

    tfidf_top_terms_df = pd.DataFrame(tfidf_top_term_rows)
    tfidf_bar_plot_df = tfidf_top_terms_df.copy()

    tfidf_summary_df = pd.DataFrame(
        [
            {
                "channel": channel_label,
                "messages_ready": len(tfidf_messages_df),
                "periods": len(tfidf_period_labels),
                "start": tfidf_messages_df["timestamp"].min(),
                "end": tfidf_messages_df["timestamp"].max(),
                "messages_using_translation": int(tfidf_messages_df["used_translation"].sum()),
                "vocabulary_size": int(len(tfidf_feature_names)),
            }
        ]
    )

    tfidf_highlight_terms = list(dict.fromkeys(tfidf_risers_df["term"].tolist() + tfidf_fallers_df["term"].tolist()))
    tfidf_highlight_color_map = {term: config.status_colors["new"] for term in tfidf_risers_df["term"].tolist()}
    tfidf_highlight_color_map.update({term: config.status_colors["dropped"] for term in tfidf_fallers_df["term"].tolist()})

    tfidf_bump_fig, tfidf_bump_ax = plt.subplots(figsize=(18, 11))
    tfidf_x_positions = np.arange(len(tfidf_period_labels))
    tfidf_rank_ceiling = max(10, int(tfidf_rank_df[tfidf_period_labels].to_numpy().max()))

    for term in tfidf_rank_df.index:
        y_values = tfidf_rank_df.loc[term, tfidf_period_labels].to_numpy(dtype=float)
        if term in tfidf_highlight_terms:
            highlight_color = tfidf_highlight_color_map[term]
            tfidf_bump_ax.plot(tfidf_x_positions, y_values, color=highlight_color, linewidth=2.8, alpha=0.95, zorder=3)
            tfidf_bump_ax.scatter(
                tfidf_x_positions,
                y_values,
                color=highlight_color,
                s=38,
                zorder=4,
                edgecolor="white",
                linewidth=0.8,
            )
            bbox = {"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 0.2}
            tfidf_bump_ax.text(
                tfidf_x_positions[0] - 0.08,
                y_values[0],
                term,
                ha="right",
                va="center",
                fontsize=10,
                color=highlight_color,
                bbox=bbox,
            )
            tfidf_bump_ax.text(
                tfidf_x_positions[-1] + 0.08,
                y_values[-1],
                term,
                ha="left",
                va="center",
                fontsize=10,
                color=highlight_color,
                bbox=bbox,
            )
        else:
            tfidf_bump_ax.plot(tfidf_x_positions, y_values, color="#cfcfcf", linewidth=0.9, alpha=0.18, zorder=1)

    tfidf_bump_ax.set_title(f"{channel_label} Telegram - TF-IDF Rank Trajectories by Period", fontsize=16, pad=18)
    tfidf_bump_ax.set_xticks(tfidf_x_positions)
    tfidf_bump_ax.set_xticklabels(tfidf_period_labels)
    tfidf_bump_ax.set_xlim(-0.35, len(tfidf_x_positions) - 0.65)
    tfidf_bump_ax.set_ylim(tfidf_rank_ceiling + 5, 0.5)
    tfidf_bump_ax.set_ylabel("TF-IDF rank (1 = most distinctive)")
    tfidf_bump_ax.grid(axis="y", alpha=0.2)
    tfidf_bump_ax.legend(
        handles=[
            plt.Line2D([0], [0], color=config.status_colors["new"], lw=3, label="Top risers"),
            plt.Line2D([0], [0], color=config.status_colors["dropped"], lw=3, label="Top fallers"),
            plt.Line2D([0], [0], color="#cfcfcf", lw=2, label="All other terms"),
        ],
        loc="upper right",
        frameon=True,
    )
    tfidf_bump_fig.tight_layout()

    term_rows, term_cols = subplot_grid(len(tfidf_period_labels), max_cols=2)
    tfidf_terms_fig, tfidf_terms_axes = plt.subplots(
        term_rows,
        term_cols,
        figsize=(18, max(7, 6 * term_rows)),
        constrained_layout=True,
    )
    tfidf_terms_axes = np.atleast_1d(tfidf_terms_axes).flatten()
    tfidf_max_plot_score = max(0.05, float(tfidf_bar_plot_df["plot_score"].max()) * 1.18)

    for axis_index, period_label in enumerate(tfidf_period_labels):
        ax = tfidf_terms_axes[axis_index]
        panel_df = (
            tfidf_bar_plot_df.loc[tfidf_bar_plot_df["period_label"] == period_label]
            .sort_values("display_rank")
            .reset_index(drop=True)
        )
        if panel_df.empty:
            ax.set_visible(False)
            continue

        panel_colors = [config.status_colors[status] for status in panel_df["status"]]
        bars = ax.barh(panel_df["term_label"], panel_df["plot_score"], color=panel_colors, alpha=0.88, edgecolor="none")
        ax.invert_yaxis()
        ax.set_xlim(0, tfidf_max_plot_score)
        ax.set_title(period_label, fontsize=13)
        ax.set_xlabel("TF-IDF score")
        ax.grid(axis="x", alpha=0.2)

        for bar, (_, row) in zip(bars, panel_df.iterrows()):
            if row["status"] == "dropped":
                bar.set_hatch("///")
                bar.set_alpha(0.45)
                value_label = f"{row['prior_period_score']:.3f} (prior)"
            else:
                value_label = f"{row['plot_score']:.3f}"
            ax.text(
                bar.get_width() + tfidf_max_plot_score * 0.01,
                bar.get_y() + bar.get_height() / 2,
                value_label,
                va="center",
                ha="left",
                fontsize=8.5,
                color="#333333",
            )

        if (panel_df["status"] == "dropped").any():
            ax.text(
                0.98,
                0.02,
                "Red hatched rows show prior-period score\nfor terms that dropped out of the current top window.",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=8,
                color=config.status_colors["dropped"],
            )

    for extra_ax in tfidf_terms_axes[len(tfidf_period_labels) :]:
        extra_ax.set_visible(False)

    tfidf_terms_fig.suptitle(f"{channel_label} Telegram - Distinctive Terms by Period", fontsize=16, y=1.02)
    tfidf_terms_fig.legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, facecolor=config.status_colors["baseline"], label="Baseline / recurring"),
            plt.Rectangle((0, 0), 1, 1, facecolor=config.status_colors["new"], label="New vs prior comparison window"),
            plt.Rectangle(
                (0, 0),
                1,
                1,
                facecolor=config.status_colors["dropped"],
                hatch="///",
                alpha=0.45,
                label="Dropped from prior top window",
            ),
        ],
        loc="upper center",
        ncol=3,
        frameon=True,
    )

    tfidf_wordcloud_frequencies = {
        period_label: tfidf_score_df[period_label][tfidf_score_df[period_label] > 0]
        .sort_values(ascending=False)
        .head(config.wordcloud_max_words)
        .to_dict()
        for period_label in tfidf_period_labels
    }

    cloud_rows, cloud_cols = subplot_grid(len(tfidf_period_labels), max_cols=2)
    tfidf_wordcloud_fig, tfidf_wordcloud_axes = plt.subplots(
        cloud_rows,
        cloud_cols,
        figsize=(18, max(6, 5 * cloud_rows)),
        constrained_layout=True,
    )
    tfidf_wordcloud_axes = np.atleast_1d(tfidf_wordcloud_axes).flatten()

    for axis_index, period_label in enumerate(tfidf_period_labels):
        ax = tfidf_wordcloud_axes[axis_index]
        frequencies = tfidf_wordcloud_frequencies.get(period_label, {})
        if not frequencies:
            ax.axis("off")
            ax.set_title(period_label)
            ax.text(0.5, 0.5, "No terms available", ha="center", va="center", fontsize=12)
            continue

        cloud = WordCloud(
            width=900,
            height=500,
            background_color="white",
            max_words=config.wordcloud_max_words,
            colormap="viridis",
            prefer_horizontal=0.95,
            collocations=False,
            normalize_plurals=False,
            random_state=42,
        ).generate_from_frequencies(frequencies)
        ax.imshow(cloud, interpolation="bilinear")
        ax.axis("off")
        ax.set_title(period_label, fontsize=13)

    for extra_ax in tfidf_wordcloud_axes[len(tfidf_period_labels) :]:
        extra_ax.set_visible(False)

    tfidf_wordcloud_fig.suptitle(
        f"{channel_label} Telegram - TF-IDF Word Clouds (Supplementary)",
        fontsize=16,
        y=1.02,
    )

    return LexicalShiftResult(
        tfidf_messages_df=tfidf_messages_df,
        tfidf_period_docs_df=tfidf_period_docs_df,
        tfidf_score_df=tfidf_score_df,
        tfidf_rank_df=tfidf_rank_df,
        tfidf_risers_df=tfidf_risers_df,
        tfidf_fallers_df=tfidf_fallers_df,
        tfidf_movers_df=tfidf_movers_df,
        tfidf_top_terms_df=tfidf_top_terms_df,
        tfidf_bar_plot_df=tfidf_bar_plot_df,
        tfidf_summary_df=tfidf_summary_df,
        tfidf_wordcloud_frequencies=tfidf_wordcloud_frequencies,
        tfidf_bump_fig=tfidf_bump_fig,
        tfidf_terms_fig=tfidf_terms_fig,
        tfidf_wordcloud_fig=tfidf_wordcloud_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
