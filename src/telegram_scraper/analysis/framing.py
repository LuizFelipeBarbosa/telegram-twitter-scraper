from __future__ import annotations

import re
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation, subplot_grid
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

DEFAULT_ZERO_SHOT_MODEL = "facebook/bart-large-mnli"
AMBIGUOUS_FRAME_SLUG = "mixed_ambiguous"
AMBIGUOUS_FRAME_LABEL = "Mixed / Ambiguous"
SENTIMENT_LABEL_ORDER = ["negative", "neutral", "positive"]

DEFAULT_FRAME_TAXONOMY: tuple[dict[str, Any], ...] = (
    {
        "frame_slug": "fear_threat",
        "frame_label": "Fear / Threat",
        "candidate_label": "fear and threat warning",
        "description": "Warnings about attacks, destruction, danger, or safety risks.",
        "signal_words": "threaten, strike, destroy, danger",
        "color": "#d62728",
    },
    {
        "frame_slug": "us_vs_them_othering",
        "frame_label": "Us-vs-Them / Othering",
        "candidate_label": "us versus them othering",
        "description": "Language that pits groups against each other or marks an enemy out-group.",
        "signal_words": "regime, enemy, they want to, against our",
        "color": "#9467bd",
    },
    {
        "frame_slug": "call_to_action",
        "frame_label": "Call to Action",
        "candidate_label": "call to action",
        "description": "Urges readers, governments, or groups to do something.",
        "signal_words": "must, should, urges, demands",
        "color": "#ff7f0e",
    },
    {
        "frame_slug": "victimhood_injustice",
        "frame_label": "Victimhood / Injustice",
        "candidate_label": "victimhood and injustice",
        "description": "Portrays a group as wronged, harmed, or unfairly treated.",
        "signal_words": "innocent, civilians, crime, massacre",
        "color": "#e377c2",
    },
    {
        "frame_slug": "authority_appeal",
        "frame_label": "Authority Appeal",
        "candidate_label": "authority appeal and official quote",
        "description": "Uses officials, leaders, or experts to lend credibility.",
        "signal_words": "according to, stated, the minister said",
        "color": "#1f77b4",
    },
    {
        "frame_slug": "factual_neutral",
        "frame_label": "Factual / Neutral",
        "candidate_label": "factual neutral reporting",
        "description": "Straight news reporting with limited emotional loading.",
        "signal_words": "reported, according to reports, official statement",
        "color": "#7f7f7f",
    },
    {
        "frame_slug": "conspiracy_suspicion",
        "frame_label": "Conspiracy / Suspicion",
        "candidate_label": "conspiracy and suspicion",
        "description": "Implies hidden agendas, manipulation, or covert plans.",
        "signal_words": "reveals, secret, plot, behind the scenes",
        "color": "#8c564b",
    },
    {
        "frame_slug": "triumphalism_strength",
        "frame_label": "Triumphalism / Strength",
        "candidate_label": "triumphalism and strength",
        "description": "Celebrates power, resilience, capability, or victory.",
        "signal_words": "powerful, resistance, victory, capable",
        "color": "#2ca02c",
    },
)

_FRAME_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_FRAME_EMOJI_RE = re.compile(
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
_FRAME_TRAILING_DELIMITER_RE = re.compile(r"(?:\s*\n?---\s*)+$")


@dataclass(frozen=True)
class RhetoricFramingConfig:
    window_freq: str = "12h"
    text_max_chars: int = 512
    model_batch_size: int = 8
    classifier_model: str = DEFAULT_ZERO_SHOT_MODEL
    device: int = -1
    ambiguous_threshold: float = 0.35
    hypothesis_template: str = "This message primarily uses {}."
    gallery_examples_per_frame: int = 3
    validation_samples_per_frame: int = 4
    validation_random_state: int = 42
    example_preview_chars: int = 220
    frame_colors: dict[str, str] = field(
        default_factory=lambda: {
            record["frame_label"]: record["color"] for record in DEFAULT_FRAME_TAXONOMY
        }
        | {AMBIGUOUS_FRAME_LABEL: "#b0b0b0"}
    )


@dataclass(frozen=True)
class RhetoricFramingResult:
    rhetoric_df_text: pd.DataFrame
    rhetoric_messages_df: pd.DataFrame
    rhetoric_window_df: pd.DataFrame
    rhetoric_window_long_df: pd.DataFrame
    rhetoric_summary_df: pd.DataFrame
    rhetoric_label_counts_df: pd.DataFrame
    rhetoric_half_summary_df: pd.DataFrame
    rhetoric_half_flow_df: pd.DataFrame
    rhetoric_taxonomy_df: pd.DataFrame
    rhetoric_example_messages_df: pd.DataFrame
    rhetoric_validation_sample_df: pd.DataFrame
    rhetoric_sentiment_crosstab_df: pd.DataFrame
    rhetoric_sentiment_share_df: pd.DataFrame
    rhetoric_frame_label_lookup: dict[str, str]
    rhetoric_frame_color_map: dict[str, str]
    rhetoric_over_time_fig: Any
    rhetoric_transition_fig: Any
    rhetoric_examples_fig: Any
    rhetoric_sentiment_heatmap_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "rhetoric_df_text": self.rhetoric_df_text,
            "rhetoric_messages_df": self.rhetoric_messages_df,
            "rhetoric_window_df": self.rhetoric_window_df,
            "rhetoric_window_long_df": self.rhetoric_window_long_df,
            "rhetoric_summary_df": self.rhetoric_summary_df,
            "rhetoric_label_counts_df": self.rhetoric_label_counts_df,
            "rhetoric_half_summary_df": self.rhetoric_half_summary_df,
            "rhetoric_half_flow_df": self.rhetoric_half_flow_df,
            "rhetoric_taxonomy_df": self.rhetoric_taxonomy_df,
            "rhetoric_example_messages_df": self.rhetoric_example_messages_df,
            "rhetoric_validation_sample_df": self.rhetoric_validation_sample_df,
            "rhetoric_sentiment_crosstab_df": self.rhetoric_sentiment_crosstab_df,
            "rhetoric_sentiment_share_df": self.rhetoric_sentiment_share_df,
            "rhetoric_frame_label_lookup": self.rhetoric_frame_label_lookup,
            "rhetoric_frame_color_map": self.rhetoric_frame_color_map,
            "rhetoric_over_time_fig": self.rhetoric_over_time_fig,
            "rhetoric_transition_fig": self.rhetoric_transition_fig,
            "rhetoric_examples_fig": self.rhetoric_examples_fig,
            "rhetoric_sentiment_heatmap_fig": self.rhetoric_sentiment_heatmap_fig,
        }


