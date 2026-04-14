from __future__ import annotations

import math
import re
import textwrap
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation, subplot_grid
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

DEFAULT_CORRECTION_KEYWORDS = (
    "correction",
    "clarification",
    "clarifies",
    "clarified",
    "corrected",
    "earlier",
    "update:",
    "updated:",
    "revised",
    "editor's note",
)
DEFAULT_MEDIA_COLOR = "#1f77b4"
DEFAULT_TEXT_ONLY_COLOR = "#9aa0a6"
DEFAULT_EXTERNAL_NODE_COLOR = "#ffffff"
_DEFAULT_MAX_TIMESTAMP = pd.Timestamp("2262-01-01", tz="UTC")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")


@dataclass(frozen=True)
class ReplyThreadingConfig:
    top_replied_messages: int = 20
    content_review_parents: int = 10
    top_threads: int = 5
    distribution_overflow_bucket: int = 3
    preview_chars: int = 110
    tree_label_chars: int = 60
    outlier_annotations: int = 6
    first_reply_hist_bins: int = 20
    similarity_update_threshold: float = 0.72
    similarity_related_threshold: float = 0.35
    correction_keywords: tuple[str, ...] = DEFAULT_CORRECTION_KEYWORDS


@dataclass(frozen=True)
class ReplyThreadingResult:
    reply_messages_df: pd.DataFrame
    reply_edges_df: pd.DataFrame
    reply_top_replied_df: pd.DataFrame
    reply_thread_summary_df: pd.DataFrame
    reply_distribution_df: pd.DataFrame
    reply_hourly_reply_rate_df: pd.DataFrame
    reply_feature_tests_df: pd.DataFrame
    reply_media_contingency_df: pd.DataFrame
    reply_first_reply_timing_df: pd.DataFrame
    reply_content_review_df: pd.DataFrame
    reply_summary_df: pd.DataFrame
    reply_graph: Any
    reply_distribution_fig: Any
    reply_threads_fig: Any
    reply_scatter_fig: Any
    reply_timing_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "reply_messages_df": self.reply_messages_df,
            "reply_edges_df": self.reply_edges_df,
            "reply_top_replied_df": self.reply_top_replied_df,
            "reply_thread_summary_df": self.reply_thread_summary_df,
            "reply_distribution_df": self.reply_distribution_df,
            "reply_hourly_reply_rate_df": self.reply_hourly_reply_rate_df,
            "reply_feature_tests_df": self.reply_feature_tests_df,
            "reply_media_contingency_df": self.reply_media_contingency_df,
            "reply_first_reply_timing_df": self.reply_first_reply_timing_df,
            "reply_content_review_df": self.reply_content_review_df,
            "reply_summary_df": self.reply_summary_df,
            "reply_graph": self.reply_graph,
            "reply_distribution_fig": self.reply_distribution_fig,
            "reply_threads_fig": self.reply_threads_fig,
            "reply_scatter_fig": self.reply_scatter_fig,
            "reply_timing_fig": self.reply_timing_fig,
        }


def _preview_text(text: str, *, width: int) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return "(media-only message)"
    return textwrap.shorten(cleaned, width=width, placeholder="...")


def _token_set(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "")}


def _lexical_overlap(left_text: str, right_text: str) -> float:
    left_tokens = _token_set(left_text)
    right_tokens = _token_set(right_text)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _cosine_similarity(
    embedding_lookup: Mapping[tuple[int, int], Sequence[float]] | None,
    *,
    channel_id: int,
    parent_message_id: int,
    reply_message_id: int,
) -> float | None:
    if not embedding_lookup:
        return None

    left = embedding_lookup.get((channel_id, parent_message_id))
    right = embedding_lookup.get((channel_id, reply_message_id))
    if left is None or right is None:
        return None
    if len(left) != len(right) or len(left) == 0:
        return None

    dot_product = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right):
        left_float = float(left_value)
        right_float = float(right_value)
        dot_product += left_float * right_float
        left_norm += left_float * left_float
        right_norm += right_float * right_float

    if left_norm <= 0 or right_norm <= 0:
        return None
    return dot_product / math.sqrt(left_norm * right_norm)


def _time_gap_label(minutes: float | None) -> str:
    if minutes is None or pd.isna(minutes):
        return ""
    minutes_float = float(minutes)
    if minutes_float < 60:
        return f"{minutes_float:.0f}m"
    if minutes_float < 24 * 60:
        return f"{minutes_float / 60:.1f}h"
    return f"{minutes_float / (24 * 60):.1f}d"


def _prepare_reply_messages(messages: Sequence[RawMessage], config: ReplyThreadingConfig) -> pd.DataFrame:
    reply_records: list[dict[str, Any]] = []
    for message in messages:
        timestamp = pd.to_datetime(message.timestamp, utc=True)
        message_text = (preferred_message_text(message) or "").strip()
        reply_records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "hour": timestamp.hour,
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "text": message_text,
                "raw_text": (message.text or "").strip(),
                "english_text": (message.english_text or "").strip(),
                "has_media": bool(message.media_refs),
                "is_media_only": message.is_media_only,
                "reply_to_message_id": int(message.reply_to_message_id) if message.reply_to_message_id is not None else pd.NA,
                "text_length": len(message_text),
                "text_preview": _preview_text(message_text, width=config.preview_chars),
            }
        )

    reply_messages_df = pd.DataFrame(reply_records).sort_values(["timestamp", "message_id"]).reset_index(drop=True)
    if reply_messages_df.empty:
        raise RuntimeError("No messages are available for reply-threading analysis. Run Section 3 first.")

    reply_messages_df["reply_to_message_id"] = reply_messages_df["reply_to_message_id"].astype("Int64")
    return reply_messages_df


