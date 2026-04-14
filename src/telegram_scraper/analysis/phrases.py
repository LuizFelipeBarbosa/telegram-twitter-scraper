from __future__ import annotations

import math
import re
import textwrap
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from telegram_scraper.analysis._common import UNKNOWN_LANGUAGE, message_used_translation
from telegram_scraper.notebook_pipeline import RawMessage, preferred_message_text

DEFAULT_PHRASE_EXTRA_STOPWORDS = {
    "says",
    "said",
    "say",
    "according",
    "media",
    "report",
    "reports",
    "reported",
    "breaking",
    "watch",
    "exclusive",
    "footage",
    "video",
    "videos",
    "photo",
    "photos",
    "image",
    "images",
    "news",
    "channel",
    "telegram",
    "presstv",
    "press",
    "today",
    "also",
    "just",
    "via",
}
DEFAULT_STATUS_COLORS = {
    "retained": "#9e9e9e",
    "new": "#2ca02c",
    "dropped": "#d62728",
}
DEFAULT_COMMUNITY_COLORS = [
    "#4c78a8",
    "#f58518",
    "#54a24b",
    "#e45756",
    "#72b7b2",
    "#b279a2",
    "#ff9da6",
    "#9d755d",
    "#bab0ab",
]
FALLBACK_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "them",
    "there",
    "they",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "you",
    "your",
}

_PHRASE_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_PHRASE_MENTION_RE = re.compile(r"@\w+")
_PHRASE_HASHTAG_RE = re.compile(r"#(\w+)")
_PHRASE_TRAILING_DELIMITER_RE = re.compile(r"(?:\s*\n?---\s*)+$")
_PHRASE_NON_ALPHA_RE = re.compile(r"[^a-z\s']")
_PHRASE_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PhraseNetworkConfig:
    min_token_length: int = 3
    text_max_chars: int = 4000
    min_bigram_freq: int = 5
    min_trigram_freq: int = 3
    min_bigram_pmi: float = 3.0
    min_trigram_pmi: float = 3.0
    top_bigrams: int = 30
    top_trigrams: int = 20
    network_edge_limit: int = 40
    temporal_top_k: int = 50
    temporal_network_edge_limit: int = 20
    temporal_min_freq: int = 3
    preserve_tokens: set[str] = field(default_factory=lambda: {"us", "un", "eu", "uk"})
    extra_stopwords: set[str] = field(default_factory=lambda: set(DEFAULT_PHRASE_EXTRA_STOPWORDS))
    status_colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_STATUS_COLORS))
    community_colors: list[str] = field(default_factory=lambda: list(DEFAULT_COMMUNITY_COLORS))
    layout_seed: int = 42


@dataclass(frozen=True)
class PhraseNetworkResult:
    phrase_messages_df: pd.DataFrame
    phrase_bigram_df: pd.DataFrame
    phrase_trigram_df: pd.DataFrame
    phrase_bigram_bar_df: pd.DataFrame
    phrase_network_summary_df: pd.DataFrame
    phrase_network_nodes_df: pd.DataFrame
    phrase_network_edges_df: pd.DataFrame
    phrase_temporal_bigram_df: pd.DataFrame
    phrase_temporal_change_df: pd.DataFrame
    phrase_bigram_graph: Any
    phrase_network_fig: Any
    phrase_bigram_bar_fig: Any
    phrase_temporal_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "phrase_messages_df": self.phrase_messages_df,
            "phrase_bigram_df": self.phrase_bigram_df,
            "phrase_trigram_df": self.phrase_trigram_df,
            "phrase_bigram_bar_df": self.phrase_bigram_bar_df,
            "phrase_network_summary_df": self.phrase_network_summary_df,
            "phrase_network_nodes_df": self.phrase_network_nodes_df,
            "phrase_network_edges_df": self.phrase_network_edges_df,
            "phrase_temporal_bigram_df": self.phrase_temporal_bigram_df,
            "phrase_temporal_change_df": self.phrase_temporal_change_df,
            "phrase_bigram_graph": self.phrase_bigram_graph,
            "phrase_network_fig": self.phrase_network_fig,
            "phrase_bigram_bar_fig": self.phrase_bigram_bar_fig,
            "phrase_temporal_fig": self.phrase_temporal_fig,
        }