def clean_rhetoric_text(text: str) -> str:
    cleaned = _FRAME_URL_RE.sub(" ", text or "")
    cleaned = _FRAME_EMOJI_RE.sub(" ", cleaned)
    cleaned = _FRAME_TRAILING_DELIMITER_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _frame_taxonomy_df(config: RhetoricFramingConfig) -> pd.DataFrame:
    taxonomy_rows = []
    for order, record in enumerate(DEFAULT_FRAME_TAXONOMY, start=1):
        taxonomy_rows.append(
            {
                "frame_slug": record["frame_slug"],
                "frame_label": record["frame_label"],
                "candidate_label": record["candidate_label"],
                "description": record["description"],
                "signal_words": record["signal_words"],
                "color": config.frame_colors.get(record["frame_label"], record["color"]),
                "sort_order": order,
            }
        )
    return pd.DataFrame(taxonomy_rows)


def _frame_score_column(frame_slug: str) -> str:
    return f"frame_{frame_slug}"


def _hex_to_rgba(color: str, alpha: float) -> str:
    stripped = color.lstrip("#")
    if len(stripped) != 6:
        return f"rgba(128, 128, 128, {alpha:.3f})"
    red = int(stripped[0:2], 16)
    green = int(stripped[2:4], 16)
    blue = int(stripped[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _prepare_rhetoric_messages(messages: Sequence[RawMessage]) -> pd.DataFrame:
    analysis_records: list[dict[str, Any]] = []
    for message in messages:
        timestamp = pd.to_datetime(message.timestamp, utc=True)
        cleaned_text = clean_rhetoric_text(preferred_message_text(message))
        if not cleaned_text:
            continue
        analysis_records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "text": cleaned_text,
                "raw_text": (message.text or "").strip(),
                "english_text": (message.english_text or "").strip(),
                "has_media": bool(message.media_refs),
                "text_length": len(cleaned_text),
            }
        )

    rhetoric_df_text = pd.DataFrame(analysis_records).sort_values("timestamp").reset_index(drop=True)
    if rhetoric_df_text.empty:
        raise RuntimeError("No text-bearing messages are available after cleaning. Run Sections 3-4 first.")
    return rhetoric_df_text


def _build_zero_shot_classifier(config: RhetoricFramingConfig):
    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Rhetoric framing analysis requires transformers plus a backend such as torch. "
            "Install notebook extras like: pip install transformers torch plotly matplotlib seaborn"
        ) from exc

    return pipeline(
        "zero-shot-classification",
        model=config.classifier_model,
        device=config.device,
    )


def _invoke_zero_shot_classifier(
    classifier: Any,
    batch_texts: Sequence[str],
    candidate_labels: Sequence[str],
    config: RhetoricFramingConfig,
):
    required_kwargs = {
        "candidate_labels": candidate_labels,
        "multi_label": False,
    }
    full_kwargs = {
        **required_kwargs,
        "hypothesis_template": config.hypothesis_template,
        "truncation": True,
        "batch_size": config.model_batch_size,
    }
    try:
        return classifier(batch_texts, **full_kwargs)
    except TypeError:
        try:
            return classifier(
                batch_texts,
                **{
                    **required_kwargs,
                    "hypothesis_template": config.hypothesis_template,
                },
            )
        except TypeError:
            return classifier(batch_texts, **required_kwargs)



