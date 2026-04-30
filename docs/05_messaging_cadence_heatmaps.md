# Plan 5 — Messaging Cadence & Volume Heatmaps

> **Dataset:** the full message export (including media-only posts) produced by a channel-specific pipeline notebook — `notebooks/pipeline_<slug>.ipynb` writing to `notebooks/messages.csv`, or `CHANNEL_RESULTS[slug]["df"]` in the multi-channel pipeline.
> **Period:** whatever window the export covers — a few days, a few weeks, or longer. Every aggregation below scales with the span.
> **Objective:** Reveal posting patterns — when does the target channel publish most actively, and do posting spikes correlate with real-world events?
>
> _Illustrative sample values in this plan are drawn from a prior PressTV run (1,200 messages, April 6–14 2026, ~8 days). Substitute your own channel's counts and window when applying the plan._

---

## Goal

This is the fastest analysis to run and should be done first. It uses only timestamps and the `has_media` flag — no NLP required. The result orients you in the data before running heavier analyses, and can reveal whether the channel operates on a predictable editorial schedule or reactively to events.

---

## Pipeline

### Step 1 — Timestamp Parsing

```python
import pandas as pd

# Load either the per-channel CSV (e.g. notebooks/messages.csv) or reuse
# CHANNEL_RESULTS[slug]["df"] from the in-memory multi-channel pipeline.
df = pd.read_csv("notebooks/messages.csv", index_col=0)

df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df["date"] = df["timestamp"].dt.date
df["hour"] = df["timestamp"].dt.hour
df["day_of_week"] = df["timestamp"].dt.dayofweek  # 0=Mon, 6=Sun
df["day_name"] = df["timestamp"].dt.day_name()
```

### Step 2 — Volume Aggregation

```python
# Messages per hour (continuous)
hourly_counts = df.set_index("timestamp").resample("1h").size().rename("msg_count")

# Messages per day
daily_counts = df.groupby("date").size().rename("msg_count")

# Day-of-week × hour-of-day matrix
dow_hour = df.groupby(["day_of_week", "hour"]).size().unstack(fill_value=0)
```

### Step 3 — Event Overlay

Identify the top 5 posting-volume spikes by finding hours with the highest message counts:

```python
top_spikes = hourly_counts.nlargest(10)
```

Cross-reference each spike with the messages posted during that hour. Read the text to identify the triggering event and create an annotation label.

### Step 4 — Media Ratio Analysis

```python
# Per-hour media ratio
media_hourly = df.set_index("timestamp").resample("1h").agg(
    total=("message_id", "size"),
    media_count=("has_media", "sum"),
)
media_hourly["media_pct"] = (media_hourly["media_count"] / media_hourly["total"] * 100).round(1)
```

---

## Visualization

### Primary — Calendar Strip Heatmap

A continuous heatmap strip showing every hour of the export window:

- **Rows:** One per day in the window.
- **Columns:** 24 columns (one per hour, 00:00–23:00 UTC).
- **Cell color:** Message count (sequential colormap: light → dark).
- **Annotations:** Mark the top 3 spike cells with event labels.

```python
import seaborn as sns
import matplotlib.pyplot as plt

CHANNEL_LABEL = "Channel X"  # e.g. "PressTV", "Behold Israel", "Times of Israel"

pivot = df.groupby(["date", "hour"]).size().unstack(fill_value=0)
fig, ax = plt.subplots(figsize=(16, max(3, 0.4 * len(pivot))))
sns.heatmap(pivot, cmap="YlOrRd", linewidths=0.5, ax=ax, annot=True, fmt="d")
ax.set_xlabel("Hour (UTC)")
ax.set_ylabel("Date")
ax.set_title(f"{CHANNEL_LABEL} Telegram — Hourly Message Volume")
```

### Secondary — Structural Rhythm Heatmap

Averaged across all days to reveal the channel's baseline posting schedule:

- **Rows:** Day of week (Mon–Sun, 7 rows).
- **Columns:** Hour of day (24 columns).
- **Cell color:** Average message count.

This separates the structural rhythm from event-driven spikes. If the channel publishes on a schedule, it will show as consistent hot bands. If purely reactive, the pattern will be noisy.

### Tertiary — Volume + Media Overlay Chart

- **Bars:** Hourly message count (left y-axis).
- **Line:** Percentage of messages with media (right y-axis), smoothed with a 6-to-12-hour rolling mean so sparse hours don't dominate.
- **Reference line:** Channel's overall media share (compute from `df["has_media"].mean()` — sample values so far: ~63% for PressTV, ~47% for Behold Israel).
- **X-axis:** Continuous datetime.
- **Divergence insight:** Hours where media % spikes above the channel's own baseline likely indicate breaking visual news. Hours where text-only dominates may indicate opinion / analysis / commentary.

### Bonus — Daily Summary Table

A simple table alongside the visuals:

| Date | Total Messages | With Media | Text-Only | Peak Hour | Peak Count |
|------|---------------|------------|-----------|-----------|------------|
| _(one row per day in the export window)_ | ... | ... | ... | ... | ... |

---

## Libraries

```
pandas
seaborn
matplotlib
calplot (optional, for GitHub-style calendar view)
```

---

## Estimated Complexity

**Low** — Pure aggregation, no NLP models needed. The entire analysis runs in under a second. Most effort goes into annotation and layout refinement.

---

## Expected Insights

- Whether the channel operates on a fixed schedule (e.g., heavy posting during business hours in its home timezone, quiet overnight) or posts reactively. The home timezone is a useful thing to note when writing the section up, since the apparent "working day" in UTC will shift depending on where the editorial team sits.
- The top 3–5 posting spikes and what events triggered them.
- Whether media-heavy bursts (photos, videos) correlate with breaking news vs. planned editorial content.
- Whether weekend posting differs from weekday posting (relevant for understanding editorial staffing).
- Cross-channel: plotting the daily-volume curves of several `CHANNEL_RESULTS[slug]` entries on the same axis exposes whether a shared event drives simultaneous spikes across the ecosystem or whether each channel has its own rhythm.