def _ensure_stopwords_loaded() -> set[str]:
    try:
        import nltk
        from nltk.corpus import stopwords
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Phrase-network analysis requires nltk. Install notebook extras like: "
            "pip install nltk networkx plotly matplotlib numpy"
        ) from exc

    try:
        return set(stopwords.words("english"))
    except LookupError:
        try:  # pragma: no cover - depends on notebook env state
            nltk.download("stopwords", quiet=True)
        except Exception:
            return set(FALLBACK_STOPWORDS)
        try:
            return set(stopwords.words("english"))
        except LookupError:
            return set(FALLBACK_STOPWORDS)


def _build_stopwords(channel_name: str, config: PhraseNetworkConfig) -> set[str]:
    channel_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z]+", channel_name or "")
        if len(token) >= config.min_token_length
    }
    stop_words = _ensure_stopwords_loaded().union(config.extra_stopwords).union(channel_tokens)
    return stop_words.difference({token.lower() for token in config.preserve_tokens})


def clean_phrase_text(text: str, stop_words: set[str], config: PhraseNetworkConfig) -> tuple[str, list[str]]:
    cleaned = _PHRASE_URL_RE.sub(" ", (text or "")[: config.text_max_chars])
    cleaned = _PHRASE_MENTION_RE.sub(" ", cleaned)
    cleaned = _PHRASE_HASHTAG_RE.sub(r" \1 ", cleaned)
    cleaned = _PHRASE_TRAILING_DELIMITER_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("’", "'").replace("-", " ").replace("/", " ").replace("_", " ")
    cleaned = cleaned.lower()
    cleaned = _PHRASE_NON_ALPHA_RE.sub(" ", cleaned)
    cleaned = _PHRASE_WHITESPACE_RE.sub(" ", cleaned).strip()

    tokens = [token.strip("'") for token in cleaned.split()]
    preserve_tokens = {token.lower() for token in config.preserve_tokens}
    filtered_tokens = [
        token
        for token in tokens
        if token
        and token not in stop_words
        and (len(token) >= config.min_token_length or token in preserve_tokens)
    ]
    return " ".join(filtered_tokens), filtered_tokens


def _prepare_phrase_messages(
    translated_messages: Sequence[RawMessage],
    *,
    stop_words: set[str],
    config: PhraseNetworkConfig,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for message in translated_messages:
        original_text = (preferred_message_text(message) or "").strip()
        clean_text, tokens = clean_phrase_text(original_text, stop_words, config)
        if not tokens:
            continue

        timestamp = pd.to_datetime(message.timestamp, utc=True)
        records.append(
            {
                "channel_id": message.channel_id,
                "message_id": message.message_id,
                "timestamp": timestamp,
                "date": timestamp.floor("D"),
                "source_language": message.source_language or UNKNOWN_LANGUAGE,
                "used_translation": message_used_translation(message),
                "has_media": bool(message.media_refs),
                "text": original_text,
                "clean_text": clean_text,
                "tokens": tokens,
                "token_count": len(tokens),
            }
        )

    phrase_messages_df = pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)
    if phrase_messages_df.empty:
        raise RuntimeError("No text-bearing messages remain for phrase-network analysis after cleaning. Run Sections 3-4 first.")
    return phrase_messages_df


def _iter_ngrams(tokens: Sequence[str], ngram_size: int):
    for index in range(max(0, len(tokens) - ngram_size + 1)):
        yield tuple(tokens[index : index + ngram_size])


def _ngram_occurrence_summary(
    phrase_messages_df: pd.DataFrame,
    *,
    ngram_size: int,
) -> tuple[Counter[tuple[str, ...]], Counter[tuple[str, ...]], dict[tuple[str, ...], pd.Timestamp], dict[tuple[str, ...], pd.Timestamp], dict[tuple[str, ...], dict[str, Any]]]:
    occurrence_counter: Counter[tuple[str, ...]] = Counter()
    message_counter: Counter[tuple[str, ...]] = Counter()
    first_seen: dict[tuple[str, ...], pd.Timestamp] = {}
    last_seen: dict[tuple[str, ...], pd.Timestamp] = {}
    example_lookup: dict[tuple[str, ...], dict[str, Any]] = {}

    for row in phrase_messages_df.itertuples(index=False):
        seen_in_message: set[tuple[str, ...]] = set()
        for ngram in _iter_ngrams(row.tokens, ngram_size):
            occurrence_counter[ngram] += 1
            if ngram not in seen_in_message:
                message_counter[ngram] += 1
                seen_in_message.add(ngram)
            if ngram not in first_seen:
                first_seen[ngram] = row.timestamp
            last_seen[ngram] = row.timestamp
            if ngram not in example_lookup:
                example_lookup[ngram] = {
                    "example_message_id": row.message_id,
                    "example_timestamp": row.timestamp,
                    "example_text": textwrap.shorten(row.text, width=160, placeholder="..."),
                }

    return occurrence_counter, message_counter, first_seen, last_seen, example_lookup