def _build_reply_graph(reply_messages_df: pd.DataFrame):
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading analysis requires networkx. "
            "Install notebook extras like: pip install networkx scipy matplotlib numpy"
        ) from exc

    reply_graph = nx.DiGraph()
    for row in reply_messages_df.itertuples(index=False):
        reply_graph.add_node(
            int(row.message_id),
            in_dataset=True,
            timestamp=row.timestamp,
            text=row.text,
            text_preview=row.text_preview,
            has_media=bool(row.has_media),
        )

    reply_only_df = reply_messages_df.loc[
        reply_messages_df["reply_to_message_id"].notna(),
        [
            "channel_id",
            "message_id",
            "timestamp",
            "text",
            "text_preview",
            "has_media",
            "reply_to_message_id",
        ],
    ].copy()
    reply_only_df = reply_only_df.rename(
        columns={
            "message_id": "reply_message_id",
            "timestamp": "reply_timestamp",
            "text": "reply_text",
            "text_preview": "reply_text_preview",
            "has_media": "reply_has_media",
            "reply_to_message_id": "parent_message_id",
        }
    )
    reply_only_df["parent_message_id"] = reply_only_df["parent_message_id"].astype(int)

    for row in reply_only_df.itertuples(index=False):
        parent_message_id = int(row.parent_message_id)
        if not reply_graph.has_node(parent_message_id):
            reply_graph.add_node(
                parent_message_id,
                in_dataset=False,
                timestamp=pd.NaT,
                text="",
                text_preview=f"[outside collection] message {parent_message_id}",
                has_media=False,
            )
        reply_graph.add_edge(int(row.reply_message_id), parent_message_id)

    parent_lookup_df = reply_messages_df[
        ["message_id", "timestamp", "text", "text_preview", "has_media"]
    ].rename(
        columns={
            "message_id": "parent_message_id",
            "timestamp": "parent_timestamp",
            "text": "parent_text",
            "text_preview": "parent_text_preview",
            "has_media": "parent_has_media",
        }
    )

    reply_edges_df = reply_only_df.merge(parent_lookup_df, on="parent_message_id", how="left")
    reply_edges_df["parent_in_dataset"] = reply_edges_df["parent_timestamp"].notna()
    reply_edges_df["time_gap_minutes"] = (
        reply_edges_df["reply_timestamp"] - reply_edges_df["parent_timestamp"]
    ).dt.total_seconds() / 60.0
    reply_edges_df.loc[~reply_edges_df["parent_in_dataset"], "time_gap_minutes"] = pd.NA
    reply_edges_df["time_gap_label"] = [
        _time_gap_label(minutes) for minutes in reply_edges_df["time_gap_minutes"]
    ]
    reply_edges_df = reply_edges_df.sort_values(["reply_timestamp", "reply_message_id"]).reset_index(drop=True)
    return reply_graph, reply_edges_df


