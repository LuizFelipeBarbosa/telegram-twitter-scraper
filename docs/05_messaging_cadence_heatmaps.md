# Plan 5 — Messaging Cadence & Volume Heatmaps

> **Dataset:** 1,200 messages (full dataset including media-only) from PressTV Telegram channel
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Reveal posting patterns — when does PressTV publish most actively? Do posting spikes correlate with real-world events?

---

## Goal

This is the fastest analysis to run and should be done first. It uses only timestamps and the `has_media` flag — no NLP required. The result orients you in the data before running heavier analyses, and can reveal whether PressTV operates on a predictable editorial schedule or reactively to events.

---

## Pipeline

### Step 1 — Timestamp Parsing

```python
import pandas as pd

df = pd.read_csv("filename.csv", index_col=0)
df["timestamp"] = pd.to_datetime(df["timestamp"])
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

A continuous heatmap strip showing every hour of the 8-day period:

- **Rows:** One per day (8 rows).
- **Columns:** 24 columns (one per hour, 00:00–23:00 UTC).
- **Cell color:** Message count (sequential colormap: light → dark).
- **Annotations:** Mark the top 3 spike cells with event labels.

```python
import seaborn as sns
import matplotlib.pyplot as plt

pivot = df.groupby(["date", "hour"]).size().unstack(fill_value=0)
fig, ax = plt.subplots(figsize=(16, 5))
sns.heatmap(pivot, cmap="YlOrRd", linewidths=0.5, ax=ax, annot=True, fmt="d")
ax.set_xlabel("Hour (UTC)")
ax.set_ylabel("Date")
ax.set_title("PressTV Telegram — Hourly Message Volume")
```

### Secondary — Structural Rhythm Heatmap

Averaged across all days to reveal the channel's baseline posting schedule:

- **Rows:** Day of week (Mon–Sun, 7 rows).
- **Columns:** Hour of day (24 columns).
- **Cell color:** Average message count.

This separates the structural rhythm from event-driven spikes. If PressTV publishes on a schedule, it will show as consistent hot bands. If purely reactive, the pattern will be noisy.

### Tertiary — Volume + Media Overlay Chart

- **Bars:** Hourly message count (left y-axis).
- **Line:** Percentage of messages with media (right y-axis).
- **X-axis:** Continuous datetime.
- **Divergence insight:** Hours where media % spikes above the baseline (~63% overall) likely indicate breaking visual news. Hours where text-only dominates may indicate opinion/analysis pieces.

### Bonus — Daily Summary Table

A simple table alongside the visuals:

| Date | Total Messages | With Media | Text-Only | Peak Hour | Peak Count |
|------|---------------|------------|-----------|-----------|------------|
| Apr 6 | ... | ... | ... | ... | ... |

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

- Whether PressTV operates on a fixed schedule (e.g., heavy posting during business hours in Tehran, quiet overnight) or posts reactively.
- The top 3–5 posting spikes and what events triggered them.
- Whether media-heavy bursts (photos, videos) correlate with breaking news vs. planned editorial content.
- Whether weekend posting differs from weekday posting (relevant for understanding editorial staffing).