def _documents_for_collocations(phrase_messages_df: pd.DataFrame, *, ngram_size: int) -> list[list[str]]:
    return [tokens for tokens in phrase_messages_df["tokens"].tolist() if len(tokens) >= ngram_size]


def _score_collocations(documents: list[list[str]], *, ngram_size: int, min_freq: int) -> list[tuple[tuple[str, ...], float]]:
    try:
        from nltk.collocations import BigramCollocationFinder, TrigramCollocationFinder
        from nltk.metrics import BigramAssocMeasures, TrigramAssocMeasures
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Phrase-network analysis requires nltk collocations support. Install notebook extras like: "
            "pip install nltk networkx plotly matplotlib numpy"
        ) from exc

    if not documents:
        return []

    if ngram_size == 2:
        finder = BigramCollocationFinder.from_documents(documents)
        finder.apply_freq_filter(min_freq)
        scored = finder.score_ngrams(BigramAssocMeasures.pmi)
    elif ngram_size == 3:
        finder = TrigramCollocationFinder.from_documents(documents)
        finder.apply_freq_filter(min_freq)
        scored = finder.score_ngrams(TrigramAssocMeasures.pmi)
    else:  # pragma: no cover - internal misuse guard
        raise ValueError(f"Unsupported ngram_size={ngram_size}")

    return [(tuple(ngram), float(score)) for ngram, score in scored]


def _empty_ngram_df(*, ngram_size: int, phrase_label: str) -> pd.DataFrame:
    columns = [
        "rank",
        phrase_label,
        *[f"word_{index}" for index in range(1, ngram_size + 1)],
        "pmi",
        "frequency",
        "message_count",
        "contains_entity_term",
        "network_score",
        "first_seen",
        "last_seen",
        "example_message_id",
        "example_timestamp",
        "example_text",
    ]
    return pd.DataFrame(columns=columns)