def _annotate_threads(reply_messages_df: pd.DataFrame, reply_graph: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    message_ids = set(reply_messages_df["message_id"].astype(int))
    timestamp_lookup = reply_messages_df.set_index("message_id")["timestamp"].to_dict()
    preview_lookup = reply_messages_df.set_index("message_id")["text_preview"].to_dict()
    in_degree_lookup = {int(node): int(value) for node, value in reply_graph.in_degree()}

    parent_lookup = {
        int(node): int(next(reply_graph.successors(node)))
        for node in reply_graph.nodes()
        if reply_graph.out_degree(node) > 0
    }

    depth_cache: dict[int, int] = {}
    root_cache: dict[int, int] = {}

    def full_depth(node: int, *, seen: set[int] | None = None) -> int:
        node = int(node)
        if node in depth_cache:
            return depth_cache[node]
        if seen is None:
            seen = set()
        if node in seen:
            depth_cache[node] = 0
            return 0
        parent = parent_lookup.get(node)
        if parent is None:
            depth = 0
        else:
            depth = 1 + full_depth(parent, seen=seen | {node})
        depth_cache[node] = depth
        return depth

    def root_of(node: int, *, seen: set[int] | None = None) -> int:
        node = int(node)
        if node in root_cache:
            return root_cache[node]
        if seen is None:
            seen = set()
        if node in seen:
            root_cache[node] = node
            return node
        parent = parent_lookup.get(node)
        if parent is None:
            root_cache[node] = node
            return node
        root_node = root_of(parent, seen=seen | {node})
        root_cache[node] = root_node
        return root_node

    component_rows: list[dict[str, Any]] = []
    message_component_rows: list[dict[str, Any]] = []

    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading analysis requires networkx. "
            "Install notebook extras like: pip install networkx scipy matplotlib numpy"
        ) from exc

    for component_index, component_nodes in enumerate(nx.weakly_connected_components(reply_graph), start=1):
        component_node_set = {int(node) for node in component_nodes}
        dataset_nodes = sorted(
            [node for node in component_node_set if node in message_ids],
            key=lambda node: (timestamp_lookup.get(node, _DEFAULT_MAX_TIMESTAMP), node),
        )
        if not dataset_nodes:
            continue

        root_candidates = sorted(
            {root_of(node) for node in dataset_nodes},
            key=lambda node: (timestamp_lookup.get(node, _DEFAULT_MAX_TIMESTAMP), node),
        )
        root_message_id = int(root_candidates[0]) if root_candidates else int(dataset_nodes[0])
        root_depth = full_depth(root_message_id)
        message_depth_lookup = {
            int(node): max(0, full_depth(node) - root_depth)
            for node in dataset_nodes
        }
        thread_depth = max(message_depth_lookup.values()) if message_depth_lookup else 0

        top_replied_message_id = max(
            dataset_nodes,
            key=lambda node: (in_degree_lookup.get(int(node), 0), -int(node)),
        )
        root_in_dataset = root_message_id in message_ids
        root_preview = (
            preview_lookup.get(root_message_id, "")
            if root_in_dataset
            else f"[outside collection] message {root_message_id}"
        )

        component_rows.append(
            {
                "component_index": component_index,
                "thread_size": int(len(dataset_nodes)),
                "thread_depth": int(thread_depth),
                "component_total_nodes": int(len(component_node_set)),
                "external_node_count": int(len(component_node_set) - len(dataset_nodes)),
                "reply_messages": int(sum(node in parent_lookup for node in dataset_nodes)),
                "messages_receiving_replies": int(sum(in_degree_lookup.get(node, 0) > 0 for node in dataset_nodes)),
                "root_message_id": int(root_message_id),
                "root_in_dataset": bool(root_in_dataset),
                "root_preview": root_preview,
                "first_timestamp": min(timestamp_lookup[node] for node in dataset_nodes),
                "last_timestamp": max(timestamp_lookup[node] for node in dataset_nodes),
                "top_replied_message_id": int(top_replied_message_id),
                "top_replied_count": int(in_degree_lookup.get(int(top_replied_message_id), 0)),
                "is_isolated": int(len(dataset_nodes)) == 1 and int(len(component_node_set)) == 1,
                "component_nodes": tuple(sorted(component_node_set)),
                "dataset_message_ids": tuple(dataset_nodes),
            }
        )

        for node in dataset_nodes:
            message_component_rows.append(
                {
                    "message_id": int(node),
                    "component_index": component_index,
                    "message_depth": int(message_depth_lookup.get(int(node), 0)),
                }
            )

    reply_thread_summary_df = pd.DataFrame(component_rows)
    if reply_thread_summary_df.empty:
        reply_messages_df = reply_messages_df.copy()
        reply_messages_df["message_depth"] = 0
        reply_messages_df["thread_label"] = "T00"
        reply_messages_df["thread_rank"] = 0
        reply_messages_df["thread_size"] = 1
        reply_messages_df["thread_depth"] = 0
        reply_messages_df["thread_root_message_id"] = reply_messages_df["message_id"]
        reply_messages_df["thread_root_in_dataset"] = True
        reply_messages_df["thread_root_preview"] = reply_messages_df["text_preview"]
        return reply_messages_df, reply_thread_summary_df

    reply_thread_summary_df = reply_thread_summary_df.sort_values(
        ["thread_size", "thread_depth", "reply_messages", "messages_receiving_replies", "first_timestamp"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    reply_thread_summary_df["thread_rank"] = range(1, len(reply_thread_summary_df) + 1)
    reply_thread_summary_df["thread_label"] = [f"T{rank:03d}" for rank in reply_thread_summary_df["thread_rank"]]

    message_component_df = pd.DataFrame(message_component_rows).merge(
        reply_thread_summary_df[
            [
                "component_index",
                "thread_rank",
                "thread_label",
                "thread_size",
                "thread_depth",
                "root_message_id",
                "root_in_dataset",
                "root_preview",
                "external_node_count",
            ]
        ],
        on="component_index",
        how="left",
    )
    message_component_df = message_component_df.rename(
        columns={
            "root_message_id": "thread_root_message_id",
            "root_in_dataset": "thread_root_in_dataset",
            "root_preview": "thread_root_preview",
        }
    )

    reply_messages_df = reply_messages_df.merge(message_component_df, on="message_id", how="left")
    return reply_messages_df, reply_thread_summary_df


def _reply_bucket_label(reply_count: int, *, overflow_bucket: int) -> str:
    return f"{overflow_bucket}+" if int(reply_count) >= overflow_bucket else str(int(reply_count))


def _build_distribution(reply_messages_df: pd.DataFrame, config: ReplyThreadingConfig) -> pd.DataFrame:
    distribution_df = reply_messages_df.copy()
    distribution_df["reply_bucket_sort"] = distribution_df["reply_count"].clip(upper=config.distribution_overflow_bucket)
    distribution_df["reply_bucket"] = [
        _reply_bucket_label(reply_count, overflow_bucket=config.distribution_overflow_bucket)
        for reply_count in distribution_df["reply_count"]
    ]
    distribution_summary_df = (
        distribution_df.groupby(["reply_bucket_sort", "reply_bucket"], as_index=False)
        .agg(message_count=("message_id", "size"))
        .sort_values("reply_bucket_sort")
        .reset_index(drop=True)
    )
    distribution_summary_df["message_share_pct"] = (
        100 * distribution_summary_df["message_count"] / max(1, len(reply_messages_df))
    ).round(1)
    return distribution_summary_df


def _merge_sentiment_metadata(
    reply_messages_df: pd.DataFrame,
    sentiment_emotion_df: pd.DataFrame | None,
) -> pd.DataFrame:
    merged_df = reply_messages_df.copy()
    merged_df["sentiment_score"] = pd.NA
    merged_df["dominant_sentiment"] = pd.NA
    merged_df["dominant_emotion"] = pd.NA

    if sentiment_emotion_df is None or sentiment_emotion_df.empty:
        return merged_df
    required_columns = {"channel_id", "message_id", "sentiment_score"}
    if not required_columns.issubset(sentiment_emotion_df.columns):
        return merged_df

    available_columns = [
        column
        for column in ["channel_id", "message_id", "sentiment_score", "dominant_sentiment", "dominant_emotion"]
        if column in sentiment_emotion_df.columns
    ]
    return merged_df.drop(columns=["sentiment_score", "dominant_sentiment", "dominant_emotion"]).merge(
        sentiment_emotion_df[available_columns].drop_duplicates(subset=["channel_id", "message_id"]),
        on=["channel_id", "message_id"],
        how="left",
    )


def _build_feature_tables(reply_messages_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    try:
        from scipy.stats import chi2_contingency, mannwhitneyu
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading analysis requires scipy. "
            "Install notebook extras like: pip install scipy networkx matplotlib numpy"
        ) from exc

    replied_df = reply_messages_df.loc[reply_messages_df["reply_count"] > 0].copy()
    unreplied_df = reply_messages_df.loc[reply_messages_df["reply_count"] == 0].copy()

    feature_rows: list[dict[str, Any]] = []
    if not replied_df.empty and not unreplied_df.empty:
        statistic, p_value = mannwhitneyu(
            replied_df["text_length"],
            unreplied_df["text_length"],
            alternative="two-sided",
        )
        feature_rows.append(
            {
                "feature": "text_length",
                "test": "Mann-Whitney U",
                "statistic": float(statistic),
                "p_value": float(p_value),
                "group_a": "messages receiving replies",
                "group_a_n": int(len(replied_df)),
                "group_a_median": float(replied_df["text_length"].median()),
                "group_b": "messages receiving no replies",
                "group_b_n": int(len(unreplied_df)),
                "group_b_median": float(unreplied_df["text_length"].median()),
                "note": "Compares text-length distributions between replied-to and unreplied messages.",
            }
        )
    else:
        feature_rows.append(
            {
                "feature": "text_length",
                "test": "Mann-Whitney U",
                "statistic": pd.NA,
                "p_value": pd.NA,
                "group_a": "messages receiving replies",
                "group_a_n": int(len(replied_df)),
                "group_a_median": float(replied_df["text_length"].median()) if not replied_df.empty else pd.NA,
                "group_b": "messages receiving no replies",
                "group_b_n": int(len(unreplied_df)),
                "group_b_median": float(unreplied_df["text_length"].median()) if not unreplied_df.empty else pd.NA,
                "note": "At least one comparison group is empty, so the test was skipped.",
            }
        )

    reply_media_contingency_df = pd.crosstab(
        reply_messages_df["has_media"].map({False: "no_media", True: "has_media"}),
        reply_messages_df["reply_received"].map({0: "no_reply", 1: "received_reply"}),
    ).reindex(index=["no_media", "has_media"], columns=["no_reply", "received_reply"], fill_value=0)
    reply_media_contingency_df.index.name = "media_presence"

    if reply_media_contingency_df.to_numpy().sum() > 0:
        media_reply_rates = (
            reply_messages_df.groupby("has_media")["reply_received"].mean().mul(100).to_dict()
        )
        try:
            chi2, chi2_p_value, _, _ = chi2_contingency(reply_media_contingency_df)
            chi2_statistic: float | Any = float(chi2)
            chi2_probability: float | Any = float(chi2_p_value)
            chi2_note = "group_*_median columns store reply rates (%) for the media contingency test."
        except ValueError:
            chi2_statistic = pd.NA
            chi2_probability = pd.NA
            chi2_note = (
                "Chi-square test was skipped because the contingency table contains a zero expected frequency; "
                "group_*_median columns store reply rates (%)."
            )

        feature_rows.append(
            {
                "feature": "has_media × reply_received",
                "test": "Chi-square",
                "statistic": chi2_statistic,
                "p_value": chi2_probability,
                "group_a": "has_media",
                "group_a_n": int(reply_messages_df["has_media"].sum()),
                "group_a_median": round(float(media_reply_rates.get(True, 0.0)), 2),
                "group_b": "no_media",
                "group_b_n": int((~reply_messages_df["has_media"]).sum()),
                "group_b_median": round(float(media_reply_rates.get(False, 0.0)), 2),
                "note": chi2_note,
            }
        )

    reply_feature_tests_df = pd.DataFrame(feature_rows)

    reply_hourly_reply_rate_df = (
        reply_messages_df.groupby("hour", as_index=False)
        .agg(
            message_count=("message_id", "size"),
            replied_message_count=("reply_received", "sum"),
            mean_reply_count=("reply_count", "mean"),
        )
        .sort_values("hour")
        .reset_index(drop=True)
    )
    reply_hourly_reply_rate_df["reply_rate_pct"] = (
        100
        * reply_hourly_reply_rate_df["replied_message_count"]
        / reply_hourly_reply_rate_df["message_count"].replace(0, pd.NA)
    ).fillna(0.0).round(1)
    reply_hourly_reply_rate_df["mean_reply_count"] = reply_hourly_reply_rate_df["mean_reply_count"].round(3)
    return reply_feature_tests_df, reply_media_contingency_df, reply_hourly_reply_rate_df


def _build_first_reply_timing(reply_edges_df: pd.DataFrame) -> pd.DataFrame:
    valid_timing_df = reply_edges_df.loc[reply_edges_df["parent_in_dataset"]].copy()
    if valid_timing_df.empty:
        return pd.DataFrame(
            columns=[
                "thread_label",
                "parent_message_id",
                "parent_timestamp",
                "parent_reply_count",
                "parent_text_preview",
                "first_reply_message_id",
                "first_reply_timestamp",
                "first_reply_minutes",
                "first_reply_gap_label",
            ]
        )

    first_reply_timing_df = (
        valid_timing_df.sort_values(["parent_message_id", "time_gap_minutes", "reply_timestamp", "reply_message_id"])
        .drop_duplicates("parent_message_id")
        .rename(
            columns={
                "parent_thread_label": "thread_label",
                "reply_message_id": "first_reply_message_id",
                "reply_timestamp": "first_reply_timestamp",
                "time_gap_minutes": "first_reply_minutes",
                "time_gap_label": "first_reply_gap_label",
            }
        )
    )
    first_reply_timing_df = first_reply_timing_df[
        [
            "thread_label",
            "parent_message_id",
            "parent_timestamp",
            "parent_reply_count",
            "parent_text_preview",
            "first_reply_message_id",
            "first_reply_timestamp",
            "first_reply_minutes",
            "first_reply_gap_label",
        ]
    ].reset_index(drop=True)
    return first_reply_timing_df


def _relationship_hint(
    *,
    parent_text: str,
    parent_has_media: bool,
    reply_text: str,
    reply_has_media: bool,
    cosine_similarity: float | None,
    lexical_overlap: float,
    config: ReplyThreadingConfig,
) -> str:
    reply_text_lower = (reply_text or "").lower()
    if any(keyword.lower() in reply_text_lower for keyword in config.correction_keywords):
        return "correction / clarification"
    if reply_has_media and not parent_has_media:
        return "media supplement"

    similarity_score = cosine_similarity if cosine_similarity is not None else lexical_overlap
    if similarity_score >= config.similarity_update_threshold:
        return "update / continuation"
    if similarity_score <= config.similarity_related_threshold:
        return "related story"
    if lexical_overlap > 0:
        return "update / continuation"
    return "related story"


def _build_content_review(
    reply_top_replied_df: pd.DataFrame,
    reply_edges_df: pd.DataFrame,
    embedding_lookup: Mapping[tuple[int, int], Sequence[float]] | None,
    config: ReplyThreadingConfig,
) -> pd.DataFrame:
    if reply_top_replied_df.empty or reply_edges_df.empty:
        return pd.DataFrame(
            columns=[
                "parent_rank",
                "thread_label",
                "parent_message_id",
                "parent_reply_count",
                "parent_timestamp",
                "parent_text_preview",
                "reply_order",
                "reply_message_id",
                "reply_timestamp",
                "reply_text_preview",
                "time_gap_minutes",
                "time_gap_label",
                "embedding_cosine_similarity",
                "lexical_overlap",
                "relationship_hint",
            ]
        )

    top_parent_lookup = {
        int(row.message_id): {
            "parent_rank": rank,
            "thread_label": row.thread_label,
            "parent_reply_count": int(row.reply_count),
        }
        for rank, row in enumerate(
            reply_top_replied_df.head(config.content_review_parents).itertuples(index=False),
            start=1,
        )
    }

    content_rows: list[dict[str, Any]] = []
    for parent_message_id, parent_meta in top_parent_lookup.items():
        parent_edges_df = reply_edges_df.loc[
            reply_edges_df["parent_message_id"] == parent_message_id
        ].sort_values(["reply_timestamp", "reply_message_id"])
        if parent_edges_df.empty:
            continue

        for reply_order, row in enumerate(parent_edges_df.itertuples(index=False), start=1):
            embedding_cosine_similarity = _cosine_similarity(
                embedding_lookup,
                channel_id=int(row.channel_id),
                parent_message_id=parent_message_id,
                reply_message_id=int(row.reply_message_id),
            )
            lexical_overlap = _lexical_overlap(str(row.parent_text or ""), str(row.reply_text or ""))
            content_rows.append(
                {
                    "parent_rank": int(parent_meta["parent_rank"]),
                    "thread_label": str(parent_meta["thread_label"]),
                    "parent_message_id": int(parent_message_id),
                    "parent_reply_count": int(parent_meta["parent_reply_count"]),
                    "parent_timestamp": row.parent_timestamp,
                    "parent_text_preview": row.parent_text_preview,
                    "reply_order": int(reply_order),
                    "reply_message_id": int(row.reply_message_id),
                    "reply_timestamp": row.reply_timestamp,
                    "reply_text_preview": row.reply_text_preview,
                    "time_gap_minutes": float(row.time_gap_minutes) if not pd.isna(row.time_gap_minutes) else pd.NA,
                    "time_gap_label": row.time_gap_label,
                    "embedding_cosine_similarity": (
                        round(float(embedding_cosine_similarity), 3)
                        if embedding_cosine_similarity is not None
                        else pd.NA
                    ),
                    "lexical_overlap": round(float(lexical_overlap), 3),
                    "relationship_hint": _relationship_hint(
                        parent_text=str(row.parent_text or ""),
                        parent_has_media=bool(row.parent_has_media),
                        reply_text=str(row.reply_text or ""),
                        reply_has_media=bool(row.reply_has_media),
                        cosine_similarity=embedding_cosine_similarity,
                        lexical_overlap=lexical_overlap,
                        config=config,
                    ),
                }
            )

    if not content_rows:
        return pd.DataFrame(
            columns=[
                "parent_rank",
                "thread_label",
                "parent_message_id",
                "parent_reply_count",
                "parent_timestamp",
                "parent_text_preview",
                "reply_order",
                "reply_message_id",
                "reply_timestamp",
                "reply_text_preview",
                "time_gap_minutes",
                "time_gap_label",
                "embedding_cosine_similarity",
                "lexical_overlap",
                "relationship_hint",
            ]
        )

    return pd.DataFrame(content_rows).sort_values(
        ["parent_rank", "reply_order", "reply_timestamp", "reply_message_id"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)


def _empty_figure(*, title: str, message: str):
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib networkx scipy numpy"
        ) from exc

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis("off")
    ax.set_title(title)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11)
    fig.tight_layout()
    return fig


def _build_distribution_figure(
    reply_distribution_df: pd.DataFrame,
    reply_top_replied_df: pd.DataFrame,
    *,
    channel_label: str,
) -> Any:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib networkx scipy numpy"
        ) from exc

    footer_rows = min(3, len(reply_top_replied_df))
    bottom_margin = 0.24 + 0.06 * footer_rows
    fig, ax = plt.subplots(figsize=(12, 5.8))
    fig.subplots_adjust(bottom=bottom_margin)

    bars = ax.bar(
        reply_distribution_df["reply_bucket"],
        reply_distribution_df["message_count"],
        color=["#d9d9d9", "#a6bddb", "#74a9cf", "#2b8cbe"][: len(reply_distribution_df)],
        edgecolor="#4d4d4d",
        linewidth=0.8,
    )
    for bar, value in zip(bars, reply_distribution_df["message_count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(1, reply_distribution_df["message_count"].max() * 0.01),
            str(int(value)),
            ha="center",
            va="bottom",
            fontsize=10,
        )

    ax.set_title(f"{channel_label} Telegram - Reply Count Distribution")
    ax.set_xlabel("Replies received")
    ax.set_ylabel("Messages")
    ax.grid(axis="y", alpha=0.2)
    ax.set_ylim(0, max(1, float(reply_distribution_df["message_count"].max()) * 1.18))

    for footnote_index, row in enumerate(reply_top_replied_df.head(3).itertuples(index=False), start=1):
        fig.text(
            0.01,
            0.03 + 0.055 * (footer_rows - footnote_index),
            f"Top {footnote_index}: #{int(row.message_id)} · replies={int(row.reply_count)} · {row.text_preview}",
            ha="left",
            va="bottom",
            fontsize=9,
            color="#222222",
        )

    return fig


def _tree_positions(tree_graph: Any, roots: list[int], timestamp_lookup: Mapping[int, Any]) -> dict[int, tuple[float, float]]:
    positions: dict[int, tuple[float, float]] = {}
    next_x = [0.0]

    def children_sorted(node: int) -> list[int]:
        return sorted(
            [int(child) for child in tree_graph.successors(node)],
            key=lambda child: (timestamp_lookup.get(child, _DEFAULT_MAX_TIMESTAMP), child),
        )

    def assign(node: int, depth: int) -> float:
        children = children_sorted(node)
        if not children:
            x_position = next_x[0]
            next_x[0] += 1.0
        else:
            child_positions = [assign(child, depth + 1) for child in children]
            x_position = sum(child_positions) / len(child_positions)
        positions[int(node)] = (x_position, -float(depth))
        return x_position

    for root in roots:
        assign(int(root), 0)
        next_x[0] += 1.0
    return positions


def _build_threads_figure(
    reply_graph: Any,
    reply_thread_summary_df: pd.DataFrame,
    reply_messages_df: pd.DataFrame,
    reply_edges_df: pd.DataFrame,
    *,
    channel_label: str,
    config: ReplyThreadingConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib networkx scipy numpy"
        ) from exc

    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading analysis requires networkx. "
            "Install notebook extras like: pip install networkx scipy matplotlib numpy"
        ) from exc

    threaded_components_df = reply_thread_summary_df.loc[
        (reply_thread_summary_df["component_total_nodes"] > 1)
        | (reply_thread_summary_df["reply_messages"] > 0)
        | (reply_thread_summary_df["messages_receiving_replies"] > 0)
    ].head(config.top_threads)
    if threaded_components_df.empty:
        return _empty_figure(
            title=f"{channel_label} Telegram - Top Reply Threads",
            message="No threaded reply components were found beyond isolated single messages.",
        )

    message_lookup = reply_messages_df.set_index("message_id").to_dict("index")
    edge_gap_lookup = reply_edges_df.set_index("reply_message_id")["time_gap_label"].to_dict()
    timestamp_lookup = {
        int(message_id): record["timestamp"] for message_id, record in message_lookup.items()
    }

    rows, cols = subplot_grid(len(threaded_components_df), max_cols=2)
    fig, axes = plt.subplots(rows, cols, figsize=(18, max(6.5, rows * 5.8)), constrained_layout=True)
    axes_list = list(getattr(axes, "flatten", lambda: [axes])()) if hasattr(axes, "flatten") else [axes]

    for ax, row in zip(axes_list, threaded_components_df.itertuples(index=False)):
        component_graph = reply_graph.subgraph(list(row.component_nodes)).copy()
        tree_graph = nx.DiGraph()
        tree_graph.add_nodes_from(component_graph.nodes())
        tree_graph.add_edges_from((parent, reply) for reply, parent in component_graph.edges())

        roots = sorted(
            [int(node) for node in tree_graph.nodes() if tree_graph.in_degree(node) == 0],
            key=lambda node: (timestamp_lookup.get(node, _DEFAULT_MAX_TIMESTAMP), node),
        )
        if not roots:
            roots = sorted(tree_graph.nodes())

        positions = _tree_positions(tree_graph, roots, timestamp_lookup)
        node_sizes = []
        node_colors = []
        node_edge_colors = []
        labels: dict[int, str] = {}
        for node in tree_graph.nodes():
            node_int = int(node)
            record = message_lookup.get(node_int)
            if record is None:
                node_sizes.append(900)
                node_colors.append(DEFAULT_EXTERNAL_NODE_COLOR)
                node_edge_colors.append("#333333")
                labels[node_int] = textwrap.fill(f"outside window\n#{node_int}", width=15)
                continue

            node_sizes.append(1050 if record["has_media"] else 950)
            node_colors.append(DEFAULT_MEDIA_COLOR if record["has_media"] else DEFAULT_TEXT_ONLY_COLOR)
            node_edge_colors.append("#333333")
            labels[node_int] = textwrap.fill(
                _preview_text(str(record["text"] or ""), width=config.tree_label_chars),
                width=18,
            )

        nx.draw_networkx_edges(tree_graph, positions, ax=ax, arrows=True, arrowstyle="-|>", arrowsize=14, width=1.5, edge_color="#777777")
        nx.draw_networkx_nodes(
            tree_graph,
            positions,
            ax=ax,
            node_size=node_sizes,
            node_color=node_colors,
            edgecolors=node_edge_colors,
            linewidths=1.2,
        )
        nx.draw_networkx_labels(tree_graph, positions, labels=labels, font_size=8.5, ax=ax)

        edge_labels = {
            (parent, reply): edge_gap_lookup.get(int(reply), "")
            for parent, reply in tree_graph.edges()
            if edge_gap_lookup.get(int(reply), "")
        }
        if edge_labels:
            nx.draw_networkx_edge_labels(tree_graph, positions, edge_labels=edge_labels, font_size=8, rotate=False, ax=ax)

        ax.set_title(
            f"{row.thread_label} · size={int(row.thread_size)} · depth={int(row.thread_depth)}",
            fontsize=12,
        )
        ax.axis("off")

    for extra_ax in axes_list[len(threaded_components_df) :]:
        extra_ax.set_visible(False)

    fig.suptitle(f"{channel_label} Telegram - Top Reply Thread Trees", fontsize=15, y=1.02)
    fig.legend(
        handles=[
            Patch(facecolor=DEFAULT_MEDIA_COLOR, edgecolor="#333333", label="Message with media"),
            Patch(facecolor=DEFAULT_TEXT_ONLY_COLOR, edgecolor="#333333", label="Text-only / media-only message"),
            Patch(facecolor=DEFAULT_EXTERNAL_NODE_COLOR, edgecolor="#333333", label="Parent outside collection"),
        ],
        loc="upper center",
        ncol=3,
        frameon=True,
    )
    return fig


