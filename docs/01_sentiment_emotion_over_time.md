# Plan 1 — Sentiment & Emotion Over Time

> **Dataset:** 940 text-bearing messages from PressTV Telegram channel
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Reveal how the emotional arc of PressTV's messaging shifts hour-by-hour and day-by-day in response to geopolitical events.

---

## Goal

Track sentiment polarity and fine-grained emotion across the 8-day window. Spikes and dips in sentiment should correlate with real-world events (strikes, negotiations, UN votes, threats), making this a narrative-level view of how PressTV modulates its tone.

---

## Pipeline

### Step 1 — Preprocessing

- Drop the 260 null-text rows.
- Parse `timestamp` into `datetime`, extract `date` and `hour` columns.
- Strip URLs, emoji sequences, and trailing `\n---` delimiters from text.

### Step 2 — Sentiment Scoring

Run each message through a pretrained transformer sentiment model. Two recommended options:

| Model | Type | Output | Speed |
|-------|------|--------|-------|
| `cardiffnlp/twitter-roberta-base-sentiment-latest` | Transformer (HuggingFace) | `negative / neutral / positive` with confidence scores | ~5 min on CPU |
| VADER (`vaderSentiment`) | Rule-based lexicon | Compound score (−1 to +1) | Seconds |

**Recommendation:** Use the RoBERTa model for accuracy on geopolitical language. VADER tends to misread formal news register and sarcasm.

```python
from transformers import pipeline

sentiment_pipe = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    top_k=None,
)

df_text["sentiment_scores"] = df_text["text"].apply(lambda t: sentiment_pipe(t[:512]))
```

### Step 3 — Emotion Classification

Use `j-hartmann/emotion-english-distilroberta-base` for fine-grained emotions across 7 categories: `anger`, `disgust`, `fear`, `joy`, `sadness`, `surprise`, `neutral`.

```python
emotion_pipe = pipeline(
    "text-classification",
    model="j-hartmann/emotion-english-distilroberta-base",
    top_k=None,
)

df_text["emotions"] = df_text["text"].apply(lambda t: emotion_pipe(t[:512]))
```

### Step 4 — Aggregation

- Group by 6-hour or 12-hour windows using `pd.Grouper(key="timestamp", freq="6h")`.
- Compute mean sentiment compound score per window.
- Compute emotion proportions per window (count of each dominant emotion ÷ total messages in window).

### Step 5 — Event Annotation

Manually identify 5–10 key events from the date range by scanning high-volume or high-sentiment-shift periods. Examples from the dataset:

- Iran–US peace talks begin in Islamabad
- Trump threatens Iranian infrastructure
- Israeli ground invasion of southern Lebanon
- Iraqi presidential election voting
- Iranian media rejects rumors of officials' travel

Tag each with a timestamp for overlay on the chart.

---

## Visualization

### Primary — Dual-Axis Time Series

- **Left y-axis:** Rolling mean sentiment score (−1 to +1), plotted as a smoothed line with a 95% confidence band.
- **Right y-axis:** Stacked area chart of emotion proportions (anger, fear, joy, sadness, etc.).
- **X-axis:** Datetime (full 8-day range).
- **Overlay:** Vertical dashed lines at event timestamps with rotated annotation labels.

### Secondary — Emotion Heatmap (Small Multiples)

- One row per day (8 rows).
- Columns for each hour (24 columns).
- Cell color = dominant emotion for that hour.
- Reveals intra-day emotional rhythms and event-driven disruptions.

### Styling Notes

- Use a diverging color palette for sentiment (red → white → green).
- Use a categorical palette for emotions (e.g., anger=crimson, fear=dark orange, joy=gold, sadness=steel blue, neutral=gray).
- Annotate the single most extreme sentiment hour with a callout box showing the triggering message text.

---

## Libraries

```
transformers
pandas
matplotlib / plotly
seaborn (for heatmap)
```

---

## Estimated Complexity

**Medium** — Model inference is the bottleneck (~5 min on CPU for 940 texts with each model). Aggregation and plotting are fast.

---

## Expected Insights

- Whether PressTV maintains a consistent negative tone or modulates strategically around events.
- Which emotions dominate overall (likely anger and fear given the geopolitical context) and whether there are surprise joy/triumph spikes (e.g., after successful negotiations).
- Whether sentiment leads or lags real-world events — does the channel anticipate or react?