def _build_ngram_df(
    phrase_messages_df: pd.DataFrame,
    *,
    ngram_size: int,
    min_freq: int,
    min_pmi: float,
    phrase_label: str,
    entity_terms: set[str],
) -> pd.DataFrame:
    documents = _documents_for_collocations(phrase_messages_df, ngram_size=ngram_size)
    if not documents:
        return _empty_ngram_df(ngram_size=ngram_size, phrase_label=phrase_label)

    occurrence_counter, message_counter, first_seen, last_seen, example_lookup = _ngram_occurrence_summary(
        phrase_messages_df,
        ngram_size=ngram_size,
    )
    scored = _score_collocations(documents, ngram_size=ngram_size, min_freq=min_freq)

    rows: list[dict[str, Any]] = []
    for ngram, pmi in scored:
        frequency = int(occurrence_counter.get(ngram, 0))
        if frequency < min_freq or pmi < min_pmi:
            continue

        row = {
            "rank": 0,
            phrase_label: " ".join(ngram),
            "pmi": float(pmi),
            "frequency": frequency,
            "message_count": int(message_counter.get(ngram, 0)),
            "contains_entity_term": any(token in entity_terms for token in ngram),
            "network_score": float(pmi) * frequency,
            "first_seen": first_seen.get(ngram),
            "last_seen": last_seen.get(ngram),
            **example_lookup.get(ngram, {}),
        }
        for index, token in enumerate(ngram, start=1):
            row[f"word_{index}"] = token
        rows.append(row)

    if not rows:
        return _empty_ngram_df(ngram_size=ngram_size, phrase_label=phrase_label)

    ngram_df = pd.DataFrame(rows).sort_values(
        ["pmi", "frequency", "message_count", phrase_label],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    ngram_df["rank"] = range(1, len(ngram_df) + 1)
    return ngram_df


def _scale_values(values: Sequence[float], *, min_out: float, max_out: float) -> list[float]:
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if math.isclose(min_value, max_value):
        midpoint = (min_out + max_out) / 2.0
        return [midpoint for _ in values]
    scale = max_out - min_out
    return [min_out + ((value - min_value) / (max_value - min_value)) * scale for value in values]


def _assign_communities(graph: Any) -> dict[str, int]:
    if graph.number_of_nodes() == 0:
        return {}
    if graph.number_of_nodes() == 1 or graph.number_of_edges() == 0:
        return {next(iter(graph.nodes())): 0}

    import networkx as nx

    undirected_graph = graph.to_undirected()
    communities = list(nx.community.greedy_modularity_communities(undirected_graph, weight="weight"))
    node_to_community: dict[str, int] = {}
    for community_index, nodes in enumerate(communities):
        for node in nodes:
            node_to_community[str(node)] = community_index
    return node_to_community


def _build_phrase_graph(phrase_bigram_df: pd.DataFrame, config: PhraseNetworkConfig):
    import networkx as nx

    graph = nx.DiGraph()
    if phrase_bigram_df.empty:
        return graph

    edge_source_df = phrase_bigram_df.sort_values(
        ["network_score", "frequency", "pmi", "bigram"],
        ascending=[False, False, False, True],
    ).head(config.network_edge_limit)

    for row in edge_source_df.itertuples(index=False):
        graph.add_edge(
            row.word_1,
            row.word_2,
            weight=float(row.frequency),
            pmi=float(row.pmi),
            message_count=int(row.message_count),
            bigram=row.bigram,
            contains_entity_term=bool(row.contains_entity_term),
        )

    community_lookup = _assign_communities(graph)
    for node in graph.nodes():
        in_weight = sum(float(data.get("weight", 0.0)) for _, _, data in graph.in_edges(node, data=True))
        out_weight = sum(float(data.get("weight", 0.0)) for _, _, data in graph.out_edges(node, data=True))
        total_freq = in_weight + out_weight
        community = community_lookup.get(str(node), 0)
        graph.nodes[node]["in_degree"] = int(graph.in_degree(node))
        graph.nodes[node]["out_degree"] = int(graph.out_degree(node))
        graph.nodes[node]["degree"] = int(graph.degree(node))
        graph.nodes[node]["in_weight"] = in_weight
        graph.nodes[node]["out_weight"] = out_weight
        graph.nodes[node]["total_freq"] = total_freq
        graph.nodes[node]["weighted_degree"] = total_freq
        graph.nodes[node]["community"] = community
        graph.nodes[node]["community_color"] = config.community_colors[community % len(config.community_colors)]

    return graph


def _empty_plotly_figure(go: Any, *, title: str, message: str) -> Any:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font={"size": 14})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(title=title, template="plotly_white")
    return fig


