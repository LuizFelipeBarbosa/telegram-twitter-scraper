# Plan 4 — Named Entity Network Graphs

> **Dataset:** text-bearing messages exported by a channel-specific pipeline notebook (e.g. `notebooks/pipeline_<slug>.ipynb` or `CHANNEL_RESULTS[slug]["df_text"]` from the multi-channel pipeline).
> **Period:** whatever window the export covers.
> **Objective:** Map the "cast of characters" in the channel's coverage — which people, organizations, nations, or groups are mentioned together, revealing the channel's narrative structure and framing of alliances / opposition.
>
> _Illustrative sample values in this plan are drawn from a prior PressTV run (940 text-bearing messages, April 6–14 2026, ~8 days). Substitute your own channel's counts and window when applying the plan._

---

## Goal

Extract every named entity (person, organization, country, group) from the corpus, then build a co-occurrence network showing who gets linked with whom within the same message. The resulting graph reveals the channel's implicit framing: which actors are placed in the same context, what alliances and oppositions are constructed through adjacency.

---

## Pipeline

### Step 1 — NER Extraction

Run spaCy NER on each message. Target entity labels:

| Label | Description | Example entities (swap for your channel's beat) |
|-------|-------------|----------|
| `PERSON` | Named individuals | Trump, Velayati, Nasrallah |
| `ORG` | Organizations | UN, Hezbollah, Pentagon, IRGC |
| `GPE` | Geopolitical entities | Iran, Israel, Lebanon, Pakistan |
| `NORP` | Nationalities / groups | American, Shia, Arab, Palestinian |

```python
import spacy

nlp = spacy.load("en_core_web_sm")  # or en_core_web_trf for accuracy

def extract_entities(text):
    doc = nlp(text[:1000])  # cap length for speed
    return [
        (ent.text, ent.label_)
        for ent in doc.ents
        if ent.label_ in {"PERSON", "ORG", "GPE", "NORP"}
    ]

df_text["entities"] = df_text["text"].apply(extract_entities)
```

### Step 2 — Entity Normalization

NER models produce noisy variants. Normalize common aliases. The map below is a starting point — `src/telegram_scraper/analysis/entities.py` ships `DEFAULT_ENTITY_ALIAS_MAP` and a `NamedEntityConfig.alias_map` override you can pass per channel to handle ideological renames (e.g., a pro-Tehran channel's "Zionist regime" → "Israel"; a pro-Jerusalem channel's "Judea and Samaria" → "West Bank"; a US-politics channel's "Sleepy Joe" → "Biden"). Extend it after skimming the top-N unnormalized entities on a first pass.

```python
# Starter map — extend per channel.
ENTITY_MAP = {
    "United States": "US",
    "America": "US",
    "the United States": "US",
    "Donald Trump": "Trump",
    "President Trump": "Trump",
    # Channel-specific ideological labels (example values from PressTV):
    "Islamic Republic": "Iran",
    "Zionist regime": "Israel",
    "Israeli regime": "Israel",
}

def normalize_entity(name):
    return ENTITY_MAP.get(name, name)
```

### Step 3 — Co-occurrence Matrix

For each message, generate all unique entity pairs (order-independent). Increment a co-occurrence counter.

```python
from collections import Counter
from itertools import combinations

pair_counter = Counter()
entity_counter = Counter()

for entities in df_text["entities"]:
    unique_names = list(set(normalize_entity(e[0]) for e in entities))
    for name in unique_names:
        entity_counter[name] += 1
    for pair in combinations(sorted(unique_names), 2):
        pair_counter[pair] += 1
```

Filter out entities appearing fewer than 3 times to reduce noise.

### Step 4 — Graph Construction

```python
import networkx as nx

G = nx.Graph()

# Add nodes with frequency as attribute
for entity, count in entity_counter.items():
    if count >= 3:
        # Determine entity type from most common label
        G.add_node(entity, count=count, type=most_common_type)

# Add edges with co-occurrence weight
for (e1, e2), weight in pair_counter.items():
    if weight >= 2 and e1 in G and e2 in G:
        G.add_edge(e1, e2, weight=weight)
```

### Step 5 — Community Detection

```python
from community import community_louvain

partition = community_louvain.best_partition(G, weight="weight")
nx.set_node_attributes(G, partition, "community")
```

Expected community structure depends heavily on the channel. For a Middle-East-focused geopolitical channel, communities might emerge around Iranian officials, US/Israeli actors, Arab states, and international organizations. For other beats (e.g., domestic politics, business, sports) the communities will reflect that domain's factions instead — read the Louvain partition as the channel's own implicit grouping of actors.

### Step 6 — Layout

```python
pos = nx.spring_layout(G, k=2.0, iterations=100, weight="weight", seed=42)
# Alternative: nx.kamada_kawai_layout(G, weight="weight")
```

---

## Visualization

### Primary — Interactive Network Graph

- **Nodes:** Sized by mention frequency. Colored by entity type:
  - `PERSON` = crimson
  - `ORG` = steel blue
  - `GPE` = forest green
  - `NORP` = amber
- **Edges:** Thickness proportional to co-occurrence weight. Opacity scaled to prevent visual clutter.
- **Hover:** Entity name, mention count, entity type, community label.
- **Interaction:** Zoom, pan, drag nodes. Click to highlight ego network.

**Implementation:** Use Pyvis for quick interactive HTML output, or Plotly for more control.

```python
from pyvis.network import Network

net = Network(height="700px", width="100%", bgcolor="#0a0a0a", font_color="white")
for node in G.nodes(data=True):
    net.add_node(node[0], size=node[1]["count"] * 2, color=type_color_map[node[1]["type"]])
for e1, e2, data in G.edges(data=True):
    net.add_edge(e1, e2, value=data["weight"])
net.show("entity_network.html")
```

### Secondary — Top-20 Entity Bar Chart

- Horizontal bars, one per entity.
- Bar length = total mention count.
- Stacked or colored by entity type.
- Ordered descending.

### Tertiary — Ego Network Subgraphs

For 3–4 key actors, extract each one's ego network (immediate neighbors only) and display as separate small graphs. Reveals each actor's narrative context — who they're framed alongside.

Pick the ego targets from the top of `entity_summary_df` (or pass an explicit candidate list through `NamedEntityConfig` — see `src/telegram_scraper/analysis/entities.py`). Good defaults are the top 4 entities by weighted degree; for comparability across channels, override that with a small set of shared actors that appear in every channel's graph.

```python
# Pick ego targets dynamically from the top of the entity ranking.
ego_targets = (
    entity_network_nodes_df
    .sort_values(["weighted_degree", "message_count"], ascending=[False, False])
    ["entity"]
    .head(4)
    .tolist()
)

# Or pin a shared set for cross-channel comparison (example from PressTV run):
# ego_targets = ["Iran", "US", "Israel", "Trump"]

ego_subgraphs = {name: nx.ego_graph(G, name, radius=1) for name in ego_targets if name in G}
```

---

## Libraries

```
spacy (en_core_web_sm or en_core_web_trf)
networkx
pyvis or plotly
community (python-louvain)
pandas
```

---

## Estimated Complexity

**Medium** — NER is the slow step (~2–3 min on CPU with `en_core_web_sm`, longer with `trf`). Graph construction is fast. Layout tuning and entity normalization require manual iteration.

---

## Expected Insights

- The central nodes in the channel's narrative (for a prior PressTV run these were Iran, US, Israel, and Trump; for a different channel the core cast will differ — that contrast is one of the most useful cross-channel comparisons this plan enables).
- Which actors are framed as connected — e.g., does a militia name always co-occur with a specific state sponsor, or does it also appear in independent contexts?
- Community structure revealing implicit alliance framing (e.g., one bloc vs. another).
- Peripheral entities that appear rarely but in notable combinations.
- Whether the channel's entity landscape is tightly focused (few dominant actors, high graph density) or broad (many actors with moderate attention, lower density) — a simple proxy for editorial scope.
- Cross-channel: running this plan over each `CHANNEL_RESULTS[slug]` and aligning the top-N actor lists reveals which entities are shared across outlets and which are unique to a specific channel's framing.
