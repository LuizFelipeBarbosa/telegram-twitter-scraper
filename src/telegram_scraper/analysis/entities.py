from __future__ import annotations

import re
import textwrap
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import pandas as pd

from telegram_scraper.analysis._common import subplot_grid

DEFAULT_ENTITY_ALIAS_MAP = {
    "United States": "US",
    "the United States": "US",
    "United States of America": "US",
    "U.S.": "US",
    "U.S": "US",
    "US": "US",
    "America": "US",
    "United Nations": "UN",
    "U.N.": "UN",
    "U.N": "UN",
    "Donald Trump": "Trump",
    "President Trump": "Trump",
    "President Donald Trump": "Trump",
    "US President Donald Trump": "Trump",
    "Islamic Republic": "Iran",
    "Islamic Republic of Iran": "Iran",
    "Zionist regime": "Israel",
    "Israeli regime": "Israel",
    "Islamic Revolutionary Guard Corps": "IRGC",
}

DEFAULT_ENTITY_DROP_NAMES = {
    "Press TV",
    "PressTV",
    "Press Tv",
}

ENTITY_TYPE_ORDER = ["PERSON", "ORG", "GPE", "NORP", "UNKNOWN"]
DEFAULT_ENTITY_TYPE_COLORS = {
    "PERSON": "crimson",
    "ORG": "steelblue",
    "GPE": "forestgreen",
    "NORP": "#ffbf00",
    "UNKNOWN": "#8c8c8c",
}

_ENTITY_MENTION_RE = re.compile(r"@\w+")
_ENTITY_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NamedEntityConfig:
    spacy_model: str = "en_core_web_sm"
    labels: set[str] = field(default_factory=lambda: {"PERSON", "ORG", "GPE", "NORP"})
    text_max_chars: int = 1000
    batch_size: int = 64
    min_message_count: int = 3
    min_edge_weight: int = 2
    top_n_bar: int = 20
    ego_panels: int = 4
    ego_max_neighbors: int = 10
    alias_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ENTITY_ALIAS_MAP))
    drop_names: set[str] = field(default_factory=lambda: set(DEFAULT_ENTITY_DROP_NAMES))
    type_colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ENTITY_TYPE_COLORS))


@dataclass(frozen=True)
class NamedEntityResult:
    df_text: pd.DataFrame
    entity_messages_df: pd.DataFrame
    entity_mentions_df: pd.DataFrame
    entity_summary_df: pd.DataFrame
    entity_pair_df: pd.DataFrame
    entity_network_summary_df: pd.DataFrame
    entity_network_nodes_df: pd.DataFrame
    entity_network_edges_df: pd.DataFrame
    entity_community_summary_df: pd.DataFrame
    entity_extraction_summary_df: pd.DataFrame
    named_entity_graph: Any
    entity_top_entities_fig: Any
    entity_network_fig: Any
    entity_ego_fig: Any
    analysis_seconds: float

    def to_namespace(self) -> dict[str, Any]:
        return {
            "df_text": self.df_text,
            "entity_messages_df": self.entity_messages_df,
            "entity_mentions_df": self.entity_mentions_df,
            "entity_summary_df": self.entity_summary_df,
            "entity_pair_df": self.entity_pair_df,
            "entity_network_summary_df": self.entity_network_summary_df,
            "entity_network_nodes_df": self.entity_network_nodes_df,
            "entity_network_edges_df": self.entity_network_edges_df,
            "entity_community_summary_df": self.entity_community_summary_df,
            "entity_extraction_summary_df": self.entity_extraction_summary_df,
            "named_entity_graph": self.named_entity_graph,
            "entity_top_entities_fig": self.entity_top_entities_fig,
            "entity_network_fig": self.entity_network_fig,
            "entity_ego_fig": self.entity_ego_fig,
        }