def _build_network_dataframes(graph: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_rows = [
        {
            "token": node,
            "degree": data.get("degree", 0),
            "in_degree": data.get("in_degree", 0),
            "out_degree": data.get("out_degree", 0),
            "in_weight": data.get("in_weight", 0.0),
            "out_weight": data.get("out_weight", 0.0),
            "total_freq": data.get("total_freq", 0.0),
            "weighted_degree": data.get("weighted_degree", 0.0),
            "community": data.get("community", 0),
            "community_color": data.get("community_color", "#4c78a8"),
        }
        for node, data in graph.nodes(data=True)
    ]
    edge_rows = [
        {
            "source": source,
            "target": target,
            "bigram": data.get("bigram", f"{source} {target}"),
            "weight": data.get("weight", 0.0),
            "pmi": data.get("pmi", 0.0),
            "message_count": data.get("message_count", 0),
            "contains_entity_term": bool(data.get("contains_entity_term", False)),
        }
        for source, target, data in graph.edges(data=True)
    ]

    phrase_network_nodes_df = pd.DataFrame(node_rows)
    phrase_network_edges_df = pd.DataFrame(edge_rows)
    if not phrase_network_nodes_df.empty:
        phrase_network_nodes_df = phrase_network_nodes_df.sort_values(
            ["total_freq", "degree", "token"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
    if not phrase_network_edges_df.empty:
        phrase_network_edges_df = phrase_network_edges_df.sort_values(
            ["weight", "pmi", "bigram"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
    return phrase_network_nodes_df, phrase_network_edges_df


def _network_positions(graph: Any, *, layout_seed: int) -> dict[str, tuple[float, float]]:
    if graph.number_of_nodes() == 0:
        return {}

    import networkx as nx

    layout_graph = graph.to_undirected()
    return nx.spring_layout(
        layout_graph,
        seed=layout_seed,
        weight="weight",
        k=1.4 / math.sqrt(max(layout_graph.number_of_nodes(), 1)),
    )


def _build_network_figure(graph: Any, *, channel_name: str, config: PhraseNetworkConfig):
    import plotly.graph_objects as go

    title = f"{channel_name} Telegram - Bigram Phrase Network"
    if graph.number_of_nodes() == 0:
        return _empty_plotly_figure(go, title=title, message="No significant bigrams survived the current filters.")

    positions = _network_positions(graph, layout_seed=config.layout_seed)
    node_order = list(graph.nodes())
    node_weights = [float(graph.nodes[node].get("total_freq", 0.0)) for node in node_order]
    node_sizes = _scale_values(node_weights, min_out=18.0, max_out=42.0)

    edge_weights = [float(data.get("weight", 0.0)) for _, _, data in graph.edges(data=True)]
    edge_widths = _scale_values(edge_weights, min_out=1.5, max_out=6.0)
    fig = go.Figure()

    for edge_index, (source, target, data) in enumerate(graph.edges(data=True)):
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        width = edge_widths[edge_index] if edge_index < len(edge_widths) else 2.0
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=width,
            arrowcolor="#8f8f8f",
            opacity=0.55,
        )
        fig.add_trace(
            go.Scatter(
                x=[(x0 + x1) / 2.0],
                y=[(y0 + y1) / 2.0],
                mode="markers",
                marker={"size": max(10.0, width * 2.5), "color": "rgba(0,0,0,0)"},
                hovertemplate=(
                    f"<b>{data.get('bigram', f'{source} {target}')}</b>"
                    f"<br>Frequency: {data.get('weight', 0)}"
                    f"<br>PMI: {float(data.get('pmi', 0.0)):.2f}"
                    f"<br>Messages: {data.get('message_count', 0)}"
                    "<extra></extra>"
                ),
                showlegend=False,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[positions[node][0] for node in node_order],
            y=[positions[node][1] for node in node_order],
            mode="markers+text",
            text=node_order,
            textposition="top center",
            hovertemplate=(
                "<b>%{text}</b>"
                "<br>Total frequency: %{customdata[0]:.0f}"
                "<br>Degree: %{customdata[1]:.0f}"
                "<br>Community: %{customdata[2]:.0f}"
                "<extra></extra>"
            ),
            customdata=[
                [
                    graph.nodes[node].get("total_freq", 0.0),
                    graph.nodes[node].get("degree", 0),
                    graph.nodes[node].get("community", 0),
                ]
                for node in node_order
            ],
            marker={
                "size": node_sizes,
                "color": [graph.nodes[node].get("community_color", "#4c78a8") for node in node_order],
                "line": {"color": "white", "width": 1.2},
                "opacity": 0.92,
            },
            showlegend=False,
        )
    )

    fig.update_layout(
        title=(
            f"{title}<br><sup>Nodes sized by total bigram frequency; arrows weighted by phrase frequency; "
            f"communities inferred with greedy modularity</sup>"
        ),
        template="plotly_white",
        margin={"l": 20, "r": 20, "t": 85, "b": 20},
        xaxis={"visible": False},
        yaxis={"visible": False},
        hovermode="closest",
    )
    return fig


def _build_bigram_bar_figure(phrase_bigram_bar_df: pd.DataFrame, *, channel_name: str):
    import plotly.graph_objects as go

    title = f"{channel_name} Telegram - Top Bigram PMI Scores"
    if phrase_bigram_bar_df.empty:
        return _empty_plotly_figure(go, title=title, message="No significant bigrams survived the current filters.")

    color_map = {True: "#d62728", False: "#4c78a8"}
    entity_labels = phrase_bigram_bar_df["contains_entity_term"].map(
        {True: "Contains entity-linked token", False: "No entity-linked token"}
    )
    fig = go.Figure(
        go.Bar(
            x=phrase_bigram_bar_df["pmi"],
            y=phrase_bigram_bar_df["bigram"],
            orientation="h",
            marker={"color": [color_map[bool(value)] for value in phrase_bigram_bar_df["contains_entity_term"]]},
            text=[f"freq {int(value)}" for value in phrase_bigram_bar_df["frequency"]],
            textposition="outside",
            customdata=list(zip(phrase_bigram_bar_df["frequency"], entity_labels)),
            hovertemplate=(
                "<b>%{y}</b>"
                "<br>PMI: %{x:.2f}"
                "<br>Frequency: %{customdata[0]}"
                "<br>%{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=title,
        template="plotly_white",
        xaxis_title="PMI",
        yaxis_title="Bigram",
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
        height=max(450, 18 * len(phrase_bigram_bar_df) + 180),
    )
    return fig


def _format_half_window(half_df: pd.DataFrame, label: str) -> str:
    if half_df.empty:
        return label
    start = pd.Timestamp(half_df["timestamp"].min())
    end = pd.Timestamp(half_df["timestamp"].max())
    if start.date() == end.date():
        return f"{label} ({start.strftime('%b')} {start.day})"
    return f"{label} ({start.strftime('%b')} {start.day}–{end.strftime('%b')} {end.day})"


def _top_half_bigrams(
    phrase_messages_df: pd.DataFrame,
    *,
    period_half: str,
    min_freq: int,
    top_k: int,
) -> pd.DataFrame:
    half_df = phrase_messages_df.loc[phrase_messages_df["period_half"] == period_half].copy()
    bigram_df = _build_ngram_df(
        half_df,
        ngram_size=2,
        min_freq=min_freq,
        min_pmi=float("-inf"),
        phrase_label="bigram",
        entity_terms=set(),
    )
    if bigram_df.empty:
        bigram_df["period_half"] = pd.Series(dtype="object")
        bigram_df["period_label"] = pd.Series(dtype="object")
        return bigram_df

    period_label = _format_half_window(half_df, period_half)
    top_df = bigram_df.head(top_k).copy()
    top_df["period_half"] = period_half
    top_df["period_label"] = period_label
    return top_df


def _build_temporal_change_df(first_half_df: pd.DataFrame, second_half_df: pd.DataFrame) -> pd.DataFrame:
    first_lookup = {row.bigram: row for row in first_half_df.itertuples(index=False)}
    second_lookup = {row.bigram: row for row in second_half_df.itertuples(index=False)}

    rows: list[dict[str, Any]] = []
    for bigram in sorted(set(first_lookup).union(second_lookup)):
        first_row = first_lookup.get(bigram)
        second_row = second_lookup.get(bigram)
        if first_row and second_row:
            status = "retained"
        elif first_row:
            status = "dropped"
        else:
            status = "new"

        rows.append(
            {
                "bigram": bigram,
                "status": status,
                "first_rank": getattr(first_row, "rank", pd.NA),
                "second_rank": getattr(second_row, "rank", pd.NA),
                "first_pmi": getattr(first_row, "pmi", pd.NA),
                "second_pmi": getattr(second_row, "pmi", pd.NA),
                "first_frequency": getattr(first_row, "frequency", pd.NA),
                "second_frequency": getattr(second_row, "frequency", pd.NA),
            }
        )

    phrase_temporal_change_df = pd.DataFrame(rows)
    if phrase_temporal_change_df.empty:
        return pd.DataFrame(
            columns=[
                "bigram",
                "status",
                "first_rank",
                "second_rank",
                "first_pmi",
                "second_pmi",
                "first_frequency",
                "second_frequency",
            ]
        )

    status_order = pd.Categorical(
        phrase_temporal_change_df["status"],
        categories=["new", "dropped", "retained"],
        ordered=True,
    )
    phrase_temporal_change_df = phrase_temporal_change_df.assign(_status_order=status_order)
    phrase_temporal_change_df = phrase_temporal_change_df.sort_values(
        ["_status_order", "second_rank", "first_rank", "bigram"],
        ascending=[True, True, True, True],
    ).drop(columns="_status_order").reset_index(drop=True)
    return phrase_temporal_change_df


def _build_temporal_network_figure(
    first_half_df: pd.DataFrame,
    second_half_df: pd.DataFrame,
    phrase_temporal_change_df: pd.DataFrame,
    *,
    channel_name: str,
    config: PhraseNetworkConfig,
):
    import matplotlib.pyplot as plt
    import networkx as nx
    from matplotlib.patches import Patch

    first_plot_df = first_half_df.head(config.temporal_network_edge_limit).copy()
    second_plot_df = second_half_df.head(config.temporal_network_edge_limit).copy()

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    axes = axes.flatten()
    fig.suptitle(
        f"{channel_name} Telegram - Phrase Network Shift\n"
        "Left highlights phrases absent from the second half (red); right highlights phrases new to the second half (green).",
        fontsize=14,
        y=0.98,
    )

    if first_plot_df.empty and second_plot_df.empty:
        for ax in axes:
            ax.axis("off")
        fig.text(0.5, 0.5, "No temporal bigrams are available under the current filters.", ha="center", va="center", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        return fig

    union_graph = nx.DiGraph()
    for source_df in (first_plot_df, second_plot_df):
        for row in source_df.itertuples(index=False):
            union_graph.add_edge(row.word_1, row.word_2, weight=float(row.frequency), bigram=row.bigram)

    positions = _network_positions(union_graph, layout_seed=config.layout_seed)
    status_lookup = phrase_temporal_change_df.set_index("bigram")["status"].to_dict() if not phrase_temporal_change_df.empty else {}

    plot_specs = [
        (axes[0], first_plot_df, first_plot_df.get("period_label", pd.Series(["First Half"])).iloc[0] if not first_plot_df.empty else "First Half", "dropped"),
        (axes[1], second_plot_df, second_plot_df.get("period_label", pd.Series(["Second Half"])).iloc[0] if not second_plot_df.empty else "Second Half", "new"),
    ]

    for ax, source_df, title, highlight_status in plot_specs:
        ax.set_title(title, fontsize=12, pad=10)
        ax.axis("off")

        if source_df.empty:
            ax.text(0.5, 0.5, "No qualifying bigrams", ha="center", va="center", transform=ax.transAxes, fontsize=12)
            continue

        graph = nx.DiGraph()
        for row in source_df.itertuples(index=False):
            graph.add_edge(row.word_1, row.word_2, weight=float(row.frequency), bigram=row.bigram)

        node_order = list(graph.nodes())
        node_weights = [
            sum(float(data.get("weight", 0.0)) for _, _, data in graph.in_edges(node, data=True))
            + sum(float(data.get("weight", 0.0)) for _, _, data in graph.out_edges(node, data=True))
            for node in node_order
        ]
        node_sizes = _scale_values(node_weights, min_out=700.0, max_out=1900.0)
        edge_weights = [float(data.get("weight", 0.0)) for _, _, data in graph.edges(data=True)]
        edge_widths = _scale_values(edge_weights, min_out=1.8, max_out=5.5)
        edge_colors = []
        for _, _, data in graph.edges(data=True):
            status = status_lookup.get(data.get("bigram", ""), "retained")
            if status == highlight_status:
                edge_colors.append(config.status_colors[highlight_status])
            else:
                edge_colors.append(config.status_colors["retained"])

        nx.draw_networkx_edges(
            graph,
            positions,
            ax=ax,
            arrows=True,
            arrowstyle="-|>",
            arrowsize=16,
            width=edge_widths,
            edge_color=edge_colors,
            alpha=0.8,
            connectionstyle="arc3,rad=0.08",
        )
        nx.draw_networkx_nodes(
            graph,
            positions,
            ax=ax,
            node_size=node_sizes,
            node_color="#4c78a8",
            edgecolors="white",
            linewidths=1.0,
            alpha=0.95,
        )
        nx.draw_networkx_labels(graph, positions, ax=ax, font_size=9, font_weight="bold")

        if graph.number_of_edges() <= 12:
            edge_labels = {(source, target): int(data.get("weight", 0.0)) for source, target, data in graph.edges(data=True)}
            nx.draw_networkx_edge_labels(graph, positions, edge_labels=edge_labels, ax=ax, font_size=8, rotate=False)

    fig.legend(
        handles=[
            Patch(facecolor=config.status_colors["retained"], label="Retained phrase"),
            Patch(facecolor=config.status_colors["dropped"], label="Dropped in second half"),
            Patch(facecolor=config.status_colors["new"], label="New in second half"),
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    return fig


def run_phrase_network_analysis(
    translated_messages: Sequence[RawMessage],
    *,
    channel_label: str,
    entity_terms: set[str] | None = None,
    config: PhraseNetworkConfig | None = None,
) -> PhraseNetworkResult:
    config = config or PhraseNetworkConfig()
    started_at = time.monotonic()

    try:
        import matplotlib.pyplot as plt  # noqa: F401
        import networkx as nx  # noqa: F401
        import numpy as np  # noqa: F401
        import plotly.graph_objects as go  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Phrase-network analysis requires nltk, networkx, plotly, matplotlib, and numpy. "
            "Install notebook extras like: pip install nltk networkx plotly matplotlib numpy"
        ) from exc

    normalized_entity_terms = {token.lower() for token in (entity_terms or set()) if token}
    stop_words = _build_stopwords(channel_label, config)
    phrase_messages_df = _prepare_phrase_messages(translated_messages, stop_words=stop_words, config=config)

    midpoint_timestamp = phrase_messages_df["timestamp"].median()
    phrase_messages_df["period_half"] = pd.Series(
        ["First Half" if timestamp <= midpoint_timestamp else "Second Half" for timestamp in phrase_messages_df["timestamp"]],
        dtype="object",
    )

    phrase_bigram_df = _build_ngram_df(
        phrase_messages_df,
        ngram_size=2,
        min_freq=config.min_bigram_freq,
        min_pmi=config.min_bigram_pmi,
        phrase_label="bigram",
        entity_terms=normalized_entity_terms,
    )
    phrase_trigram_df = _build_ngram_df(
        phrase_messages_df,
        ngram_size=3,
        min_freq=config.min_trigram_freq,
        min_pmi=config.min_trigram_pmi,
        phrase_label="trigram",
        entity_terms=normalized_entity_terms,
    )

    phrase_bigram_graph = _build_phrase_graph(phrase_bigram_df, config)
    phrase_network_nodes_df, phrase_network_edges_df = _build_network_dataframes(phrase_bigram_graph)

    phrase_bigram_bar_df = phrase_bigram_df.head(config.top_bigrams).sort_values(
        ["pmi", "frequency", "bigram"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    first_half_bigrams_df = _top_half_bigrams(
        phrase_messages_df,
        period_half="First Half",
        min_freq=config.temporal_min_freq,
        top_k=config.temporal_top_k,
    )
    second_half_bigrams_df = _top_half_bigrams(
        phrase_messages_df,
        period_half="Second Half",
        min_freq=config.temporal_min_freq,
        top_k=config.temporal_top_k,
    )
    phrase_temporal_bigram_df = pd.concat([first_half_bigrams_df, second_half_bigrams_df], ignore_index=True)
    phrase_temporal_change_df = _build_temporal_change_df(first_half_bigrams_df, second_half_bigrams_df)

    phrase_network_summary_df = pd.DataFrame(
        [
            {
                "messages_analyzed": len(phrase_messages_df),
                "unique_tokens": len({token for tokens in phrase_messages_df["tokens"] for token in tokens}),
                "significant_bigrams": len(phrase_bigram_df),
                "significant_trigrams": len(phrase_trigram_df),
                "network_nodes": phrase_bigram_graph.number_of_nodes(),
                "network_edges": phrase_bigram_graph.number_of_edges(),
                "midpoint_timestamp": midpoint_timestamp,
                "first_half_messages": int((phrase_messages_df["period_half"] == "First Half").sum()),
                "second_half_messages": int((phrase_messages_df["period_half"] == "Second Half").sum()),
                "top_bigram": phrase_bigram_df.iloc[0]["bigram"] if not phrase_bigram_df.empty else None,
                "top_trigram": phrase_trigram_df.iloc[0]["trigram"] if not phrase_trigram_df.empty else None,
            }
        ]
    )

    phrase_network_fig = _build_network_figure(phrase_bigram_graph, channel_name=channel_label, config=config)
    phrase_bigram_bar_fig = _build_bigram_bar_figure(phrase_bigram_bar_df, channel_name=channel_label)
    phrase_temporal_fig = _build_temporal_network_figure(
        first_half_bigrams_df,
        second_half_bigrams_df,
        phrase_temporal_change_df,
        channel_name=channel_label,
        config=config,
    )

    return PhraseNetworkResult(
        phrase_messages_df=phrase_messages_df,
        phrase_bigram_df=phrase_bigram_df,
        phrase_trigram_df=phrase_trigram_df,
        phrase_bigram_bar_df=phrase_bigram_bar_df,
        phrase_network_summary_df=phrase_network_summary_df,
        phrase_network_nodes_df=phrase_network_nodes_df,
        phrase_network_edges_df=phrase_network_edges_df,
        phrase_temporal_bigram_df=phrase_temporal_bigram_df,
        phrase_temporal_change_df=phrase_temporal_change_df,
        phrase_bigram_graph=phrase_bigram_graph,
        phrase_network_fig=phrase_network_fig,
        phrase_bigram_bar_fig=phrase_bigram_bar_fig,
        phrase_temporal_fig=phrase_temporal_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
