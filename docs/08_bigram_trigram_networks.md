# Plan 8 — Bigram / Trigram Phrase Networks

> **Dataset:** 940 text-bearing messages from PressTV Telegram channel
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Expose recurring talking points and propaganda phrases by mapping which words consistently appear together.

---

## Goal

Identify statistically significant multi-word phrases that reveal PressTV's recurring talking points, editorial templates, and propaganda patterns. Unlike single-word frequency analysis (Plan 3), bigram/trigram networks capture *phrase-level* patterns — "Zionist regime", "resistance axis", "nuclear deal" — that carry meaning beyond their individual words.

---

## Pipeline

### Step 1 — Preprocessing

```python
import re
import nltk
from nltk.corpus import stopwords

nltk.download("stopwords")
nltk.download("punkt")
stop_words = set(stopwords.words("english"))

def preprocess(text):
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\d+", "", text)
    tokens = nltk.word_tokenize(text)
    tokens = [t for t in tokens if t not in stop_words and len(t) > 2]
    return tokens

df_text["tokens"] = df_text["text"].apply(preprocess)
```

### Step 2 — N-gram Extraction with PMI Scoring

Use NLTK's collocation finders to identify statistically significant phrases using Pointwise Mutual Information (PMI). PMI measures how much more likely two words are to appear together than by chance.

```python
from nltk.collocations import BigramCollocationFinder, TrigramCollocationFinder
from nltk.metrics import BigramAssocMeasures, TrigramAssocMeasures

# Flatten all tokens
all_tokens = [token for tokens in df_text["tokens"] for token in tokens]

# Bigrams
bigram_finder = BigramCollocationFinder.from_words(all_tokens)
bigram_finder.apply_freq_filter(5)  # Must appear 5+ times
bigram_pmi = bigram_finder.score_ngrams(BigramAssocMeasures.pmi)

# Trigrams
trigram_finder = TrigramCollocationFinder.from_words(all_tokens)
trigram_finder.apply_freq_filter(3)  # Must appear 3+ times
trigram_pmi = trigram_finder.score_ngrams(TrigramAssocMeasures.pmi)
```

### Step 3 — Filtering

Keep only bigrams with PMI > 3.0 (strong association) and frequency > 5. This eliminates noise while preserving meaningful phrases.

```python
# Get both PMI and frequency for filtering
bigram_freq = dict(bigram_finder.ngram_fd)

significant_bigrams = [
    (bigram, pmi, bigram_freq.get(bigram, 0))
    for bigram, pmi in bigram_pmi
    if pmi > 3.0 and bigram_freq.get(bigram, 0) >= 5
]

significant_bigrams.sort(key=lambda x: x[1], reverse=True)
```

### Step 4 — Graph Construction

Build a directed graph where edges represent sequential word relationships in significant bigrams:

```python
import networkx as nx

G = nx.DiGraph()

for (w1, w2), pmi, freq in significant_bigrams:
    G.add_node(w1)
    G.add_node(w2)
    G.add_edge(w1, w2, weight=freq, pmi=pmi)

# Set node size based on total degree (connections)
for node in G.nodes():
    G.nodes[node]["degree"] = G.degree(node)
    # Also track total frequency across all bigrams containing this word
    G.nodes[node]["total_freq"] = sum(
        d["weight"] for _, _, d in G.edges(node, data=True)
    ) + sum(
        d["weight"] for _, _, d in G.in_edges(node, data=True)
    )
```

### Step 5 — Temporal Split

Split into two halves and compare which phrases are unique to each period:

```python
midpoint = df_text["timestamp"].median()

first_half_tokens = [
    t for tokens, ts in zip(df_text["tokens"], df_text["timestamp"])
    for t in tokens if ts <= midpoint
]
second_half_tokens = [
    t for tokens, ts in zip(df_text["tokens"], df_text["timestamp"])
    for t in tokens if ts > midpoint
]

# Repeat bigram extraction for each half
bf_first = BigramCollocationFinder.from_words(first_half_tokens)
bf_first.apply_freq_filter(3)
bf_second = BigramCollocationFinder.from_words(second_half_tokens)
bf_second.apply_freq_filter(3)

# Find bigrams unique to each half
first_set = set(b for b, _ in bf_first.score_ngrams(BigramAssocMeasures.pmi)[:50])
second_set = set(b for b, _ in bf_second.score_ngrams(BigramAssocMeasures.pmi)[:50])

new_phrases = second_set - first_set      # Emerged in second half
dropped_phrases = first_set - second_set   # Disappeared in second half
```

---

## Visualization

### Primary — Directed Phrase Network Graph

- **Nodes:** Individual words. Sized by total degree (number of bigram connections). Colored by word category — manually assign or cluster by graph community.
- **Edges:** Directed arrows from first word to second word in each bigram. Thickness proportional to frequency. Label with the frequency count.
- **Layout:** Force-directed (`spring_layout`) with repulsion tuned to prevent overlap.
- **Clusters:** Words that participate in many shared bigrams form visible clusters. Expected clusters: a "nuclear" hub (nuclear → deal, nuclear → weapons, nuclear → program), a "military" hub, a "diplomatic" hub.

```python
from pyvis.network import Network

net = Network(height="700px", width="100%", directed=True)
for node, data in G.nodes(data=True):
    net.add_node(node, size=data["degree"] * 5, label=node)
for u, v, data in G.edges(data=True):
    net.add_edge(u, v, value=data["weight"], title=f"PMI: {data['pmi']:.2f}")
net.show("bigram_network.html")
```

### Secondary — Top Bigrams Ranked Bar Chart

- Horizontal bars for the top 30 bigrams by PMI.
- Bar length = PMI score.
- Annotate each bar with the raw frequency count.
- Color bars by whether the bigram contains a named entity (useful for distinguishing proper-noun phrases from generic collocations).

### Tertiary — Temporal Comparison (Side-by-Side Networks)

Two network graphs side by side:

- **Left:** First half (Apr 6–10) bigram network.
- **Right:** Second half (Apr 10–14) bigram network.
- Highlight new phrases (green edges) and disappeared phrases (red edges in left graph, absent in right).
- Reveals how the talking-point vocabulary evolved.

### Quaternary — Trigram Table

Since trigrams are harder to visualize as networks, present them as a ranked table:

| Rank | Trigram | PMI | Frequency |
|------|---------|-----|-----------|
| 1 | ... | ... | ... |

---

## Libraries

```
nltk (collocations, BigramAssocMeasures)
networkx
pyvis or plotly
pandas
matplotlib
```

---

## Estimated Complexity

**Low-Medium** — PMI computation is fast (sub-second). The main effort is in graph layout tuning to make the network readable and in interpreting the temporal split results.

---

## Expected Insights

- PressTV's signature phrases — compound terms that recur as editorial building blocks (e.g., "Zionist regime", "resistance axis", "nuclear deal", "illegal sanctions").
- Phrase clusters revealing thematic vocabulary neighborhoods.
- Whether new phrases emerge in the second half (indicating narrative evolution) or the vocabulary remains static (indicating template-driven messaging).
- High-PMI, low-frequency bigrams that may indicate specialized or coded language.
- Comparison with generic news language — which phrases are uniquely PressTV vs. standard newswire?
