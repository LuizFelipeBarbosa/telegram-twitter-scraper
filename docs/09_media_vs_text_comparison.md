# Plan 9 — Comparative Analysis: Media vs. Text-Only Messages

> **Implementation status:** Implemented in `src/telegram_scraper/analysis/media_vs_text.py` and surfaced as **Section 14** in `notebooks/pipeline.ipynb`.
>
> **Dataset:** 1,200 messages from PressTV Telegram channel (757 with media, 443 text-only)
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Analyze whether media-accompanied messages differ systematically in content, timing, and framing from text-only messages.

---

## Goal

With 63% of messages carrying media (photos, videos, documents), PressTV heavily leverages visual content. This analysis asks whether media messages are substantively different from text-only messages — do they cover different topics, use different emotional registers, appear at different times, and employ different rhetorical strategies? The answer reveals whether media is decorative or structurally meaningful in PressTV's editorial strategy.

---

## Pipeline

### Step 1 — Segmentation

```python
df_media = df[df["has_media"] == True].copy()
df_text_only = df[df["has_media"] == False].copy()

# Among text-bearing messages only (exclude media-only posts with no text)
df_media_with_text = df_media[df_media["text"].notna()].copy()
df_text_only_with_text = df_text_only[df_text_only["text"].notna()].copy()

print(f"Media messages: {len(df_media)} ({len(df_media_with_text)} with text)")
print(f"Text-only messages: {len(df_text_only)} ({len(df_text_only_with_text)} with text)")
```

### Step 2 — Upstream Analysis Replication

Re-run key analyses from prior plans separately for each segment:

| Analysis | Source Plan | Rerun For |
|----------|-----------|-----------|
| Sentiment scoring | Plan 1 | Media vs. text-only |
| Topic assignment | Plan 2 | Media vs. text-only |
| Top TF-IDF terms | Plan 3 | Media vs. text-only |
| Entity extraction | Plan 4 | Media vs. text-only |
| Rhetorical frame | Plan 6 | Media vs. text-only |

If prior plans have already been completed, merge their results into the segmented DataFrames rather than recomputing.

### Step 3 — Statistical Comparison

For each metric, run a two-sample test to check for significant differences:

```python
from scipy.stats import mannwhitneyu, chi2_contingency

# Continuous variables: Mann-Whitney U
for metric in ["sentiment_score", "text_length"]:
    stat, p = mannwhitneyu(
        df_media_with_text[metric],
        df_text_only_with_text[metric],
        alternative="two-sided"
    )
    print(f"{metric}: U={stat:.0f}, p={p:.4f}")

# Categorical variables: Chi-square
contingency = pd.crosstab(
    df_with_results["has_media"],
    df_with_results["dominant_topic"]
)
chi2, p, dof, expected = chi2_contingency(contingency)
print(f"Topic × Media: χ²={chi2:.2f}, p={p:.4f}")
```

### Step 4 — Timing Analysis

Compare posting-hour distributions between media and text-only messages:

```python
media_hours = df_media["hour"].value_counts(normalize=True).sort_index()
text_hours = df_text_only["hour"].value_counts(normalize=True).sort_index()
```

### Step 5 — Text Length Comparison

```python
df["text_length"] = df["text"].str.len().fillna(0)

media_lengths = df_media_with_text["text_length"]
text_only_lengths = df_text_only_with_text["text_length"]
```

---

## Visualization

### Primary — Paired Violin Plots

One pair per metric, left = media, right = text-only. Shows full distribution shape, not just means.

```python
import seaborn as sns
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Sentiment
sns.violinplot(data=df_with_results, x="has_media", y="sentiment_score", ax=axes[0])
axes[0].set_title("Sentiment Distribution")

# Text Length
sns.violinplot(data=df_with_results, x="has_media", y="text_length", ax=axes[1])
axes[1].set_title("Text Length Distribution")

# Emotion (one violin per emotion category, faceted)
# ...
```

### Secondary — Overlaid Density Curves (Posting Hour)

- Two KDE curves on the same axes.
- X-axis = hour of day (0–23).
- Y-axis = density.
- Blue curve = media messages, orange curve = text-only.
- Shaded areas under each curve.
- Reveals whether media posts cluster at different times (e.g., breaking news hours) vs. text-only posts (e.g., analysis/opinion pieces published during editorial hours).

### Tertiary — Grouped Topic Bar Chart

- One group per topic (from Plan 2).
- Two bars per group: media messages (blue) and text-only (orange).
- Reveals which topics get visual treatment and which remain text-only.
- Expected: military/breaking news topics skew media-heavy; diplomatic/analysis topics skew text-only.

### Quaternary — Rhetoric Frame Comparison

Stacked bar chart or mosaic plot:

- X-axis = rhetorical category (from Plan 6).
- Y-axis = message count.
- Stacked by media (blue) vs. text-only (orange).
- Reveals whether certain persuasion strategies are systematically paired with visuals.

### Summary Dashboard

Combine all four visualizations into a single 2×2 dashboard panel with a shared title: "Media vs. Text-Only: How Visual Content Shapes PressTV's Messaging"

---

## Libraries

```
pandas
scipy.stats
seaborn
matplotlib
plotly (optional, for interactive versions)
```

---

## Estimated Complexity

**Medium** — The statistical tests and plotting are straightforward. The main cost is re-running upstream analyses (sentiment, topics, rhetoric) for each segment, or merging pre-computed results. If prior plans are already complete, this plan is mostly aggregation and visualization.

---

## Dependencies on Prior Plans

This plan builds on results from earlier analyses. Minimum requirements:

| Dependency | Required For | Can Skip? |
|-----------|-------------|-----------|
| Plan 1 (Sentiment) | Sentiment violin plot | Yes — omit that panel |
| Plan 2 (Topics) | Topic bar chart | Yes — omit that panel |
| Plan 6 (Rhetoric) | Rhetoric comparison | Yes — omit that panel |
| None | Timing + text length | No — these use raw data |

Even without the NLP-dependent panels, the timing and text length comparisons are independently valuable.

---

## Expected Insights

- Whether media messages are shorter (quick visual dispatches) or longer (photo essays with captions).
- Whether media messages have stronger negative sentiment (breaking bad news with photos) or more neutral sentiment (factual photo reporting).
- Which topics PressTV always illustrates vs. leaves as text — reveals editorial priorities for visual storytelling.
- Whether media messages cluster at specific hours (e.g., breaking news during waking hours in Iran/Middle East) while text-only posts fill other times.
- Whether certain rhetorical frames (e.g., victimhood/injustice) are systematically paired with images — a known propaganda technique of using emotional visuals to reinforce narrative frames.