def _build_scatter_figure(
    reply_messages_df: pd.DataFrame,
    *,
    channel_label: str,
    config: ReplyThreadingConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib networkx scipy numpy"
        ) from exc

    fig, ax = plt.subplots(figsize=(12.5, 6.2))
    scatter_df = reply_messages_df.copy()
    scatter_df["sentiment_score_numeric"] = pd.to_numeric(scatter_df["sentiment_score"], errors="coerce")

    if scatter_df["sentiment_score_numeric"].notna().any():
        scatter = ax.scatter(
            scatter_df["text_length"],
            scatter_df["reply_count"],
            c=scatter_df["sentiment_score_numeric"].fillna(0.0),
            cmap="coolwarm",
            vmin=-1,
            vmax=1,
            s=46,
            alpha=0.75,
            edgecolors="white",
            linewidths=0.45,
        )
        colorbar = fig.colorbar(scatter, ax=ax)
        colorbar.set_label("Sentiment score")
    else:
        media_mask = scatter_df["has_media"].fillna(False)
        ax.scatter(
            scatter_df.loc[~media_mask, "text_length"],
            scatter_df.loc[~media_mask, "reply_count"],
            color=DEFAULT_TEXT_ONLY_COLOR,
            label="No media",
            s=42,
            alpha=0.72,
            edgecolors="white",
            linewidths=0.45,
        )
        ax.scatter(
            scatter_df.loc[media_mask, "text_length"],
            scatter_df.loc[media_mask, "reply_count"],
            color=DEFAULT_MEDIA_COLOR,
            label="Has media",
            s=52,
            alpha=0.78,
            edgecolors="white",
            linewidths=0.45,
        )
        ax.legend(frameon=True)

    outlier_candidates_df = pd.concat(
        [
            scatter_df.sort_values(["reply_count", "text_length"], ascending=[False, False]).head(config.outlier_annotations),
            scatter_df.loc[scatter_df["reply_count"] > 0]
            .sort_values(["text_length", "reply_count"], ascending=[False, False])
            .head(config.outlier_annotations),
        ],
        ignore_index=True,
    ).drop_duplicates(subset=["message_id"])
    outlier_candidates_df = outlier_candidates_df.head(config.outlier_annotations)

    for row in outlier_candidates_df.itertuples(index=False):
        ax.annotate(
            f"#{int(row.message_id)}\n{_preview_text(str(row.text or ''), width=42)}",
            xy=(float(row.text_length), float(row.reply_count)),
            xytext=(8, 8),
            textcoords="offset points",
            fontsize=8,
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.82},
        )

    ax.set_title(f"{channel_label} Telegram - Text Length vs Replies Received")
    ax.set_xlabel("Text length (characters)")
    ax.set_ylabel("Replies received")
    ax.grid(alpha=0.22)
    fig.tight_layout()
    return fig


