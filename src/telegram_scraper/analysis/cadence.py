from __future__ import annotations

import textwrap
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

_DAY_NAME_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class MessagingCadenceConfig:
    hour_freq: str = "1h"
    top_spike_candidates: int = 10
    annotated_spikes: int = 3
    preview_chars: int = 100
    calendar_cmap: str = "YlOrRd"
    rhythm_cmap: str = "YlGnBu"


@dataclass(frozen=True)
class MessagingCadenceResult:
    cadence_messages_df: pd.DataFrame
    cadence_hourly_counts_df: pd.DataFrame
    cadence_daily_counts_df: pd.DataFrame
    cadence_calendar_heatmap_df: pd.DataFrame
    cadence_structural_rhythm_df: pd.DataFrame
    cadence_media_hourly_df: pd.DataFrame
    cadence_top_spikes_df: pd.DataFrame
    cadence_spike_messages_df: pd.DataFrame
    cadence_daily_summary_df: pd.DataFrame
    cadence_event_annotations_df: pd.DataFrame
    cadence_weekday_observation_df: pd.DataFrame
    cadence_summary_df: pd.DataFrame
    cadence_calendar_heatmap_fig: Any
    cadence_structural_rhythm_fig: Any
    cadence_volume_media_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "cadence_messages_df": self.cadence_messages_df,
            "cadence_hourly_counts_df": self.cadence_hourly_counts_df,
            "cadence_daily_counts_df": self.cadence_daily_counts_df,
            "cadence_calendar_heatmap_df": self.cadence_calendar_heatmap_df,
            "cadence_structural_rhythm_df": self.cadence_structural_rhythm_df,
            "cadence_media_hourly_df": self.cadence_media_hourly_df,
            "cadence_top_spikes_df": self.cadence_top_spikes_df,
            "cadence_spike_messages_df": self.cadence_spike_messages_df,
            "cadence_daily_summary_df": self.cadence_daily_summary_df,
            "cadence_event_annotations_df": self.cadence_event_annotations_df,
            "cadence_weekday_observation_df": self.cadence_weekday_observation_df,
            "cadence_summary_df": self.cadence_summary_df,
            "cadence_calendar_heatmap_fig": self.cadence_calendar_heatmap_fig,
            "cadence_structural_rhythm_fig": self.cadence_structural_rhythm_fig,
            "cadence_volume_media_fig": self.cadence_volume_media_fig,
        }


def _preview_text(text: str, *, width: int) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return "(media-only message)"
    return textwrap.shorten(cleaned, width=width, placeholder="...")


def _prepare_cadence_messages(messages: Sequence[RawMessage], config: MessagingCadenceConfig) -> pd.DataFrame:
    cadence_records: list[dict[str, Any]] = []
    for message in messages:
        timestamp = pd.to_datetime(message.timestamp, utc=True)
        message_text = (preferred_message_text(message) or "").strip()
        cadence_records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "date_only": timestamp.date(),
                "hour": timestamp.hour,
                "day_of_week": timestamp.dayofweek,
                "day_name": timestamp.day_name(),
                "has_media": bool(message.media_refs),
                "is_media_only": message.is_media_only,
                "text": message_text,
                "text_preview": _preview_text(message_text, width=config.preview_chars),
            }
        )

    cadence_messages_df = pd.DataFrame(cadence_records).sort_values(["timestamp", "message_id"]).reset_index(drop=True)
    if cadence_messages_df.empty:
        raise RuntimeError("No messages are available for messaging cadence analysis. Run Section 3 first.")
    return cadence_messages_df