def clean_ner_text(text: str) -> str:
    cleaned = _ENTITY_MENTION_RE.sub(" ", text or "")
    cleaned = _ENTITY_WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def normalize_entity_name(name: str, config: NamedEntityConfig) -> str:
    cleaned = (name or "").strip(" \n\t'\"“”‘’.,:;!?()[]{}")
    cleaned = cleaned.replace("’", "'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""

    alias_hit = config.alias_map.get(cleaned)
    if alias_hit:
        return alias_hit

    if re.fullmatch(r"(?:the\s+)?United States(?: of America)?|U\.?S\.?|America", cleaned, flags=re.IGNORECASE):
        return "US"
    if re.fullmatch(r"(?:the\s+)?United Nations|U\.?N\.?", cleaned, flags=re.IGNORECASE):
        return "UN"
    if re.fullmatch(r"(?:US\s+)?President\s+Donald\s+Trump|President\s+Trump|Donald\s+Trump", cleaned, flags=re.IGNORECASE):
        return "Trump"
    if re.fullmatch(r"Islamic Republic(?: of Iran)?", cleaned, flags=re.IGNORECASE):
        return "Iran"
    if re.fullmatch(r"Zionist regime|Israeli regime", cleaned, flags=re.IGNORECASE):
        return "Israel"
    if re.fullmatch(r"Islamic Revolutionary Guard Corps|IRGC", cleaned, flags=re.IGNORECASE):
        return "IRGC"
    return cleaned


def strongest_links(node_name: str, graph: Any, *, limit: int = 5) -> str:
    neighbors = sorted(graph[node_name].items(), key=lambda item: item[1].get("weight", 0), reverse=True)
    return ", ".join(f"{neighbor} ({data.get('weight', 0)})" for neighbor, data in neighbors[:limit])


def _load_spacy_pipeline(config: NamedEntityConfig):
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Named-entity analysis requires spaCy plus an English model. Install notebook extras like: "
            "pip install spacy networkx plotly python-louvain matplotlib && python -m spacy download en_core_web_sm"
        ) from exc

    try:
        return spacy.load(config.spacy_model)
    except OSError as exc:  # pragma: no cover - exercised in notebook env
        raise OSError(
            f"Named-entity analysis requires the spaCy model '{config.spacy_model}'. "
            f"Install it with: python -m spacy download {config.spacy_model}"
        ) from exc