def _build_timing_figure(
    reply_first_reply_timing_df: pd.DataFrame,
    *,
    channel_label: str,
    config: ReplyThreadingConfig,
) -> Any:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Reply-threading plotting requires matplotlib. "
            "Install notebook extras like: pip install matplotlib networkx scipy numpy"
        ) from exc

    if reply_first_reply_timing_df.empty:
        return _empty_figure(
            title=f"{channel_label} Telegram - Time to First Reply",
            message="No parent/reply pairs with timestamps were available for timing analysis.",
        )

    first_reply_minutes = reply_first_reply_timing_df["first_reply_minutes"].astype(float)
    median_gap = float(first_reply_minutes.median())

    fig, ax = plt.subplots(figsize=(12, 5.2))
    ax.hist(
        first_reply_minutes,
        bins=min(config.first_reply_hist_bins, max(6, int(math.sqrt(len(first_reply_minutes))) + 2)),
        color="#6baed6",
        edgecolor="white",
        alpha=0.9,
    )
    ax.axvline(median_gap, color="#d62728", linestyle="--", linewidth=2, label=f"Median = {median_gap:.1f} min")
    ax.set_title(f"{channel_label} Telegram - Parent → First Reply Timing")
    ax.set_xlabel("Minutes until first reply")
    ax.set_ylabel("Parent messages")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=True)
    fig.tight_layout()
    return fig