def _classify_messages(
    rhetoric_df_text: pd.DataFrame,
    rhetoric_taxonomy_df: pd.DataFrame,
    config: RhetoricFramingConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    classifier = _build_zero_shot_classifier(config)
    candidate_labels = rhetoric_taxonomy_df["candidate_label"].tolist()
    frame_slugs = rhetoric_taxonomy_df["frame_slug"].tolist()
    frame_label_lookup = rhetoric_taxonomy_df.set_index("frame_slug")["frame_label"].to_dict()

    classifier_outputs: list[Mapping[str, Any]] = []
    analysis_texts = rhetoric_df_text["text"].str.slice(0, config.text_max_chars).tolist()
    for start in range(0, len(analysis_texts), config.model_batch_size):
        batch_texts = analysis_texts[start : start + config.model_batch_size]
        batch_outputs = _invoke_zero_shot_classifier(
            classifier,
            batch_texts,
            candidate_labels,
            config,
        )
        if isinstance(batch_outputs, Mapping):
            classifier_outputs.append(batch_outputs)
        else:
            classifier_outputs.extend(batch_outputs)

    if len(classifier_outputs) != len(rhetoric_df_text):
        raise RuntimeError(
            "Zero-shot classifier returned a different number of outputs than input messages. "
            f"Expected {len(rhetoric_df_text)}, got {len(classifier_outputs)}."
        )

    rhetoric_messages_df = rhetoric_df_text.copy()
    for frame_slug in frame_slugs:
        rhetoric_messages_df[_frame_score_column(frame_slug)] = 0.0

    label_by_candidate = rhetoric_taxonomy_df.set_index("candidate_label")["frame_slug"].to_dict()
    for row_index, result in enumerate(classifier_outputs):
        labels = list(result.get("labels", []))
        scores = list(result.get("scores", []))
        label_lookup = {
            label_by_candidate.get(str(label), ""): float(score)
            for label, score in zip(labels, scores)
            if label_by_candidate.get(str(label))
        }
        for frame_slug in frame_slugs:
            rhetoric_messages_df.at[row_index, _frame_score_column(frame_slug)] = label_lookup.get(frame_slug, 0.0)

    score_columns = [_frame_score_column(frame_slug) for frame_slug in frame_slugs]
    rhetoric_messages_df["confidence"] = rhetoric_messages_df[score_columns].max(axis=1)
    rhetoric_messages_df["dominant_frame_slug"] = (
        rhetoric_messages_df[score_columns].idxmax(axis=1).str.removeprefix("frame_")
    )
    rhetoric_messages_df["dominant_frame"] = rhetoric_messages_df["dominant_frame_slug"].map(frame_label_lookup)

    ranked_frame_columns = rhetoric_messages_df[score_columns].apply(
        lambda row: row.sort_values(ascending=False).index.tolist(),
        axis=1,
    )
    ranked_scores = rhetoric_messages_df[score_columns].apply(
        lambda row: row.sort_values(ascending=False).tolist(),
        axis=1,
    )
    rhetoric_messages_df["second_frame_slug"] = [
        frame_columns[1].removeprefix("frame_") if len(frame_columns) > 1 else frame_columns[0].removeprefix("frame_")
        for frame_columns in ranked_frame_columns
    ]
    rhetoric_messages_df["second_frame"] = rhetoric_messages_df["second_frame_slug"].map(frame_label_lookup)
    rhetoric_messages_df["second_confidence"] = [
        float(scores[1]) if len(scores) > 1 else float(scores[0])
        for scores in ranked_scores
    ]
    rhetoric_messages_df["confidence_gap"] = (
        rhetoric_messages_df["confidence"] - rhetoric_messages_df["second_confidence"]
    )

    ambiguous_mask = rhetoric_messages_df["confidence"] < config.ambiguous_threshold
    rhetoric_messages_df.loc[ambiguous_mask, "dominant_frame_slug"] = AMBIGUOUS_FRAME_SLUG
    rhetoric_messages_df.loc[ambiguous_mask, "dominant_frame"] = AMBIGUOUS_FRAME_LABEL

    frame_order = rhetoric_taxonomy_df["frame_label"].tolist()
    ordered_label_counts = frame_order + [AMBIGUOUS_FRAME_LABEL]
    rhetoric_label_counts_df = (
        rhetoric_messages_df["dominant_frame"]
        .value_counts()
        .reindex(ordered_label_counts, fill_value=0)
        .rename_axis("dominant_frame")
        .reset_index(name="message_count")
    )
    rhetoric_label_counts_df["message_share_pct"] = (
        100 * rhetoric_label_counts_df["message_count"] / max(1, len(rhetoric_messages_df))
    ).round(1)

    overall_dominant_frame = rhetoric_label_counts_df.sort_values(
        ["message_count", "dominant_frame"],
        ascending=[False, True],
    ).iloc[0]["dominant_frame"]
    rhetoric_summary_df = pd.DataFrame(
        [
            {
                "messages_scored": len(rhetoric_messages_df),
                "start": rhetoric_messages_df["timestamp"].min(),
                "end": rhetoric_messages_df["timestamp"].max(),
                "ambiguous_threshold": config.ambiguous_threshold,
                "ambiguous_messages": int(ambiguous_mask.sum()),
                "dominant_frame_overall": overall_dominant_frame,
                "messages_using_translation": int(rhetoric_messages_df["used_translation"].sum()),
            }
        ]
    )
    return rhetoric_messages_df, rhetoric_label_counts_df, rhetoric_summary_df


def _aggregate_temporal_windows(
    rhetoric_messages_df: pd.DataFrame,
    rhetoric_taxonomy_df: pd.DataFrame,
    config: RhetoricFramingConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    score_columns = [_frame_score_column(frame_slug) for frame_slug in rhetoric_taxonomy_df["frame_slug"].tolist()]
    frame_label_lookup = rhetoric_taxonomy_df.set_index("frame_slug")["frame_label"].to_dict()

    window_index = pd.date_range(
        rhetoric_messages_df["timestamp"].min().floor(config.window_freq),
        rhetoric_messages_df["timestamp"].max().ceil(config.window_freq),
        freq=config.window_freq,
        tz="UTC",
    )

    aggregated = (
        rhetoric_messages_df.groupby(pd.Grouper(key="timestamp", freq=config.window_freq))
        .agg(
            message_count=("message_id", "size"),
            **{column: (column, "mean") for column in score_columns},
        )
        .reindex(window_index)
    )
    aggregated["message_count"] = aggregated["message_count"].fillna(0).astype(int)
    aggregated[score_columns] = aggregated[score_columns].fillna(0.0)
    aggregated[score_columns] = aggregated[score_columns].div(
        aggregated[score_columns].sum(axis=1).replace(0, pd.NA),
        axis=0,
    ).fillna(0.0)

    rhetoric_window_df = aggregated.reset_index().rename(columns={"index": "timestamp"})
    rhetoric_window_df["dominant_frame_slug"] = rhetoric_window_df[score_columns].idxmax(axis=1).str.removeprefix("frame_")
    rhetoric_window_df.loc[rhetoric_window_df["message_count"] == 0, "dominant_frame_slug"] = ""
    rhetoric_window_df["dominant_frame"] = rhetoric_window_df["dominant_frame_slug"].map(frame_label_lookup).fillna("No data")

    rhetoric_window_long_df = rhetoric_window_df.melt(
        id_vars=["timestamp", "message_count", "dominant_frame", "dominant_frame_slug"],
        value_vars=score_columns,
        var_name="frame_score_column",
        value_name="share",
    )
    rhetoric_window_long_df["frame_slug"] = rhetoric_window_long_df["frame_score_column"].str.removeprefix("frame_")
    rhetoric_window_long_df["frame_label"] = rhetoric_window_long_df["frame_slug"].map(frame_label_lookup)
    rhetoric_window_long_df["share_pct"] = 100 * rhetoric_window_long_df["share"]
    rhetoric_window_long_df = rhetoric_window_long_df.drop(columns="frame_score_column")

    midpoint = rhetoric_messages_df["timestamp"].min() + (
        rhetoric_messages_df["timestamp"].max() - rhetoric_messages_df["timestamp"].min()
    ) / 2
    rhetoric_messages_with_half_df = rhetoric_messages_df.copy()
    rhetoric_messages_with_half_df["period_half"] = rhetoric_messages_with_half_df["timestamp"].map(
        lambda timestamp: "First Half" if timestamp <= midpoint else "Second Half"
    )

    half_order = ["First Half", "Second Half"]
    frame_order = rhetoric_taxonomy_df["frame_label"].tolist()
    frame_order_with_ambiguous = frame_order + [AMBIGUOUS_FRAME_LABEL]

    rhetoric_half_summary_df = (
        rhetoric_messages_with_half_df.groupby(["period_half", "dominant_frame"], observed=False)
        .size()
        .rename("message_count")
        .reset_index()
    )
    rhetoric_half_summary_df["period_half"] = pd.Categorical(
        rhetoric_half_summary_df["period_half"],
        categories=half_order,
        ordered=True,
    )
    rhetoric_half_summary_df["dominant_frame"] = pd.Categorical(
        rhetoric_half_summary_df["dominant_frame"],
        categories=frame_order_with_ambiguous,
        ordered=True,
    )
    rhetoric_half_summary_df = (
        rhetoric_half_summary_df.set_index(["period_half", "dominant_frame"])
        .reindex(
            pd.MultiIndex.from_product(
                [half_order, frame_order_with_ambiguous],
                names=["period_half", "dominant_frame"],
            ),
            fill_value=0,
        )
        .reset_index()
    )
    rhetoric_half_summary_df["share_pct"] = (
        rhetoric_half_summary_df["message_count"]
        / rhetoric_half_summary_df.groupby("period_half", observed=False)["message_count"].transform("sum").replace(0, pd.NA)
        * 100
    ).fillna(0.0).round(1)

    first_half_counts = (
        rhetoric_half_summary_df.loc[rhetoric_half_summary_df["period_half"] == "First Half"]
        .set_index("dominant_frame")["message_count"]
    )
    second_half_counts = (
        rhetoric_half_summary_df.loc[rhetoric_half_summary_df["period_half"] == "Second Half"]
        .set_index("dominant_frame")["message_count"]
    )

    rhetoric_half_flow_rows: list[dict[str, Any]] = []
    total_second_half = float(second_half_counts.sum())
    if total_second_half > 0 and float(first_half_counts.sum()) > 0:
        for source_frame, source_count in first_half_counts.items():
            if source_count <= 0:
                continue
            for target_frame, target_count in second_half_counts.items():
                if target_count <= 0:
                    continue
                rhetoric_half_flow_rows.append(
                    {
                        "source_half": "First Half",
                        "source_frame": source_frame,
                        "target_half": "Second Half",
                        "target_frame": target_frame,
                        "flow_value": float(source_count) * (float(target_count) / total_second_half),
                        "source_count": int(source_count),
                        "target_count": int(target_count),
                    }
                )

    rhetoric_half_flow_df = pd.DataFrame(
        rhetoric_half_flow_rows,
        columns=[
            "source_half",
            "source_frame",
            "target_half",
            "target_frame",
            "flow_value",
            "source_count",
            "target_count",
        ],
    )

    return rhetoric_window_df, rhetoric_window_long_df, rhetoric_half_summary_df, rhetoric_half_flow_df


def _build_example_messages(
    rhetoric_messages_df: pd.DataFrame,
    rhetoric_taxonomy_df: pd.DataFrame,
    config: RhetoricFramingConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame_order = rhetoric_taxonomy_df["frame_label"].tolist()
    rhetoric_example_messages_df = (
        rhetoric_messages_df.loc[rhetoric_messages_df["dominant_frame"] != AMBIGUOUS_FRAME_LABEL]
        .sort_values(["dominant_frame", "confidence", "text_length"], ascending=[True, False, False])
        .groupby("dominant_frame", sort=False)
        .head(config.gallery_examples_per_frame)
        .copy()
    )
    rhetoric_example_messages_df["example_rank"] = rhetoric_example_messages_df.groupby("dominant_frame").cumcount() + 1
    rhetoric_example_messages_df["timestamp_label"] = rhetoric_example_messages_df["timestamp"].dt.strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    rhetoric_example_messages_df["text_preview"] = rhetoric_example_messages_df["text"].map(
        lambda text: textwrap.shorten((text or "").replace("\n", " "), width=config.example_preview_chars, placeholder="...")
    )
    rhetoric_example_messages_df = rhetoric_example_messages_df[
        [
            "dominant_frame",
            "example_rank",
            "timestamp",
            "timestamp_label",
            "confidence",
            "second_frame",
            "second_confidence",
            "text_preview",
            "text",
        ]
    ].reset_index(drop=True)
    rhetoric_example_messages_df["dominant_frame"] = pd.Categorical(
        rhetoric_example_messages_df["dominant_frame"],
        categories=frame_order,
        ordered=True,
    )
    rhetoric_example_messages_df = rhetoric_example_messages_df.sort_values(
        ["dominant_frame", "example_rank"]
    ).reset_index(drop=True)

    validation_group_order = frame_order + [AMBIGUOUS_FRAME_LABEL]

    sampled_groups: list[pd.DataFrame] = []
    for frame_label in validation_group_order:
        group_df = rhetoric_messages_df.loc[rhetoric_messages_df["dominant_frame"] == frame_label].copy()
        if group_df.empty:
            continue
        sample_n = min(config.validation_samples_per_frame, len(group_df))
        sampled_groups.append(group_df.sample(n=sample_n, random_state=config.validation_random_state))

    rhetoric_validation_sample_df = pd.concat(sampled_groups, ignore_index=True) if sampled_groups else pd.DataFrame()
    if not rhetoric_validation_sample_df.empty:
        rhetoric_validation_sample_df["timestamp_label"] = rhetoric_validation_sample_df["timestamp"].dt.strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        rhetoric_validation_sample_df["text_preview"] = rhetoric_validation_sample_df["text"].map(
            lambda text: textwrap.shorten((text or "").replace("\n", " "), width=220, placeholder="...")
        )
        rhetoric_validation_sample_df = rhetoric_validation_sample_df[
            [
                "timestamp",
                "timestamp_label",
                "dominant_frame",
                "confidence",
                "second_frame",
                "second_confidence",
                "confidence_gap",
                "text_preview",
                "text",
            ]
        ].copy()
        rhetoric_validation_sample_df["dominant_frame"] = pd.Categorical(
            rhetoric_validation_sample_df["dominant_frame"],
            categories=validation_group_order,
            ordered=True,
        )
        rhetoric_validation_sample_df = rhetoric_validation_sample_df.sort_values(
            ["dominant_frame", "timestamp"]
        ).reset_index(drop=True)

    return rhetoric_example_messages_df, rhetoric_validation_sample_df


def _build_sentiment_crosstab(
    rhetoric_messages_df: pd.DataFrame,
    rhetoric_taxonomy_df: pd.DataFrame,
    sentiment_emotion_df: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame_order = rhetoric_taxonomy_df["frame_label"].tolist()
    frame_order_with_ambiguous = frame_order + [AMBIGUOUS_FRAME_LABEL]

    if sentiment_emotion_df is None or sentiment_emotion_df.empty:
        empty_counts_df = pd.DataFrame(columns=SENTIMENT_LABEL_ORDER, index=frame_order_with_ambiguous)
        empty_counts_df.index.name = "dominant_frame"
        empty_share_df = empty_counts_df.copy()
        return empty_counts_df, empty_share_df

    required_columns = {"channel_id", "message_id", "dominant_sentiment"}
    if not required_columns.issubset(sentiment_emotion_df.columns):
        empty_counts_df = pd.DataFrame(columns=SENTIMENT_LABEL_ORDER, index=frame_order_with_ambiguous)
        empty_counts_df.index.name = "dominant_frame"
        empty_share_df = empty_counts_df.copy()
        return empty_counts_df, empty_share_df

    merged_df = rhetoric_messages_df.merge(
        sentiment_emotion_df[["channel_id", "message_id", "dominant_sentiment"]].drop_duplicates(
            subset=["channel_id", "message_id"]
        ),
        on=["channel_id", "message_id"],
        how="inner",
    )
    if merged_df.empty:
        empty_counts_df = pd.DataFrame(columns=SENTIMENT_LABEL_ORDER, index=frame_order_with_ambiguous)
        empty_counts_df.index.name = "dominant_frame"
        empty_share_df = empty_counts_df.copy()
        return empty_counts_df, empty_share_df

    rhetoric_sentiment_crosstab_df = pd.crosstab(
        merged_df["dominant_frame"],
        merged_df["dominant_sentiment"],
    ).reindex(index=frame_order_with_ambiguous, columns=SENTIMENT_LABEL_ORDER, fill_value=0)
    rhetoric_sentiment_crosstab_df.index.name = "dominant_frame"
    rhetoric_sentiment_share_df = rhetoric_sentiment_crosstab_df.div(
        rhetoric_sentiment_crosstab_df.sum(axis=1).replace(0, pd.NA),
        axis=0,
    ).fillna(0.0)
    return rhetoric_sentiment_crosstab_df, rhetoric_sentiment_share_df


def _build_over_time_figure(
    rhetoric_window_long_df: pd.DataFrame,
    rhetoric_taxonomy_df: pd.DataFrame,
    rhetoric_frame_color_map: dict[str, str],
    *,
    channel_label: str,
) -> Any:
    try:
        import plotly.express as px
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Rhetoric framing plotting requires plotly. "
            "Install notebook extras like: pip install plotly matplotlib seaborn transformers torch"
        ) from exc

    frame_order = rhetoric_taxonomy_df["frame_label"].tolist()
    area_df = rhetoric_window_long_df.copy()
    area_df["frame_label"] = pd.Categorical(area_df["frame_label"], categories=frame_order, ordered=True)
    area_df = area_df.sort_values(["timestamp", "frame_label"])

    rhetoric_over_time_fig = px.area(
        area_df,
        x="timestamp",
        y="share_pct",
        color="frame_label",
        category_orders={"frame_label": frame_order},
        color_discrete_map=rhetoric_frame_color_map,
        custom_data=["message_count", "share"],
        title=f"{channel_label} Telegram - Rhetorical Framing Over Time",
        template="plotly_white",
    )
    rhetoric_over_time_fig.update_layout(
        legend_title_text="Frame",
        xaxis_title="Timestamp (UTC)",
        yaxis_title="Share of average frame probability",
        yaxis={"range": [0, 100], "ticksuffix": "%"},
        height=520,
        margin={"l": 30, "r": 30, "t": 70, "b": 30},
    )
    rhetoric_over_time_fig.update_traces(
        hovertemplate=(
            "<b>%{fullData.name}</b><br>"
            "Window start: %{x|%Y-%m-%d %H:%M UTC}<br>"
            "Share: %{y:.1f}%<br>"
            "Window messages: %{customdata[0]}<br>"
            "Mean probability: %{customdata[1]:.3f}<extra></extra>"
        )
    )
    return rhetoric_over_time_fig


def _build_transition_figure(
    rhetoric_half_flow_df: pd.DataFrame,
    rhetoric_half_summary_df: pd.DataFrame,
    rhetoric_frame_color_map: dict[str, str],
    *,
    channel_label: str,
) -> Any:
    try:
        import plotly.graph_objects as go
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Rhetoric framing plotting requires plotly. "
            "Install notebook extras like: pip install plotly matplotlib seaborn transformers torch"
        ) from exc

    if rhetoric_half_flow_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title=f"{channel_label} Telegram - First Half vs Second Half Frame Reallocation",
            template="plotly_white",
            height=420,
        )
        fig.add_annotation(
            text="Not enough messages in both halves to build a reallocation Sankey diagram.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        return fig

    first_half_df = rhetoric_half_summary_df.loc[
        (rhetoric_half_summary_df["period_half"] == "First Half") & (rhetoric_half_summary_df["message_count"] > 0)
    ].copy()
    second_half_df = rhetoric_half_summary_df.loc[
        (rhetoric_half_summary_df["period_half"] == "Second Half") & (rhetoric_half_summary_df["message_count"] > 0)
    ].copy()

    source_nodes = [
        {
            "node_id": f"first::{row.dominant_frame}",
            "label": f"First Half · {row.dominant_frame}<br>n={int(row.message_count)}",
            "frame_label": str(row.dominant_frame),
        }
        for row in first_half_df.itertuples(index=False)
    ]
    target_nodes = [
        {
            "node_id": f"second::{row.dominant_frame}",
            "label": f"Second Half · {row.dominant_frame}<br>n={int(row.message_count)}",
            "frame_label": str(row.dominant_frame),
        }
        for row in second_half_df.itertuples(index=False)
    ]
    nodes = source_nodes + target_nodes
    node_index_lookup = {node["node_id"]: index for index, node in enumerate(nodes)}

    link_source = []
    link_target = []
    link_value = []
    link_color = []
    for row in rhetoric_half_flow_df.itertuples(index=False):
        source_id = f"first::{row.source_frame}"
        target_id = f"second::{row.target_frame}"
        if source_id not in node_index_lookup or target_id not in node_index_lookup:
            continue
        link_source.append(node_index_lookup[source_id])
        link_target.append(node_index_lookup[target_id])
        link_value.append(float(row.flow_value))
        link_color.append(_hex_to_rgba(rhetoric_frame_color_map.get(str(row.source_frame), "#b0b0b0"), 0.35))

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node={
                    "label": [node["label"] for node in nodes],
                    "pad": 18,
                    "thickness": 18,
                    "color": [rhetoric_frame_color_map.get(node["frame_label"], "#b0b0b0") for node in nodes],
                    "line": {"color": "rgba(80, 80, 80, 0.35)", "width": 0.5},
                },
                link={
                    "source": link_source,
                    "target": link_target,
                    "value": link_value,
                    "color": link_color,
                },
            )
        ]
    )
    fig.update_layout(
        title=(
            f"{channel_label} Telegram - First Half vs Second Half Frame Reallocation"
            "<br><sup>Flows show proportional redistribution between half-period frame mixes, not message-level trajectories.</sup>"
        ),
        template="plotly_white",
        height=520,
        margin={"l": 20, "r": 20, "t": 80, "b": 20},
        font={"size": 11},
    )
    return fig