def _aggregate_cadence(
    cadence_messages_df: pd.DataFrame,
    config: MessagingCadenceConfig,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    hourly_index = pd.date_range(
        cadence_messages_df["timestamp"].min().floor(config.hour_freq),
        cadence_messages_df["timestamp"].max().floor(config.hour_freq),
        freq=config.hour_freq,
        tz="UTC",
    )
    daily_index = pd.date_range(
        cadence_messages_df["timestamp"].min().floor("D"),
        cadence_messages_df["timestamp"].max().floor("D"),
        freq="D",
        tz="UTC",
    )

    cadence_messages_with_hour_df = cadence_messages_df.copy()
    cadence_messages_with_hour_df["hour_bucket"] = cadence_messages_with_hour_df["timestamp"].dt.floor(config.hour_freq)

    hourly_agg_df = (
        cadence_messages_with_hour_df.groupby("hour_bucket")
        .agg(
            message_count=("message_id", "size"),
            media_count=("has_media", "sum"),
        )
        .reindex(hourly_index, fill_value=0)
        .rename_axis("timestamp")
        .reset_index()
    )
    hourly_agg_df["message_count"] = hourly_agg_df["message_count"].astype(int)
    hourly_agg_df["media_count"] = hourly_agg_df["media_count"].astype(int)
    hourly_agg_df["text_only_count"] = hourly_agg_df["message_count"] - hourly_agg_df["media_count"]
    hourly_message_denominator = hourly_agg_df["message_count"].astype(float).where(hourly_agg_df["message_count"] > 0)
    hourly_agg_df["media_pct"] = hourly_agg_df["media_count"].div(hourly_message_denominator).mul(100).round(1)
    hourly_agg_df["date"] = hourly_agg_df["timestamp"].dt.floor("D")
    hourly_agg_df["hour"] = hourly_agg_df["timestamp"].dt.hour
    hourly_agg_df["day_of_week"] = hourly_agg_df["timestamp"].dt.dayofweek
    hourly_agg_df["day_name"] = hourly_agg_df["timestamp"].dt.day_name()

    cadence_hourly_counts_df = hourly_agg_df[
        ["timestamp", "date", "hour", "day_of_week", "day_name", "message_count"]
    ].copy()
    cadence_media_hourly_df = hourly_agg_df[
        [
            "timestamp",
            "date",
            "hour",
            "day_of_week",
            "day_name",
            "message_count",
            "media_count",
            "text_only_count",
            "media_pct",
        ]
    ].copy()

    cadence_daily_counts_df = (
        cadence_messages_df.groupby("date")
        .agg(
            message_count=("message_id", "size"),
            media_count=("has_media", "sum"),
        )
        .reindex(daily_index, fill_value=0)
        .rename_axis("date")
        .reset_index()
    )
    cadence_daily_counts_df["message_count"] = cadence_daily_counts_df["message_count"].astype(int)
    cadence_daily_counts_df["media_count"] = cadence_daily_counts_df["media_count"].astype(int)
    cadence_daily_counts_df["text_only_count"] = (
        cadence_daily_counts_df["message_count"] - cadence_daily_counts_df["media_count"]
    )
    daily_message_denominator = cadence_daily_counts_df["message_count"].astype(float).where(
        cadence_daily_counts_df["message_count"] > 0
    )
    cadence_daily_counts_df["media_pct"] = cadence_daily_counts_df["media_count"].div(daily_message_denominator).mul(100).round(1)
    cadence_daily_counts_df["day_of_week"] = cadence_daily_counts_df["date"].dt.dayofweek
    cadence_daily_counts_df["day_name"] = cadence_daily_counts_df["date"].dt.day_name()

    cadence_calendar_heatmap_df = (
        cadence_hourly_counts_df.pivot(index="date", columns="hour", values="message_count")
        .reindex(index=daily_index, columns=range(24), fill_value=0)
        .fillna(0)
        .astype(int)
    )
    cadence_calendar_heatmap_df.index.name = "date"
    cadence_calendar_heatmap_df.columns.name = "hour"

    calendar_long_df = (
        cadence_calendar_heatmap_df.reset_index()
        .melt(id_vars="date", var_name="hour", value_name="message_count")
        .astype({"hour": int, "message_count": int})
    )
    calendar_long_df["day_of_week"] = calendar_long_df["date"].dt.dayofweek

    cadence_weekday_observation_df = pd.DataFrame(
        {
            "day_of_week": range(7),
            "day_name": _DAY_NAME_SHORT,
            "days_observed": [int((daily_index.dayofweek == day_of_week).sum()) for day_of_week in range(7)],
        }
    )

    cadence_structural_rhythm_df = (
        calendar_long_df.groupby(["day_of_week", "hour"])["message_count"]
        .mean()
        .unstack(fill_value=0.0)
        .reindex(index=range(7), columns=range(24), fill_value=0.0)
        .round(2)
    )
    cadence_structural_rhythm_df.index = [
        _DAY_NAME_SHORT[day_of_week] for day_of_week in cadence_structural_rhythm_df.index
    ]
    cadence_structural_rhythm_df.index.name = "day_name"
    cadence_structural_rhythm_df.columns.name = "hour"

    representative_hour_df = (
        cadence_messages_with_hour_df.assign(text_length=cadence_messages_with_hour_df["text"].str.len())
        .sort_values(["hour_bucket", "text_length", "timestamp", "message_id"], ascending=[True, False, True, True])
        .drop_duplicates("hour_bucket")
        [["hour_bucket", "message_id", "text", "text_preview"]]
        .rename(
            columns={
                "hour_bucket": "timestamp",
                "message_id": "representative_message_id",
                "text": "representative_text",
                "text_preview": "representative_preview",
            }
        )
    )

    cadence_top_spikes_df = (
        cadence_media_hourly_df.loc[cadence_media_hourly_df["message_count"] > 0]
        .sort_values(["message_count", "media_count", "timestamp"], ascending=[False, False, True])
        .head(config.top_spike_candidates)
        .merge(representative_hour_df, on="timestamp", how="left")
        .reset_index(drop=True)
    )
    cadence_top_spikes_df.insert(0, "spike_rank", range(1, len(cadence_top_spikes_df) + 1))
    cadence_top_spikes_df["timestamp_label"] = cadence_top_spikes_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M UTC")
    cadence_top_spikes_df["candidate_label"] = [
        f"{timestamp_label} — {preview or '(media-only message)'}"
        for timestamp_label, preview in zip(
            cadence_top_spikes_df["timestamp_label"],
            cadence_top_spikes_df["representative_preview"].fillna("(media-only message)"),
        )
    ]

    top_spike_lookup = cadence_top_spikes_df.set_index("timestamp")["spike_rank"].to_dict()
    spike_volume_lookup = cadence_top_spikes_df.set_index("timestamp")["message_count"].to_dict()
    cadence_spike_messages_df = cadence_messages_with_hour_df.loc[
        cadence_messages_with_hour_df["hour_bucket"].isin(list(top_spike_lookup))
    ].copy()
    cadence_spike_messages_df["spike_rank"] = cadence_spike_messages_df["hour_bucket"].map(top_spike_lookup).astype(int)
    cadence_spike_messages_df["hour_start"] = cadence_spike_messages_df["hour_bucket"]
    cadence_spike_messages_df["hour_message_count"] = cadence_spike_messages_df["hour_bucket"].map(spike_volume_lookup).astype(int)
    cadence_spike_messages_df = cadence_spike_messages_df.sort_values(
        ["spike_rank", "timestamp", "message_id"],
        ascending=[True, True, True],
    ).reset_index(drop=True)
    cadence_spike_messages_df = cadence_spike_messages_df[
        [
            "spike_rank",
            "hour_start",
            "hour_message_count",
            "timestamp",
            "message_id",
            "has_media",
            "is_media_only",
            "text_preview",
            "text",
        ]
    ]

    daily_peak_hour_df = (
        cadence_calendar_heatmap_df.idxmax(axis=1).rename("peak_hour_int").reset_index().rename(columns={"index": "date"})
    )
    daily_peak_hour_df["peak_count"] = cadence_calendar_heatmap_df.max(axis=1).to_numpy(dtype=int)
    daily_peak_hour_df["peak_hour"] = daily_peak_hour_df["peak_hour_int"].map(lambda hour: f"{int(hour):02d}:00")
    daily_peak_hour_df.loc[daily_peak_hour_df["peak_count"] == 0, "peak_hour"] = "—"

    cadence_daily_summary_df = cadence_daily_counts_df.merge(
        daily_peak_hour_df[["date", "peak_hour", "peak_count"]],
        on="date",
        how="left",
    )
    cadence_daily_summary_df = cadence_daily_summary_df.rename(
        columns={
            "message_count": "total_messages",
            "media_count": "with_media",
            "text_only_count": "text_only",
        }
    )
    cadence_daily_summary_df = cadence_daily_summary_df[
        [
            "date",
            "day_name",
            "total_messages",
            "with_media",
            "text_only",
            "media_pct",
            "peak_hour",
            "peak_count",
        ]
    ]

    busiest_day_row = cadence_daily_counts_df.sort_values(["message_count", "date"], ascending=[False, True]).iloc[0]
    peak_hour_row = cadence_top_spikes_df.iloc[0] if not cadence_top_spikes_df.empty else None
    cadence_summary_df = pd.DataFrame(
        [
            {
                "messages_analyzed": len(cadence_messages_df),
                "start": cadence_messages_df["timestamp"].min(),
                "end": cadence_messages_df["timestamp"].max(),
                "observed_days": len(daily_index),
                "average_messages_per_day": round(float(cadence_daily_counts_df["message_count"].mean()), 1),
                "overall_media_pct": round(float(cadence_messages_df["has_media"].mean() * 100), 1),
                "busiest_day": busiest_day_row["date"],
                "busiest_day_count": int(busiest_day_row["message_count"]),
                "peak_hour": peak_hour_row["timestamp"] if peak_hour_row is not None else pd.NaT,
                "peak_hour_count": int(peak_hour_row["message_count"]) if peak_hour_row is not None else 0,
            }
        ]
    )

    return (
        cadence_hourly_counts_df,
        cadence_daily_counts_df,
        cadence_calendar_heatmap_df,
        cadence_structural_rhythm_df,
        cadence_media_hourly_df,
        cadence_top_spikes_df,
        cadence_spike_messages_df,
        cadence_daily_summary_df,
        cadence_weekday_observation_df,
        cadence_summary_df,
    )


def _build_event_annotations(
    cadence_top_spikes_df: pd.DataFrame,
    event_annotations: Sequence[Mapping[str, Any]] | None,
    config: MessagingCadenceConfig,
) -> pd.DataFrame:
    if event_annotations:
        cadence_event_annotations_df = pd.DataFrame(event_annotations)
        if cadence_event_annotations_df.empty:
            return pd.DataFrame(columns=["timestamp", "label"])
        cadence_event_annotations_df["timestamp"] = pd.to_datetime(
            cadence_event_annotations_df["timestamp"],
            utc=True,
        ).dt.floor(config.hour_freq)
        cadence_event_annotations_df["label"] = cadence_event_annotations_df["label"].fillna("").astype(str)
        cadence_event_annotations_df = cadence_event_annotations_df.loc[
            cadence_event_annotations_df["label"].str.strip().ne("")
        ]
        return cadence_event_annotations_df[["timestamp", "label"]].drop_duplicates("timestamp").sort_values(
            "timestamp"
        ).reset_index(drop=True)

    cadence_event_annotations_df = cadence_top_spikes_df[["timestamp", "candidate_label"]].head(config.annotated_spikes).copy()
    cadence_event_annotations_df = cadence_event_annotations_df.rename(columns={"candidate_label": "label"})
    return cadence_event_annotations_df.reset_index(drop=True)


def _build_calendar_heatmap_figure(
    cadence_calendar_heatmap_df: pd.DataFrame,
    cadence_event_annotations_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MessagingCadenceConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        from matplotlib.patches import Rectangle
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Messaging cadence plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn numpy"
        ) from exc

    sns.set_theme(style="whitegrid")
    plot_df = cadence_calendar_heatmap_df.copy()
    plot_df.index = [pd.Timestamp(date).strftime("%b %d") for date in plot_df.index]

    footer_line_count = len(cadence_event_annotations_df)
    bottom_margin = min(0.36, 0.12 + 0.045 * footer_line_count)
    fig, ax = plt.subplots(figsize=(18, max(4.5, len(plot_df) * 0.62 + 1.4)))
    fig.subplots_adjust(bottom=bottom_margin)

    sns.heatmap(
        plot_df,
        cmap=config.calendar_cmap,
        linewidths=0.5,
        linecolor="#e6e6e6",
        annot=True,
        fmt="d",
        cbar_kws={"label": "Messages per hour"},
        ax=ax,
    )

    date_lookup = {pd.Timestamp(date): row_index for row_index, date in enumerate(cadence_calendar_heatmap_df.index)}
    footnotes: list[str] = []
    for annotation_index, row in enumerate(cadence_event_annotations_df.itertuples(index=False), start=1):
        timestamp = pd.Timestamp(row.timestamp).tz_convert("UTC") if pd.Timestamp(row.timestamp).tzinfo else pd.Timestamp(row.timestamp).tz_localize("UTC")
        date = timestamp.floor("D")
        if date not in date_lookup:
            continue

        row_index = date_lookup[date]
        col_index = int(timestamp.hour)
        ax.add_patch(Rectangle((col_index, row_index), 1, 1, fill=False, edgecolor="black", linewidth=2.2))
        ax.scatter(
            col_index + 0.5,
            row_index + 0.5,
            s=180,
            facecolor="black",
            edgecolor="white",
            linewidth=1.0,
            zorder=6,
        )
        ax.text(
            col_index + 0.5,
            row_index + 0.5,
            str(annotation_index),
            ha="center",
            va="center",
            color="white",
            fontsize=8,
            fontweight="bold",
            zorder=7,
        )
        footnotes.append(f"{annotation_index}. {textwrap.shorten(str(row.label), width=120, placeholder='...')}")

    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Date")
    ax.set_title(f"{channel_label} Telegram - Hourly Message Volume")
    ax.set_xticklabels([f"{int(hour):02d}" for hour in cadence_calendar_heatmap_df.columns], rotation=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)

    for footnote_index, footnote in enumerate(footnotes):
        fig.text(
            0.01,
            0.025 + 0.038 * (len(footnotes) - footnote_index - 1),
            footnote,
            ha="left",
            va="bottom",
            fontsize=8.8,
            color="#222222",
        )

    return fig


def _build_structural_rhythm_figure(
    cadence_structural_rhythm_df: pd.DataFrame,
    cadence_weekday_observation_df: pd.DataFrame,
    *,
    channel_label: str,
    config: MessagingCadenceConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Messaging cadence plotting requires matplotlib and seaborn. "
            "Install notebook extras like: pip install matplotlib seaborn numpy"
        ) from exc

    sns.set_theme(style="whitegrid")
    day_counts = cadence_weekday_observation_df.set_index("day_name")["days_observed"].to_dict()
    y_tick_labels = [f"{day_name} (n={int(day_counts.get(day_name, 0))})" for day_name in cadence_structural_rhythm_df.index]

    fig, ax = plt.subplots(figsize=(18, 6))
    sns.heatmap(
        cadence_structural_rhythm_df,
        cmap=config.rhythm_cmap,
        linewidths=0.5,
        linecolor="#e6e6e6",
        annot=True,
        fmt=".1f",
        cbar_kws={"label": "Average messages per observed day"},
        ax=ax,
    )
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Day of week")
    ax.set_title(f"{channel_label} Telegram - Structural Posting Rhythm")
    ax.set_xticklabels([f"{int(hour):02d}" for hour in cadence_structural_rhythm_df.columns], rotation=0)
    ax.set_yticklabels(y_tick_labels, rotation=0)
    fig.tight_layout()
    return fig


def _build_volume_media_figure(
    cadence_media_hourly_df: pd.DataFrame,
    cadence_summary_df: pd.DataFrame,
    *,
    channel_label: str,
) -> Any:
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Messaging cadence plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib seaborn numpy"
        ) from exc

    overall_media_pct = float(cadence_summary_df["overall_media_pct"].iat[0]) if not cadence_summary_df.empty else 0.0
    bar_width = pd.Timedelta(minutes=50) / pd.Timedelta(days=1)

    fig, ax1 = plt.subplots(figsize=(18, 5.5))
    ax1.bar(
        cadence_media_hourly_df["timestamp"],
        cadence_media_hourly_df["message_count"],
        width=bar_width,
        color="#f39c12",
        alpha=0.78,
        label="Messages per hour",
    )
    ax1.set_ylabel("Messages per hour")
    ax1.set_xlabel("Timestamp (UTC)")
    ax1.set_ylim(bottom=0)
    ax1.grid(axis="y", alpha=0.22)

    ax2 = ax1.twinx()
    ax2.plot(
        cadence_media_hourly_df["timestamp"],
        cadence_media_hourly_df["media_pct"],
        color="#1f77b4",
        linewidth=2.2,
        marker="o",
        markersize=3.5,
        label="Media share per hour",
    )
    ax2.axhline(
        overall_media_pct,
        color="#1f77b4",
        linestyle="--",
        linewidth=1.3,
        alpha=0.75,
        label=f"Overall media baseline ({overall_media_pct:.1f}%)",
    )
    ax2.set_ylabel("Messages with media (%)")
    ax2.set_ylim(0, 100)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    ax1.set_title(f"{channel_label} Telegram - Hourly Volume and Media Share")

    handles_1, labels_1 = ax1.get_legend_handles_labels()
    handles_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(handles_1 + handles_2, labels_1 + labels_2, loc="upper left", frameon=True, ncol=3)
    fig.tight_layout()
    return fig