def run_reply_threading_analysis(
    messages: Sequence[RawMessage],
    *,
    channel_label: str,
    sentiment_emotion_df: pd.DataFrame | None = None,
    embedding_lookup: Mapping[tuple[int, int], Sequence[float]] | None = None,
    config: ReplyThreadingConfig | None = None,
) -> ReplyThreadingResult:
    config = config or ReplyThreadingConfig()
    started_at = time.monotonic()

    reply_messages_df = _prepare_reply_messages(messages, config)
    reply_graph, reply_edges_df = _build_reply_graph(reply_messages_df)
    reply_messages_df, reply_thread_summary_df = _annotate_threads(reply_messages_df, reply_graph)

    in_degree_lookup = {int(node): int(value) for node, value in reply_graph.in_degree()}
    time_to_parent_lookup = reply_edges_df.set_index("reply_message_id")["time_gap_minutes"].to_dict() if not reply_edges_df.empty else {}

    reply_messages_df = reply_messages_df.copy()
    reply_messages_df["reply_count"] = reply_messages_df["message_id"].map(lambda message_id: int(in_degree_lookup.get(int(message_id), 0)))
    reply_messages_df["reply_received"] = (reply_messages_df["reply_count"] > 0).astype(int)
    reply_messages_df["is_reply"] = reply_messages_df["reply_to_message_id"].notna()
    reply_messages_df["parent_in_dataset"] = reply_messages_df["reply_to_message_id"].isin(reply_messages_df["message_id"])
    reply_messages_df["time_to_parent_minutes"] = reply_messages_df["message_id"].map(time_to_parent_lookup)
    reply_messages_df = _merge_sentiment_metadata(reply_messages_df, sentiment_emotion_df)

    reply_messages_df["reply_bucket"] = [
        _reply_bucket_label(reply_count, overflow_bucket=config.distribution_overflow_bucket)
        for reply_count in reply_messages_df["reply_count"]
    ]

    reply_top_replied_df = (
        reply_messages_df.loc[reply_messages_df["reply_count"] > 0]
        .sort_values(
            ["reply_count", "timestamp", "message_id"],
            ascending=[False, True, True],
        )
        .head(config.top_replied_messages)
        .reset_index(drop=True)
    )

    parent_metrics_df = reply_messages_df[["message_id", "reply_count", "thread_label"]].rename(
        columns={
            "message_id": "parent_message_id",
            "reply_count": "parent_reply_count",
            "thread_label": "parent_thread_label",
        }
    )
    reply_edges_df = reply_edges_df.merge(parent_metrics_df, on="parent_message_id", how="left")

    reply_distribution_df = _build_distribution(reply_messages_df, config)
    reply_feature_tests_df, reply_media_contingency_df, reply_hourly_reply_rate_df = _build_feature_tables(reply_messages_df)
    reply_first_reply_timing_df = _build_first_reply_timing(reply_edges_df)
    reply_content_review_df = _build_content_review(reply_top_replied_df, reply_edges_df, embedding_lookup, config)

    largest_thread_size = int(reply_thread_summary_df["thread_size"].max()) if not reply_thread_summary_df.empty else 0
    deepest_thread_depth = int(reply_thread_summary_df["thread_depth"].max()) if not reply_thread_summary_df.empty else 0
    median_first_reply_minutes = (
        round(float(reply_first_reply_timing_df["first_reply_minutes"].median()), 2)
        if not reply_first_reply_timing_df.empty
        else pd.NA
    )
    reply_summary_df = pd.DataFrame(
        [
            {
                "messages_analyzed": int(len(reply_messages_df)),
                "reply_edges_total": int(len(reply_edges_df)),
                "reply_edges_with_parent_in_dataset": int(reply_edges_df["parent_in_dataset"].sum()) if not reply_edges_df.empty else 0,
                "messages_that_are_replies": int(reply_messages_df["is_reply"].sum()),
                "messages_receiving_replies": int(reply_messages_df["reply_received"].sum()),
                "messages_receiving_replies_pct": round(float(reply_messages_df["reply_received"].mean() * 100), 1),
                "messages_replying_to_missing_parent": int((reply_messages_df["is_reply"] & ~reply_messages_df["parent_in_dataset"]).sum()),
                "largest_thread_size": largest_thread_size,
                "deepest_thread_depth": deepest_thread_depth,
                "max_reply_count": int(reply_messages_df["reply_count"].max()),
                "median_first_reply_minutes": median_first_reply_minutes,
            }
        ]
    )

    reply_distribution_fig = _build_distribution_figure(
        reply_distribution_df,
        reply_top_replied_df,
        channel_label=channel_label,
    )
    reply_threads_fig = _build_threads_figure(
        reply_graph,
        reply_thread_summary_df,
        reply_messages_df,
        reply_edges_df,
        channel_label=channel_label,
        config=config,
    )
    reply_scatter_fig = _build_scatter_figure(
        reply_messages_df,
        channel_label=channel_label,
        config=config,
    )
    reply_timing_fig = _build_timing_figure(
        reply_first_reply_timing_df,
        channel_label=channel_label,
        config=config,
    )

    return ReplyThreadingResult(
        reply_messages_df=reply_messages_df,
        reply_edges_df=reply_edges_df,
        reply_top_replied_df=reply_top_replied_df,
        reply_thread_summary_df=reply_thread_summary_df,
        reply_distribution_df=reply_distribution_df,
        reply_hourly_reply_rate_df=reply_hourly_reply_rate_df,
        reply_feature_tests_df=reply_feature_tests_df,
        reply_media_contingency_df=reply_media_contingency_df,
        reply_first_reply_timing_df=reply_first_reply_timing_df,
        reply_content_review_df=reply_content_review_df,
        reply_summary_df=reply_summary_df,
        reply_graph=reply_graph,
        reply_distribution_fig=reply_distribution_fig,
        reply_threads_fig=reply_threads_fig,
        reply_scatter_fig=reply_scatter_fig,
        reply_timing_fig=reply_timing_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