def run_named_entity_analysis(
    df_text: pd.DataFrame,
    *,
    channel_label: str,
    config: NamedEntityConfig | None = None,
) -> NamedEntityResult:
    config = config or NamedEntityConfig()
    started_at = time.monotonic()

    try:
        import matplotlib.pyplot as plt
        import networkx as nx
        import numpy as np
        import plotly.express as px
        import plotly.graph_objects as go
        from matplotlib.patches import Patch
    except ImportError as exc:  # pragma: no cover - exercised in notebook env
        raise ImportError(
            "Named-entity analysis requires networkx, plotly, matplotlib, and numpy. "
            "Install notebook extras like: pip install networkx plotly spacy python-louvain matplotlib"
        ) from exc

    try:
        from community import community_louvain
    except ImportError:  # pragma: no cover - optional fallback
        community_louvain = None

    if df_text.empty:
        raise RuntimeError("Section 9 requires df_text from Section 6. Run Sections 4 and 6 first.")

    ner_source_df = df_text.copy()
    ner_source_df["ner_text"] = ner_source_df["text"].fillna("").map(clean_ner_text)
    ner_source_df = ner_source_df.loc[ner_source_df["ner_text"].str.len() > 0].copy()
    if ner_source_df.empty:
        raise RuntimeError("No text-bearing messages remain for named-entity analysis after NER cleaning.")

    entity_nlp = _load_spacy_pipeline(config)
    entity_pipe_disable = [
        name for name in entity_nlp.pipe_names if name not in {"ner", "tok2vec", "transformer"}
    ]
    entity_docs = entity_nlp.pipe(
        ner_source_df["ner_text"].str.slice(0, config.text_max_chars).tolist(),
        batch_size=config.batch_size,
        disable=entity_pipe_disable,
    )

    entity_rows: list[dict[str, Any]] = []
    message_entity_records: list[dict[str, Any]] = []
    entity_counter: Counter[str] = Counter()
    pair_counter: Counter[tuple[str, str]] = Counter()
    entity_label_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)
    entity_surface_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)
    pair_first_seen: dict[tuple[str, str], Any] = {}
    pair_last_seen: dict[tuple[str, str], Any] = {}
    pair_example_lookup: dict[tuple[str, str], str] = {}

    for row, doc in zip(ner_source_df.itertuples(index=False), entity_docs):
        raw_entities: list[tuple[str, str]] = []
        normalized_entities: list[tuple[str, str]] = []

        for ent in doc.ents:
            if ent.label_ not in config.labels:
                continue

            raw_name = ent.text.strip()
            normalized_name = normalize_entity_name(raw_name, config)
            if not normalized_name or normalized_name in config.drop_names:
                continue

            raw_entities.append((raw_name, ent.label_))
            normalized_entities.append((normalized_name, ent.label_))
            entity_rows.append(
                {
                    "channel_id": row.channel_id,
                    "message_id": row.message_id,
                    "timestamp": row.timestamp,
                    "raw_entity": raw_name,
                    "entity": normalized_name,
                    "entity_label": ent.label_,
                    "text": row.text,
                }
            )
            entity_label_counter[normalized_name][ent.label_] += 1
            entity_surface_counter[normalized_name][raw_name] += 1

        unique_entity_names = sorted({name for name, _ in normalized_entities})
        for entity_name in unique_entity_names:
            entity_counter[entity_name] += 1

        for pair in combinations(unique_entity_names, 2):
            pair_counter[pair] += 1
            pair_first_seen.setdefault(pair, row.timestamp)
            pair_last_seen[pair] = row.timestamp
            if pair not in pair_example_lookup:
                pair_example_lookup[pair] = textwrap.shorten(
                    (row.text or "").replace("\n", " "),
                    width=120,
                    placeholder="...",
                )

        message_entity_records.append(
            {
                "channel_id": row.channel_id,
                "message_id": row.message_id,
                "timestamp": row.timestamp,
                "source_language": row.source_language,
                "used_translation": row.used_translation,
                "text": row.text,
                "ner_text": row.ner_text,
                "entities": raw_entities,
                "normalized_entities": normalized_entities,
                "entity_names": unique_entity_names,
                "entity_count": len(unique_entity_names),
                "entity_names_preview": ", ".join(unique_entity_names[:8]) + (" ..." if len(unique_entity_names) > 8 else ""),
                "text_preview": textwrap.shorten((row.text or "").replace("\n", " "), width=120, placeholder="..."),
            }
        )

    entity_messages_df = pd.DataFrame(message_entity_records).sort_values("timestamp").reset_index(drop=True)
    entity_mentions_df = pd.DataFrame(
        entity_rows,
        columns=["channel_id", "message_id", "timestamp", "raw_entity", "entity", "entity_label", "text"],
    )
    if not entity_mentions_df.empty:
        entity_mentions_df = entity_mentions_df.sort_values(["timestamp", "message_id", "entity"]).reset_index(drop=True)

    if entity_mentions_df.empty:
        raise RuntimeError(
            "spaCy did not extract any PERSON/ORG/GPE/NORP entities. Inspect the text or try a different model."
        )

    entity_list_lookup = entity_messages_df.set_index(["channel_id", "message_id"])["entities"].to_dict()
    normalized_entity_lookup = entity_messages_df.set_index(["channel_id", "message_id"])["normalized_entities"].to_dict()
    entity_names_lookup = entity_messages_df.set_index(["channel_id", "message_id"])["entity_names"].to_dict()
    entity_count_lookup = entity_messages_df.set_index(["channel_id", "message_id"])["entity_count"].to_dict()

    df_text_with_entities = df_text.copy()
    df_text_with_entities["entities"] = [
        entity_list_lookup.get((row.channel_id, row.message_id), [])
        for row in df_text_with_entities.itertuples(index=False)
    ]
    df_text_with_entities["normalized_entities"] = [
        normalized_entity_lookup.get((row.channel_id, row.message_id), [])
        for row in df_text_with_entities.itertuples(index=False)
    ]
    df_text_with_entities["entity_names"] = [
        entity_names_lookup.get((row.channel_id, row.message_id), [])
        for row in df_text_with_entities.itertuples(index=False)
    ]
    df_text_with_entities["entity_count"] = [
        entity_count_lookup.get((row.channel_id, row.message_id), 0)
        for row in df_text_with_entities.itertuples(index=False)
    ]

    entity_extraction_summary_df = pd.DataFrame(
        [
            {
                "messages_available": len(df_text_with_entities),
                "messages_ner_ready": len(entity_messages_df),
                "messages_with_entities": int(entity_messages_df["entity_count"].gt(0).sum()),
                "entity_mentions": len(entity_mentions_df),
                "unique_normalized_entities": len(entity_counter),
                "spacy_model": config.spacy_model,
            }
        ]
    )

    entity_summary_rows: list[dict[str, Any]] = []
    for entity, message_count in entity_counter.items():
        label_counts = entity_label_counter.get(entity, Counter())
        surface_counts = entity_surface_counter.get(entity, Counter())
        entity_type = label_counts.most_common(1)[0][0] if label_counts else "UNKNOWN"
        surface_form_preview = ", ".join(surface for surface, _ in surface_counts.most_common(5))
        entity_summary_rows.append(
            {
                "entity": entity,
                "message_count": int(message_count),
                "entity_type": entity_type,
                "top_surface_form": surface_counts.most_common(1)[0][0] if surface_counts else entity,
                "surface_forms": surface_form_preview,
                "unique_surface_forms": len(surface_counts),
            }
        )

    entity_summary_df = pd.DataFrame(entity_summary_rows).sort_values(
        ["message_count", "entity"],
        ascending=[False, True],
    ).reset_index(drop=True)
    if entity_summary_df.empty:
        raise RuntimeError("No normalized entities were available for graph construction.")

    entity_pair_rows: list[dict[str, Any]] = []
    for (entity_1, entity_2), weight in pair_counter.items():
        entity_pair_rows.append(
            {
                "entity_1": entity_1,
                "entity_2": entity_2,
                "weight": int(weight),
                "first_seen": pair_first_seen.get((entity_1, entity_2)),
                "last_seen": pair_last_seen.get((entity_1, entity_2)),
                "example_text": pair_example_lookup.get((entity_1, entity_2), ""),
            }
        )
    entity_pair_df = pd.DataFrame(
        entity_pair_rows,
        columns=["entity_1", "entity_2", "weight", "first_seen", "last_seen", "example_text"],
    )
    if not entity_pair_df.empty:
        entity_pair_df = entity_pair_df.sort_values(["weight", "entity_1", "entity_2"], ascending=[False, True, True]).reset_index(drop=True)

    entity_graph_input_df = entity_summary_df.loc[entity_summary_df["message_count"] >= config.min_message_count].copy()
    named_entity_graph = nx.Graph()
    for row in entity_graph_input_df.itertuples(index=False):
        named_entity_graph.add_node(
            row.entity,
            message_count=int(row.message_count),
            entity_type=row.entity_type,
            top_surface_form=row.top_surface_form,
            surface_forms=row.surface_forms,
        )

    for row in entity_pair_df.itertuples(index=False):
        if row.weight < config.min_edge_weight:
            continue
        if not (named_entity_graph.has_node(row.entity_1) and named_entity_graph.has_node(row.entity_2)):
            continue
        named_entity_graph.add_edge(
            row.entity_1,
            row.entity_2,
            weight=int(row.weight),
            first_seen=row.first_seen,
            last_seen=row.last_seen,
            example_text=row.example_text,
        )

    named_entity_graph.remove_nodes_from(list(nx.isolates(named_entity_graph)))

    if named_entity_graph.number_of_nodes() == 0:
        entity_partition = {}
        entity_community_method = "no_graph"
        entity_layout = {}
    elif named_entity_graph.number_of_edges() == 0:
        entity_partition = {node: index for index, node in enumerate(named_entity_graph.nodes())}
        entity_community_method = "singleton"
        entity_layout = nx.spring_layout(named_entity_graph, seed=42)
    else:
        if community_louvain is not None:
            try:
                entity_partition = community_louvain.best_partition(named_entity_graph, weight="weight", random_state=42)
            except TypeError:
                entity_partition = community_louvain.best_partition(named_entity_graph, weight="weight")
            entity_community_method = "louvain"
        else:
            entity_community_sets = list(
                nx.algorithms.community.greedy_modularity_communities(named_entity_graph, weight="weight")
            )
            entity_partition = {
                node: community_id
                for community_id, community_nodes in enumerate(entity_community_sets)
                for node in community_nodes
            }
            entity_community_method = "greedy_modularity"
        entity_layout = nx.spring_layout(named_entity_graph, k=2.0, iterations=150, weight="weight", seed=42)

    nx.set_node_attributes(named_entity_graph, entity_partition, "community")
    for node in named_entity_graph.nodes():
        named_entity_graph.nodes[node]["degree"] = int(named_entity_graph.degree(node))
        named_entity_graph.nodes[node]["weighted_degree"] = float(named_entity_graph.degree(node, weight="weight"))
        named_entity_graph.nodes[node]["community_label"] = f"C{entity_partition.get(node, 0) + 1}"

    entity_network_nodes_df = pd.DataFrame(
        [
            {
                "entity": node,
                "message_count": data["message_count"],
                "entity_type": data["entity_type"],
                "graph_degree": data["degree"],
                "weighted_degree": round(data["weighted_degree"], 3),
                "community": int(data.get("community", 0)),
                "community_label": data.get("community_label", "C1"),
                "x": float(entity_layout[node][0]) if node in entity_layout else 0.0,
                "y": float(entity_layout[node][1]) if node in entity_layout else 0.0,
                "top_surface_form": data.get("top_surface_form", node),
                "surface_forms": data.get("surface_forms", ""),
                "strongest_links": strongest_links(node, named_entity_graph) if named_entity_graph.number_of_edges() else "",
            }
            for node, data in named_entity_graph.nodes(data=True)
        ]
    )
    if not entity_network_nodes_df.empty:
        entity_network_nodes_df = entity_network_nodes_df.sort_values(
            ["message_count", "weighted_degree", "entity"],
            ascending=[False, False, True],
        ).reset_index(drop=True)

    entity_network_edges_df = pd.DataFrame(
        [
            {
                "entity_1": u,
                "entity_2": v,
                "weight": int(data["weight"]),
                "first_seen": data.get("first_seen"),
                "last_seen": data.get("last_seen"),
                "example_text": data.get("example_text", ""),
            }
            for u, v, data in named_entity_graph.edges(data=True)
        ]
    )
    if not entity_network_edges_df.empty:
        entity_network_edges_df = entity_network_edges_df.sort_values(["weight", "entity_1", "entity_2"], ascending=[False, True, True]).reset_index(drop=True)

    entity_summary_df = entity_summary_df.merge(
        entity_network_nodes_df[["entity", "graph_degree", "weighted_degree", "community_label"]]
        if not entity_network_nodes_df.empty
        else pd.DataFrame(columns=["entity", "graph_degree", "weighted_degree", "community_label"]),
        on="entity",
        how="left",
    )
    entity_summary_df["graph_degree"] = entity_summary_df["graph_degree"].fillna(0).astype(int)
    entity_summary_df["weighted_degree"] = entity_summary_df["weighted_degree"].fillna(0.0)
    entity_summary_df["community_label"] = entity_summary_df["community_label"].fillna("—")

    if not entity_network_nodes_df.empty:
        entity_community_summary_df = (
            entity_network_nodes_df.groupby(["community", "community_label"], as_index=False)
            .agg(
                node_count=("entity", "size"),
                total_message_count=("message_count", "sum"),
                exemplar_entities=("entity", lambda values: ", ".join(values[:5])),
            )
            .sort_values(["total_message_count", "node_count"], ascending=[False, False])
            .reset_index(drop=True)
        )
    else:
        entity_community_summary_df = pd.DataFrame(
            columns=["community", "community_label", "node_count", "total_message_count", "exemplar_entities"]
        )

    entity_network_summary_df = pd.DataFrame(
        [
            {
                "messages_analyzed": len(entity_messages_df),
                "messages_with_entities": int(entity_messages_df["entity_count"].gt(0).sum()),
                "unique_entities_before_filter": len(entity_summary_df),
                "nodes_after_filter": int(named_entity_graph.number_of_nodes()),
                "edges_after_filter": int(named_entity_graph.number_of_edges()),
                "min_entity_messages": config.min_message_count,
                "min_edge_weight": config.min_edge_weight,
                "community_method": entity_community_method,
            }
        ]
    )

    def scale_marker_sizes(values: Any, min_size: float = 14, max_size: float = 42) -> list[float]:
        array = np.asarray(list(values), dtype=float)
        if array.size == 0:
            return []
        if np.isclose(array.max(), array.min()):
            return [0.5 * (min_size + max_size)] * len(array)
        scaled = (array - array.min()) / (array.max() - array.min())
        return (min_size + scaled * (max_size - min_size)).tolist()

    def node_hover_text(row: pd.Series) -> str:
        strongest_links_text = row["strongest_links"] or "—"
        return (
            f"<b>{row['entity']}</b><br>"
            f"Messages: {int(row['message_count'])}<br>"
            f"Type: {row['entity_type']}<br>"
            f"Community: {row['community_label']}<br>"
            f"Degree: {int(row['graph_degree'])}<br>"
            f"Weighted degree: {float(row['weighted_degree']):.1f}<br>"
            f"Surface forms: {row['surface_forms'] or row['top_surface_form']}<br>"
            f"Strongest links: {strongest_links_text}"
        )

    if entity_network_nodes_df.empty:
        entity_network_fig = go.Figure()
    else:
        node_plot_df = entity_network_nodes_df.copy()
        node_plot_df["label_text"] = ""
        label_nodes = set(node_plot_df.head(min(20, len(node_plot_df)))["entity"].tolist())
        node_plot_df.loc[node_plot_df["entity"].isin(label_nodes), "label_text"] = node_plot_df["entity"]
        node_plot_df["hover_text"] = node_plot_df.apply(node_hover_text, axis=1)
        node_plot_df["marker_size"] = scale_marker_sizes(node_plot_df["message_count"], 16, 44)
        node_plot_df["marker_color"] = node_plot_df["entity_type"].map(config.type_colors).fillna(config.type_colors["UNKNOWN"])

        edge_traces = []
        edge_hover_x: list[float] = []
        edge_hover_y: list[float] = []
        edge_hover_text: list[str] = []
        for row in entity_network_edges_df.itertuples(index=False):
            x0, y0 = entity_layout[row.entity_1]
            x1, y1 = entity_layout[row.entity_2]
            line_width = 0.7 + 1.0 * np.sqrt(row.weight)
            line_alpha = min(0.15 + 0.07 * row.weight, 0.65)
            edge_traces.append(
                go.Scatter(
                    x=[x0, x1, None],
                    y=[y0, y1, None],
                    mode="lines",
                    line={"width": line_width, "color": f"rgba(120, 120, 120, {line_alpha:.3f})"},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            edge_hover_x.append((x0 + x1) / 2)
            edge_hover_y.append((y0 + y1) / 2)
            edge_hover_text.append(
                f"<b>{row.entity_1} ↔ {row.entity_2}</b><br>"
                f"Co-occurring messages: {row.weight}<br>"
                f"First seen: {pd.Timestamp(row.first_seen):%Y-%m-%d %H:%M UTC}<br>"
                f"Last seen: {pd.Timestamp(row.last_seen):%Y-%m-%d %H:%M UTC}<br>"
                f"Example: {row.example_text}"
            )

        edge_hover_trace = go.Scatter(
            x=edge_hover_x,
            y=edge_hover_y,
            mode="markers",
            marker={"size": 10, "color": "rgba(0, 0, 0, 0)"},
            text=edge_hover_text,
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
        )

        node_trace = go.Scatter(
            x=node_plot_df["x"],
            y=node_plot_df["y"],
            mode="markers+text",
            text=node_plot_df["label_text"],
            textposition="top center",
            textfont={"size": 10, "color": "#222222"},
            hovertext=node_plot_df["hover_text"],
            hovertemplate="%{hovertext}<extra></extra>",
            marker={
                "size": node_plot_df["marker_size"],
                "color": node_plot_df["marker_color"],
                "line": {"width": 1.2, "color": "white"},
                "opacity": 0.92,
            },
            showlegend=False,
        )

        legend_traces = []
        for entity_type in ENTITY_TYPE_ORDER:
            if entity_type not in set(node_plot_df["entity_type"]):
                continue
            legend_traces.append(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker={"size": 12, "color": config.type_colors[entity_type]},
                    name=entity_type,
                    hoverinfo="skip",
                )
            )

        entity_network_fig = go.Figure(data=edge_traces + [edge_hover_trace] + legend_traces + [node_trace])
        entity_network_fig.update_layout(
            title=(
                f"{channel_label} Telegram - Named Entity Co-occurrence Network"
                f"<br><sup>Nodes: messages ≥ {config.min_message_count}; "
                f"edges: co-occurrence ≥ {config.min_edge_weight}; communities: {entity_community_method}</sup>"
            ),
            template="plotly_white",
            height=760,
            margin={"l": 20, "r": 20, "t": 90, "b": 20},
            xaxis={"visible": False},
            yaxis={"visible": False},
            hovermode="closest",
            legend_title_text="Entity type",
        )

    entity_bar_df = entity_summary_df.head(config.top_n_bar).copy().sort_values("message_count", ascending=True)
    entity_top_entities_fig = px.bar(
        entity_bar_df,
        x="message_count",
        y="entity",
        orientation="h",
        color="entity_type",
        color_discrete_map=config.type_colors,
        custom_data=["top_surface_form", "graph_degree", "weighted_degree", "community_label"],
        title=f"{channel_label} Telegram - Top {len(entity_bar_df)} Named Entities",
        template="plotly_white",
    )
    entity_top_entities_fig.update_layout(
        yaxis_title="Entity",
        xaxis_title="Messages mentioning entity",
        height=max(420, 120 + 28 * len(entity_bar_df)),
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
    )
    entity_top_entities_fig.update_traces(
        texttemplate="%{x}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Messages: %{x}<br>"
            "Canonical surface: %{customdata[0]}<br>"
            "Graph degree: %{customdata[1]}<br>"
            "Weighted degree: %{customdata[2]:.1f}<br>"
            "Community: %{customdata[3]}<extra></extra>"
        ),
    )

    entity_ego_candidates = ["Iran", "US", "Israel", "Trump", "Hezbollah", "UN"]
    entity_ego_target_entities = [entity for entity in entity_ego_candidates if entity in named_entity_graph]
    if len(entity_ego_target_entities) < config.ego_panels:
        for entity in entity_network_nodes_df.sort_values(["weighted_degree", "message_count"], ascending=[False, False])["entity"]:
            if entity not in entity_ego_target_entities:
                entity_ego_target_entities.append(entity)
            if len(entity_ego_target_entities) >= config.ego_panels:
                break
    entity_ego_target_entities = entity_ego_target_entities[: config.ego_panels]

    if not entity_ego_target_entities:
        entity_ego_fig = None
    else:
        ego_rows, ego_cols = subplot_grid(len(entity_ego_target_entities), max_cols=2)
        entity_ego_fig, entity_ego_axes = plt.subplots(
            ego_rows,
            ego_cols,
            figsize=(18, 6 * ego_rows),
            constrained_layout=True,
        )
        entity_ego_axes = np.atleast_1d(entity_ego_axes).ravel()

        for ax, center_entity in zip(entity_ego_axes, entity_ego_target_entities):
            neighbor_items = sorted(named_entity_graph[center_entity].items(), key=lambda item: item[1].get("weight", 0), reverse=True)
            top_neighbors = [neighbor for neighbor, _ in neighbor_items[: config.ego_max_neighbors]]
            ego_nodes = [center_entity, *top_neighbors]
            ego_graph = named_entity_graph.subgraph(ego_nodes).copy()
            ego_pos = nx.spring_layout(ego_graph, seed=42, weight="weight", k=1.8)

            edge_widths = [1.0 + 0.75 * data.get("weight", 1) for _, _, data in ego_graph.edges(data=True)]
            node_sizes = [280 + 90 * ego_graph.nodes[node].get("message_count", 1) for node in ego_graph.nodes()]
            node_colors = [
                config.type_colors.get(ego_graph.nodes[node].get("entity_type", "UNKNOWN"), config.type_colors["UNKNOWN"])
                for node in ego_graph.nodes()
            ]

            nx.draw_networkx_edges(ego_graph, ego_pos, width=edge_widths, edge_color="#9a9a9a", alpha=0.55, ax=ax)
            nx.draw_networkx_nodes(
                ego_graph,
                ego_pos,
                nodelist=list(ego_graph.nodes()),
                node_size=node_sizes,
                node_color=node_colors,
                edgecolors="white",
                linewidths=1.2,
                alpha=0.94,
                ax=ax,
            )
            nx.draw_networkx_nodes(
                ego_graph,
                ego_pos,
                nodelist=[center_entity],
                node_size=[280 + 90 * ego_graph.nodes[center_entity].get("message_count", 1)],
                node_color=[
                    config.type_colors.get(
                        ego_graph.nodes[center_entity].get("entity_type", "UNKNOWN"),
                        config.type_colors["UNKNOWN"],
                    )
                ],
                edgecolors="black",
                linewidths=2.4,
                ax=ax,
            )
            nx.draw_networkx_labels(ego_graph, ego_pos, font_size=9, font_weight="bold", ax=ax)
            if ego_graph.number_of_edges() <= 20:
                nx.draw_networkx_edge_labels(
                    ego_graph,
                    ego_pos,
                    edge_labels={(u, v): data.get("weight", 0) for u, v, data in ego_graph.edges(data=True)},
                    font_size=8,
                    rotate=False,
                    ax=ax,
                )
            ax.set_title(f"{center_entity} ego network ({len(ego_graph) - 1} neighbors shown)", fontsize=12, pad=10)
            ax.axis("off")

        for ax in entity_ego_axes[len(entity_ego_target_entities) :]:
            ax.set_visible(False)

        legend_handles = [
            Patch(facecolor=config.type_colors[entity_type], label=entity_type)
            for entity_type in ENTITY_TYPE_ORDER
            if entity_type in set(entity_network_nodes_df["entity_type"])
        ]
        if legend_handles:
            entity_ego_fig.legend(
                handles=legend_handles,
                loc="upper center",
                ncol=min(5, len(legend_handles)),
                frameon=True,
            )
        entity_ego_fig.suptitle(f"{channel_label} Telegram - Ego Networks for Key Actors", fontsize=15, y=1.02)

    return NamedEntityResult(
        df_text=df_text_with_entities,
        entity_messages_df=entity_messages_df,
        entity_mentions_df=entity_mentions_df,
        entity_summary_df=entity_summary_df,
        entity_pair_df=entity_pair_df,
        entity_network_summary_df=entity_network_summary_df,
        entity_network_nodes_df=entity_network_nodes_df,
        entity_network_edges_df=entity_network_edges_df,
        entity_community_summary_df=entity_community_summary_df,
        entity_extraction_summary_df=entity_extraction_summary_df,
        named_entity_graph=named_entity_graph,
        entity_top_entities_fig=entity_top_entities_fig,
        entity_network_fig=entity_network_fig,
        entity_ego_fig=entity_ego_fig,
        analysis_seconds=time.monotonic() - started_at,
    )
