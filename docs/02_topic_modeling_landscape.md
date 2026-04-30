# Plan 2 — Topic Modeling Landscape

> **Dataset:** text-bearing messages exported by a channel-specific pipeline notebook (e.g. `notebooks/pipeline_<slug>.ipynb` or `CHANNEL_RESULTS[slug]["df_text"]` from the multi-channel pipeline).
> **Period:** whatever window the export covers — the pipeline below adapts to the number of days present.
> **Objective:** Discover the latent themes the target channel focuses on and how they cluster — e.g., military threats, diplomacy, domestic politics, media/propaganda, humanitarian framing, cultural commentary, or whatever editorial beats are native to the channel.
>
> _Illustrative sample values in this plan are drawn from a prior PressTV run (940 text-bearing messages, April 6–14 2026, ~8 days). Substitute your own channel's counts and window when applying the plan._

---

## Goal

Use embedding-based topic modeling to map the thematic landscape of the channel. Each message becomes a point in 2D space, clustered by semantic similarity. The result is an interactive map where you can see what the channel talks about, how topics relate, and how topic focus drifts over the export window.

---

## Pipeline

### Step 1 — Preprocessing

- Lowercase all text.
- Remove URLs (`http\S+`), emoji sequences, and trailing `\n---` delimiters.
- Strip leading bullet/emoji markers (`🔴`, `🔺`, `📸`, etc.).
- Optionally lemmatize with spaCy to reduce vocabulary noise, though this is less critical for embedding-based approaches.

### Step 2 — Embedding

Use `sentence-transformers/all-MiniLM-L6-v2` to embed each message into a 384-dimensional vector.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(df_text["text"].tolist(), show_progress_bar=True)
```

**Alternative:** If you already have OpenAI embeddings from the notebook pipeline (Section 5 of the channel pipeline notebook — any `pipeline_<slug>.ipynb`), use those directly. They will be higher-dimensional (e.g., 1536-dim for `text-embedding-3-small`) but UMAP handles this well.

### Step 3 — Dimensionality Reduction

Project the high-dimensional embeddings into 2D using UMAP.

```python
import umap

reducer = umap.UMAP(
    n_components=2,
    n_neighbors=15,
    min_dist=0.1,
    metric="cosine",
    random_state=42,
)
coords_2d = reducer.fit_transform(embeddings)
```

**Tuning notes:**
- `n_neighbors=15` balances local and global structure for corpora on the order of ~1,000 points; drop to ~10 for smaller exports and raise toward ~30 for larger ones.
- `min_dist=0.1` allows tight clusters without excessive overlap.
- `metric="cosine"` is standard for text embeddings.

### Step 4 — Clustering

Use HDBSCAN to identify topic clusters without predefining K.

```python
import hdbscan

clusterer = hdbscan.HDBSCAN(
    min_cluster_size=15,
    min_samples=5,
    metric="euclidean",
    cluster_selection_method="eom",
)
labels = clusterer.fit_predict(coords_2d)
```

Expect roughly 5–12 clusters plus a noise cluster (label = −1) on a ~1,000-message export. Narrow-beat channels may collapse to only 1–3 clusters under default parameters — that is itself a finding, and in that case lower `min_cluster_size` and `umap_min_dist` (see the Behold Israel writeup for an example of the tuned parameters `min_cluster_size=8, min_samples=3, umap_neighbors=10, umap_min_dist=0.0`). Messages in the noise cluster are thematic outliers.

### Step 5 — Topic Labeling

For each cluster, extract the top 10 terms by c-TF-IDF (class-based TF-IDF):

```python
from sklearn.feature_extraction.text import TfidfVectorizer

for cluster_id in sorted(set(labels)):
    if cluster_id == -1:
        continue
    cluster_texts = df_text[labels == cluster_id]["text"].tolist()
    joined = " ".join(cluster_texts)
    # Fit TF-IDF on all clusters, extract top terms for this one
```

**Alternative (recommended):** Use BERTopic which wraps this entire pipeline:

```python
from bertopic import BERTopic

topic_model = BERTopic(
    embedding_model="all-MiniLM-L6-v2",
    umap_model=reducer,
    hdbscan_model=clusterer,
    nr_topics="auto",
)
topics, probs = topic_model.fit_transform(df_text["text"].tolist())
topic_model.get_topic_info()
```

Manually assign human-readable labels based on the top terms (e.g., cluster with "nuclear, deal, negotiations, talks" → "Diplomacy & Nuclear Negotiations"). The analysis module in `src/telegram_scraper/analysis/topics.py` exposes a `TOPIC_LABEL_OVERRIDES` configuration for pinning these names per channel.

### Step 6 — Temporal Layer

Add a date column to the scatter data. Optionally create an animated scatter (Plotly frames) where dots appear sequentially by timestamp, or simply color-code dots by date to see temporal drift within clusters.

---

## Visualization

### Primary — Interactive UMAP Scatter Plot

- Each dot = one message.
- Position = UMAP (x, y) coordinates.
- Color = topic cluster (categorical palette).
- Size = text length (longer messages = larger dots).
- Hover tooltip = truncated message text (first 100 chars) + timestamp + topic label.
- Built with Plotly for zoom/pan/hover interactivity.

### Secondary — Topic Prevalence Bar Chart

- Horizontal bars, one per topic.
- Bar length = number of messages in that topic.
- Ordered descending by prevalence.
- Color matches the scatter plot palette.
- Annotate each bar with the top 3 keywords.

### Tertiary — Topic Proportion Over Time (Stacked Area)

- X-axis = date (full export window).
- Y-axis = proportion of messages belonging to each topic.
- One colored band per topic.
- Reveals which themes rise and fall — e.g., does "military threats" spike mid-period while "diplomacy" grows toward the end?

---

## Libraries

```
sentence-transformers (or precomputed OpenAI embeddings)
umap-learn
hdbscan
bertopic (optional, wraps the above)
plotly
pandas
scikit-learn
```

---

## Estimated Complexity

**Medium-High** — Embedding is fast (~1 min), but UMAP + HDBSCAN hyperparameter tuning requires several iterations to get well-separated, interpretable clusters. BERTopic simplifies this significantly.

---

## Expected Insights

- The dominant themes the target channel covers during the export window (for a state-affiliated geopolitical channel this is often inter-state tensions, diplomacy, and military action; for a domestic-commentary channel it may be elections, protests, and policy debates).
- Whether topics form tight clusters (focused messaging) or a diffuse cloud (broad, unfocused coverage). A channel that collapses to a single dominant cluster even after tuning is telling you that its semantic field is narrow — that is the finding, not a modeling failure.
- How the thematic focus shifts day-to-day — does the channel pivot quickly between topics or sustain multi-day narratives?
- Which topics are thematically adjacent (e.g., "military threats" near "us-vs-them rhetoric") and which are isolated.
- Cross-channel: when the same embedding + clustering pipeline is applied to multiple channels, comparing the topic compositions of each `CHANNEL_RESULTS[slug]` reveals how differently framed outlets carve up the same news period.