def run_messaging_cadence_analysis(
    messages: Sequence[RawMessage],
    *,
    channel_label: str,
    event_annotations: Sequence[Mapping[str, Any]] | None = None,
    config: MessagingCadenceConfig | None = None,
) -> MessagingCadenceResult:
    config = config or MessagingCadenceConfig()
    started_at = time.monotonic()

    cadence_messages_df = _prepare_cadence_messages(messages, config)
    (
        cadence_hourly_counts_df,
        cadence_daily_counts_df,
        cadence_calendar_heatmap_df,
        cadence_structural_rhythm_df,
        cadence_media_hourly_df,
        cadence_top_spikes_df,
        cadence_spike_messages_df,
        cadence_daily_summary_df,
        cadence_weekday_observation_df,
        cadence_summary_df,
    ) = _aggregate_cadence(cadence_messages_df, config)
    cadence_event_annotations_df = _build_event_annotations(cadence_top_spikes_df, event_annotations, config)

    cadence_calendar_heatmap_fig = _build_calendar_heatmap_figure(
        cadence_calendar_heatmap_df,
        cadence_event_annotations_df,
        channel_label=channel_label,
        config=config,
    )
    cadence_structural_rhythm_fig = _build_structural_rhythm_figure(
        cadence_structural_rhythm_df,
        cadence_weekday_observation_df,
        channel_label=channel_label,
        config=config,
    )
    cadence_volume_media_fig = _build_volume_media_figure(
        cadence_media_hourly_df,
        cadence_summary_df,
        channel_label=channel_label,
    )

    return MessagingCadenceResult(
        cadence_messages_df=cadence_messages_df,
        cadence_hourly_counts_df=cadence_hourly_counts_df,
        cadence_daily_counts_df=cadence_daily_counts_df,
        cadence_calendar_heatmap_df=cadence_calendar_heatmap_df,
        cadence_structural_rhythm_df=cadence_structural_rhythm_df,
        cadence_media_hourly_df=cadence_media_hourly_df,
        cadence_top_spikes_df=cadence_top_spikes_df,
        cadence_spike_messages_df=cadence_spike_messages_df,
        cadence_daily_summary_df=cadence_daily_summary_df,
        cadence_event_annotations_df=cadence_event_annotations_df,
        cadence_weekday_observation_df=cadence_weekday_observation_df,
        cadence_summary_df=cadence_summary_df,
        cadence_calendar_heatmap_fig=cadence_calendar_heatmap_fig,
        cadence_structural_rhythm_fig=cadence_structural_rhythm_fig,
        cadence_volume_media_fig=cadence_volume_media_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