def _build_examples_figure(
    rhetoric_example_messages_df: pd.DataFrame,
    rhetoric_taxonomy_df: pd.DataFrame,
    rhetoric_frame_color_map: dict[str, str],
    *,
    channel_label: str,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Rhetoric example plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib seaborn plotly transformers torch"
        ) from exc

    frame_order = rhetoric_taxonomy_df["frame_label"].tolist()
    rows, cols = subplot_grid(len(frame_order), max_cols=2)
    fig, axes = plt.subplots(rows, cols, figsize=(18, max(10, rows * 4.2)), constrained_layout=True)
    if hasattr(axes, "flatten"):
        axes_list = list(axes.flatten())
    elif isinstance(axes, (list, tuple)):
        axes_list = list(axes)
    else:
        axes_list = [axes]

    example_lookup = {
        frame_label: rhetoric_example_messages_df.loc[rhetoric_example_messages_df["dominant_frame"] == frame_label]
        for frame_label in frame_order
    }

    for ax, frame_label in zip(axes_list, frame_order):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        frame_color = rhetoric_frame_color_map.get(frame_label, "#cccccc")
        ax.add_patch(
            Rectangle(
                (0.01, 0.01),
                0.98,
                0.98,
                transform=ax.transAxes,
                fill=False,
                edgecolor=frame_color,
                linewidth=2.2,
            )
        )
        ax.text(
            0.03,
            0.95,
            frame_label,
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=12,
            fontweight="bold",
            color=frame_color,
        )

        panel_df = example_lookup.get(frame_label)
        if panel_df is None or panel_df.empty:
            ax.text(
                0.04,
                0.78,
                "No high-confidence examples in this run.",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9.5,
                color="#444444",
            )
            continue

        top_y = 0.82
        y_step = 0.26
        for item_index, row in enumerate(panel_df.itertuples(index=False), start=1):
            preview_text = textwrap.fill(str(row.text_preview), width=54)
            timestamp_label = getattr(row, "timestamp_label", pd.Timestamp(row.timestamp).strftime("%Y-%m-%d %H:%M UTC"))
            ax.text(
                0.04,
                top_y - (item_index - 1) * y_step,
                f"#{int(row.example_rank)} · confidence {float(row.confidence):.2f} · {timestamp_label}\n{preview_text}",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                color="#222222",
            )

    for extra_ax in axes_list[len(frame_order) :]:
        extra_ax.set_visible(False)

    fig.suptitle(
        f"{channel_label} Telegram - Highest-Confidence Message Examples by Frame",
        fontsize=15,
        y=1.01,
    )
    return fig


