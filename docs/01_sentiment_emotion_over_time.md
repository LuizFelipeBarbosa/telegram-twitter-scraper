# Plan 1 — Sentiment & Emotion Over Time

> **Dataset:** text-bearing messages exported by a channel-specific pipeline notebook (e.g. `notebooks/pipeline_<slug>.ipynb` writing to `notebooks/messages.csv` or `CHANNEL_RESULTS[slug]["df_text"]` in the multi-channel pipeline).
> **Period:** the window covered by the channel's message export — typically a few days to a few weeks; all temporal aggregations below scale to whatever range is present in the data.
> **Objective:** Reveal how the emotional arc of the target channel's messaging shifts hour-by-hour and day-by-day in response to real-world events.
>
> _Illustrative sample values in this plan are drawn from a prior PressTV run (940 text-bearing messages, April 6–14 2026, ~8 days). Substitute your own channel's counts and date range when applying the plan._

---

## Goal

Track sentiment polarity and fine-grained emotion across the full export window. Spikes and dips in sentiment should correlate with real-world events (strikes, negotiations, UN votes, protests, elections, press conferences), making this a narrative-level view of how the channel modulates its tone.

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

Manually identify 5–10 key events from the date range by scanning high-volume or high-sentiment-shift periods. The events you annotate will depend on the channel's beat — for a geopolitical news channel they might be strikes, ceasefire announcements, or diplomatic meetings; for a domestic politics channel they might be votes, press conferences, or protests.

Example annotations from a prior PressTV run (replace with the events relevant to your channel and window):

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
- **X-axis:** Datetime (full export window).
- **Overlay:** Vertical dashed lines at event timestamps with rotated annotation labels.

### Secondary — Emotion Heatmap (Small Multiples)

- One row per day in the export window.
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

**Medium** — Model inference is the bottleneck (roughly ~5 min on CPU per ~1,000 texts for each of the sentiment and emotion models; scale linearly with corpus size). Aggregation and plotting are fast.

---

## Expected Insights

- Whether the channel maintains a consistent emotional baseline or modulates strategically around events.
- Which emotions dominate overall (e.g., anger and fear for conflict-reporting channels; joy and surprise for cultural/entertainment channels) and whether there are counter-direction spikes around specific events.
- Whether sentiment leads or lags real-world events — does the channel anticipate or react?
- How the channel's emotional register compares to other channels run through the same pipeline (cross-channel comparison becomes possible once each `CHANNEL_RESULTS[slug]` carries a sentiment timeline of the same shape).
