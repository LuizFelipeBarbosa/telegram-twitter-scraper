# Plan 4 — Named Entity Network Graphs

> **Dataset:** 940 text-bearing messages from PressTV Telegram channel
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Map the political "cast of characters" — which people, organizations, and nations are mentioned together, revealing PressTV's narrative structure and framing of alliances/opposition.

---

## Goal

Extract every named entity (person, organization, country, group) from the corpus, then build a co-occurrence network showing who gets linked with whom within the same message. The resulting graph reveals PressTV's implicit framing: which actors are placed in the same context, what alliances and oppositions are constructed through adjacency.

---

## Pipeline

### Step 1 — NER Extraction

Run spaCy NER on each message. Target entity labels:

| Label | Description | Examples |
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

NER models produce noisy variants. Normalize common aliases:

```python
ENTITY_MAP = {
    "United States": "US",
    "America": "US",
    "the United States": "US",
    "Islamic Republic": "Iran",
    "Zionist regime": "Israel",
    "Israeli regime": "Israel",
    "Donald Trump": "Trump",
    "President Trump": "Trump",
    # Add more as discovered in the data
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

Expected communities might include: Iranian officials cluster, US/Israel cluster, Arab states cluster, international organizations cluster.

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

For 3–4 key actors (e.g., "Iran", "Trump", "Hezbollah", "UN"), extract their ego network (immediate neighbors only) and display as separate small graphs. Reveals each actor's narrative context — who they're framed alongside.

```python
ego = nx.ego_graph(G, "Iran", radius=1)
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

- The central nodes in PressTV's narrative (likely Iran, US, Israel, Trump).
- Which actors are framed as connected — e.g., is "Hezbollah" always co-mentioned with "Iran" or sometimes with "Lebanon" independently?
- Community structure revealing implicit alliance framing (Iran + allies vs. US + Israel).
- Peripheral entities that appear rarely but in notable combinations.
- Whether PressTV's entity landscape is tightly focused (few dominant actors) or broad (many actors with moderate attention).