def _build_sentiment_heatmap_figure(
    rhetoric_sentiment_crosstab_df: pd.DataFrame,
    *,
    channel_label: str,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Rhetoric sentiment plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn plotly transformers torch"
        ) from exc

    if rhetoric_sentiment_crosstab_df.empty or rhetoric_sentiment_crosstab_df.sum().sum() == 0:
        return None

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, max(4.5, 0.65 * len(rhetoric_sentiment_crosstab_df.index) + 1.2)))
    sns.heatmap(
        rhetoric_sentiment_crosstab_df,
        annot=True,
        fmt="d",
        cmap="YlGnBu",
        linewidths=0.5,
        linecolor="#e6e6e6",
        cbar_kws={"label": "Message count"},
        ax=ax,
    )
    ax.set_xlabel("Dominant sentiment")
    ax.set_ylabel("Dominant rhetorical frame")
    ax.set_title(f"{channel_label} Telegram - Rhetorical Frame × Sentiment")
    ax.set_xticklabels([label.title() for label in rhetoric_sentiment_crosstab_df.columns], rotation=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    fig.tight_layout()
    return fig


def run_rhetoric_framing_analysis(
    translated_messages: Sequence[RawMessage],
    *,
    channel_label: str,
    sentiment_emotion_df: pd.DataFrame | None = None,
    config: RhetoricFramingConfig | None = None,
) -> RhetoricFramingResult:
    config = config or RhetoricFramingConfig()
    started_at = time.monotonic()

    rhetoric_taxonomy_df = _frame_taxonomy_df(config)
    rhetoric_frame_label_lookup = rhetoric_taxonomy_df.set_index("frame_slug")["frame_label"].to_dict() | {
        AMBIGUOUS_FRAME_SLUG: AMBIGUOUS_FRAME_LABEL
    }
    rhetoric_frame_color_map = rhetoric_taxonomy_df.set_index("frame_label")["color"].to_dict() | {
        AMBIGUOUS_FRAME_LABEL: config.frame_colors.get(AMBIGUOUS_FRAME_LABEL, "#b0b0b0")
    }

    rhetoric_df_text = _prepare_rhetoric_messages(translated_messages)
    rhetoric_messages_df, rhetoric_label_counts_df, rhetoric_summary_df = _classify_messages(
        rhetoric_df_text,
        rhetoric_taxonomy_df,
        config,
    )
    (
        rhetoric_window_df,
        rhetoric_window_long_df,
        rhetoric_half_summary_df,
        rhetoric_half_flow_df,
    ) = _aggregate_temporal_windows(rhetoric_messages_df, rhetoric_taxonomy_df, config)
    rhetoric_example_messages_df, rhetoric_validation_sample_df = _build_example_messages(
        rhetoric_messages_df,
        rhetoric_taxonomy_df,
        config,
    )
    rhetoric_sentiment_crosstab_df, rhetoric_sentiment_share_df = _build_sentiment_crosstab(
        rhetoric_messages_df,
        rhetoric_taxonomy_df,
        sentiment_emotion_df,
    )

    rhetoric_over_time_fig = _build_over_time_figure(
        rhetoric_window_long_df,
        rhetoric_taxonomy_df,
        rhetoric_frame_color_map,
        channel_label=channel_label,
    )
    rhetoric_transition_fig = _build_transition_figure(
        rhetoric_half_flow_df,
        rhetoric_half_summary_df,
        rhetoric_frame_color_map,
        channel_label=channel_label,
    )
    rhetoric_examples_fig = _build_examples_figure(
        rhetoric_example_messages_df,
        rhetoric_taxonomy_df,
        rhetoric_frame_color_map,
        channel_label=channel_label,
    )
    rhetoric_sentiment_heatmap_fig = _build_sentiment_heatmap_figure(
        rhetoric_sentiment_crosstab_df,
        channel_label=channel_label,
    )

    return RhetoricFramingResult(
        rhetoric_df_text=rhetoric_df_text,
        rhetoric_messages_df=rhetoric_messages_df,
        rhetoric_window_df=rhetoric_window_df,
        rhetoric_window_long_df=rhetoric_window_long_df,
        rhetoric_summary_df=rhetoric_summary_df,
        rhetoric_label_counts_df=rhetoric_label_counts_df,
        rhetoric_half_summary_df=rhetoric_half_summary_df,
        rhetoric_half_flow_df=rhetoric_half_flow_df,
        rhetoric_taxonomy_df=rhetoric_taxonomy_df,
        rhetoric_example_messages_df=rhetoric_example_messages_df,
        rhetoric_validation_sample_df=rhetoric_validation_sample_df,
        rhetoric_sentiment_crosstab_df=rhetoric_sentiment_crosstab_df,
        rhetoric_sentiment_share_df=rhetoric_sentiment_share_df,
        rhetoric_frame_label_lookup=rhetoric_frame_label_lookup,
        rhetoric_frame_color_map=rhetoric_frame_color_map,
        rhetoric_over_time_fig=rhetoric_over_time_fig,
        rhetoric_transition_fig=rhetoric_transition_fig,
        rhetoric_examples_fig=rhetoric_examples_fig,
        rhetoric_sentiment_heatmap_fig=rhetoric_sentiment_heatmap_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
