# Plan 3 — Word Frequency & TF-IDF Shifts

> **Dataset:** 940 text-bearing messages from PressTV Telegram channel
> **Period:** April 6–14, 2026 (~8 days)
> **Objective:** Surface the vocabulary that distinguishes each phase of the 8-day period and track how the lexicon evolves.

---

## Goal

Identify which words are *distinctively important* in each time period — not just frequent, but uniquely characteristic. TF-IDF scoring penalizes words that appear everywhere (like "Iran" or "said") and rewards terms that spike in a specific window, revealing shifting focus and emerging narratives.

---

## Pipeline

### Step 1 — Preprocessing

```python
import re
import nltk
from nltk.corpus import stopwords

nltk.download("stopwords")
stop_words = set(stopwords.words("english"))

# Extend with domain-ubiquitous terms that add no signal
stop_words.update(["iran", "iranian", "says", "said", "also", "would", "us", "new"])

def clean_text(text):
    text = text.lower()
    text = re.sub(r"http\S+", "", text)           # URLs
    text = re.sub(r"[^\w\s]", "", text)            # punctuation
    text = re.sub(r"\d+", "", text)                # numbers
    tokens = text.split()
    tokens = [t for t in tokens if t not in stop_words and len(t) > 2]
    return " ".join(tokens)

df_text["clean_text"] = df_text["text"].apply(clean_text)
```

### Step 2 — Period Segmentation

Split the 8-day range into 4 equal bins (~2 days each). Concatenate all message texts within each bin into a single pseudo-document.

```python
df_text["period"] = pd.cut(
    df_text["timestamp"],
    bins=4,
    labels=["Apr 6–8", "Apr 8–10", "Apr 10–12", "Apr 12–14"],
)

pseudo_docs = df_text.groupby("period")["clean_text"].apply(" ".join).tolist()
period_labels = ["Apr 6–8", "Apr 8–10", "Apr 10–12", "Apr 12–14"]
```

### Step 3 — TF-IDF Computation

```python
from sklearn.feature_extraction.text import TfidfVectorizer

tfidf = TfidfVectorizer(max_features=500, ngram_range=(1, 1))
tfidf_matrix = tfidf.fit_transform(pseudo_docs)
feature_names = tfidf.get_feature_names_out()

# Extract top 20 terms per period
import numpy as np

for i, label in enumerate(period_labels):
    scores = tfidf_matrix[i].toarray().flatten()
    top_indices = scores.argsort()[-20:][::-1]
    top_terms = [(feature_names[j], round(scores[j], 4)) for j in top_indices]
    print(f"\n{label}: {top_terms[:10]}")
```

### Step 4 — Delta Analysis

For each term, compute the change in TF-IDF rank between adjacent periods. Flag terms with the largest rank jumps (emerging topics) and drops (fading topics).

```python
rank_dfs = []
for i, label in enumerate(period_labels):
    scores = tfidf_matrix[i].toarray().flatten()
    ranked = pd.Series(scores, index=feature_names).rank(ascending=False)
    rank_dfs.append(ranked.rename(label))

rank_df = pd.concat(rank_dfs, axis=1)

# Compute rank change between first and last period
rank_df["delta"] = rank_df[period_labels[0]] - rank_df[period_labels[-1]]
# Positive delta = term rose in importance (lower rank number = higher importance)

risers = rank_df.nlargest(15, "delta")   # Terms that became MORE important
fallers = rank_df.nsmallest(15, "delta")  # Terms that became LESS important
```

---

## Visualization

### Primary — Bump Chart (Rank Trajectory)

- Each line = one word.
- X-axis = time period (4 columns).
- Y-axis = TF-IDF rank (inverted: rank 1 at top).
- Highlight the top 10 movers (5 risers in green, 5 fallers in red).
- Label endpoints with the word.
- Gray out all other lines for context.

This is the most analytically valuable chart — it shows *trajectory*, not just snapshots.

### Secondary — Faceted Horizontal Bar Charts

- One panel per period (4 panels arranged horizontally or in a 2×2 grid).
- Each panel shows the top 15 TF-IDF terms as horizontal bars.
- Color-code bars:
  - **Green** = term is new (didn't appear in the prior period's top 30).
  - **Blue** = recurring term.
  - **Red** = term that was in the prior period's top 15 but dropped out.

### Tertiary — Word Clouds (Supplementary Only)

- One word cloud per period, sized by TF-IDF score (not raw frequency).
- Use these decoratively alongside the bar charts, not as the primary analytical view.
- Word clouds are poor for precise comparison but good for quick visual impressions.

### Anti-Pattern

Avoid standard frequency-based word clouds as the sole visualization. They are visually noisy, hard to compare across periods, and overweight common words even after stopword removal.

---

## Libraries

```
scikit-learn (TfidfVectorizer)
nltk (stopwords, tokenization)
pandas
matplotlib / plotly
wordcloud (optional, for supplementary clouds)
```

---

## Estimated Complexity

**Low** — Entirely count-based computation, runs in seconds. The effort is in tuning the stopword list and choosing meaningful period boundaries.

---

## Expected Insights

- Which geopolitical terms emerge mid-period (e.g., "Islamabad", "negotiations" appearing after talks begin).
- Which terms fade (e.g., "strikes" or "threat" declining if the narrative shifts to diplomacy).
- Whether PressTV's vocabulary is narrow and repetitive or evolves meaningfully across the 8-day window.
- The speed of vocabulary pivot — do new terms appear gradually or in sharp jumps?
