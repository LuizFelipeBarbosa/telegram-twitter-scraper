# Plan 6 — Framing & Rhetoric Analysis

> **Dataset:** 940 text-bearing messages from PressTV Telegram channel
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Classify each message by its rhetorical strategy to reveal how PressTV constructs its narrative and how persuasion tactics shift over time.

---

## Goal

Move beyond *what* PressTV says to *how* it says it. Each message employs a rhetorical strategy — fear appeals, us-vs-them framing, authority citations, victimhood narratives. Mapping these across time reveals the persuasion architecture of a state-affiliated media channel during a period of geopolitical tension.

---

## Pipeline

### Step 1 — Taxonomy Definition

Define 8 rhetorical categories with clear descriptions for the zero-shot classifier:

| Category | Description | Example Signal Words |
|----------|-------------|---------------------|
| **Fear / Threat** | Warnings about attacks, destruction, danger to safety | "threaten", "strike", "destroy", "danger" |
| **Us-vs-Them / Othering** | Language pitting groups against each other | "regime", "enemy", "they want to", "against our" |
| **Call to Action** | Urging readers, nations, or groups to act | "must", "should", "urges", "demands" |
| **Victimhood / Injustice** | Portraying a group as wronged or suffering | "innocent", "civilians", "crime", "massacre" |
| **Authority Appeal** | Quoting officials, leaders, experts to lend credibility | "according to", "stated", "the minister said" |
| **Factual / Neutral** | Straight news reporting without emotional loading | Inverted pyramid structure, attribution |
| **Conspiracy / Suspicion** | Implying hidden agendas, cover-ups, manipulation | "reveals", "secret", "plot", "behind the scenes" |
| **Triumphalism / Strength** | Celebrating power, resilience, military capability | "powerful", "resistance", "victory", "capable" |

### Step 2 — Zero-Shot Classification

Use `facebook/bart-large-mnli` as the zero-shot classifier. Each message gets a probability distribution across all 8 categories.

```python
from transformers import pipeline

classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",
    device=-1,  # CPU; set to 0 for GPU
)

candidate_labels = [
    "fear and threat warning",
    "us versus them othering",
    "call to action",
    "victimhood and injustice",
    "authority appeal and official quote",
    "factual neutral reporting",
    "conspiracy and suspicion",
    "triumphalism and strength",
]

results = []
for text in df_text["text"]:
    result = classifier(text[:512], candidate_labels, multi_label=False)
    results.append({
        label: score
        for label, score in zip(result["labels"], result["scores"])
    })

rhetoric_df = pd.DataFrame(results)
```

### Step 3 — Thresholding and Assignment

```python
rhetoric_df["dominant_frame"] = rhetoric_df.idxmax(axis=1)
rhetoric_df["confidence"] = rhetoric_df.max(axis=1)

# Flag low-confidence assignments as ambiguous
rhetoric_df.loc[rhetoric_df["confidence"] < 0.35, "dominant_frame"] = "mixed/ambiguous"
```

### Step 4 — Temporal Aggregation

```python
rhetoric_df["timestamp"] = df_text["timestamp"].values

rhetoric_temporal = rhetoric_df.set_index("timestamp").resample("12h").agg({
    label: "mean" for label in candidate_labels
})

# Normalize to proportions per window
rhetoric_temporal = rhetoric_temporal.div(rhetoric_temporal.sum(axis=1), axis=0)
```

### Step 5 — Validation Sampling

Manually review 30–50 messages (stratified by category) to assess classification quality. Adjust candidate label descriptions if the classifier consistently misassigns a category.

---

## Visualization

### Primary — Stacked Area Chart (Rhetoric Over Time)

- **X-axis:** Datetime (12-hour windows across 8 days).
- **Y-axis:** Proportion (0–100%).
- **Bands:** One per rhetorical category, colored distinctively.
- **Reveals:** How persuasion tactics shift — e.g., does "fear/threat" dominate early when tensions are high, then give way to "authority appeal" as negotiations begin?

### Secondary — Sankey / Alluvial Diagram

- **Left column:** Dominant frames in the first half (Apr 6–10).
- **Right column:** Dominant frames in the second half (Apr 10–14).
- **Flows:** Message count flowing from one frame to another.
- **Reveals:** Narrative pivots — e.g., 40 messages classified as "fear/threat" in the first half shift to "call to action" in the second half.

### Tertiary — Example Gallery Dashboard

For each category, display the 3 highest-confidence messages as formatted quote cards in a grid:

- Card header = category name + confidence score.
- Card body = truncated message text (first 200 chars).
- Card footer = timestamp.
- Gives qualitative grounding to the quantitative charts.

### Quaternary — Rhetoric × Sentiment Cross-Tabulation

If Plan 1 (sentiment) has been completed, create a heatmap:
- Rows = rhetorical category.
- Columns = sentiment (negative, neutral, positive).
- Cell color = message count.
- Reveals which frames are emotionally charged vs. neutral.

---

## Libraries

```
transformers (pipeline zero-shot-classification)
pandas
plotly (stacked area, Sankey diagram)
matplotlib / seaborn (heatmaps)
```

---

## Estimated Complexity

**High** — Zero-shot classification with BART-large-MNLI is slow on CPU: ~3–5 seconds per message, or roughly 45–80 minutes for 940 messages. Mitigation strategies:

- **GPU:** Reduces to ~5 min total.
- **Batching:** The pipeline supports batch inference, reducing overhead.
- **Sampling:** Run on a 200-message random sample first to validate the taxonomy, then scale to the full dataset.
- **Alternative model:** `MoritzLaurer/deberta-v3-large-zeroshot-v2.0` is faster and often more accurate.

---

## Expected Insights

- The dominant rhetorical strategy overall (likely "authority appeal" given PressTV's heavy use of official quotes, or "us-vs-them" given the geopolitical context).
- Whether PressTV shifts tactics in response to events — e.g., pivoting from "fear/threat" to "triumphalism" after successful negotiations.
- The proportion of genuinely neutral reporting vs. emotionally loaded framing.
- Which rhetorical categories co-occur — does "victimhood" always pair with "us-vs-them"?
- How PressTV's persuasion architecture compares to other state media channels (if extended to multi-channel analysis later).
