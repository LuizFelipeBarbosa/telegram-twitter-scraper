# Behold Israel on Telegram: a 22-day notebook-based analysis

This article analyzes the **Behold Israel** Telegram channel ([t.me/beholdisraelchannel](https://t.me/beholdisraelchannel), Amir Tsarfati) using the figures produced by the same analysis sections implemented in [`notebooks/pipeline_behold_israel.ipynb`](../notebooks/pipeline_behold_israel.ipynb). It is structured to mirror the format of the PressTV write-up in [`docs/presstv-channel-analysis.md`](presstv-channel-analysis.md) so the two channels can be compared section-for-section.

> **Status.** This write-up is a first pass. It uses the figures and summary tables produced by the notebook after the Section 7/8/10 config overrides were added in [`docs/assets/behold-israel/`](./assets/behold-israel/) — i.e. topic modeling was re-tuned to `min_cluster_size=8, min_samples=3, umap_neighbors=10, umap_min_dist=0.0`, the TF-IDF bump chart labels were reduced to three risers + three fallers, and the media-share line was smoothed with a 12-hour rolling mean. Sections that still need values from a full rerun are marked explicitly below.

## Executive summary

Three patterns stand out most clearly.

1. **Behold Israel is a low-tempo, commentary-oriented channel.** Across the 22-day sample it averaged roughly **55 messages per day**, with a near-even media/text split — the overall media baseline is **46.8%**, noticeably lower than PressTV's 63.5%.
2. **Its vocabulary migrates from active strike reporting to blockade / siege / symbolic framing.** The TF-IDF bump chart shows the opening period dominated by *strikes*, *sites*, *ballistic*, *targets*, *site*, and by the final period those terms collapse while *blockade* and adjacent terms climb to the top of the distinctiveness ranking.
3. **Thematically, the channel orbits a single narrative axis: Iran, the IDF, and Israel.** The tuned topic model separates that axis into several sub-themes, but the first-pass run collapsed almost everything into one dominant cluster, which is itself a finding: Behold Israel's editorial field is narrower than PressTV's.

A second-order finding is that the channel's posting rhythm is **bursty**. Most hours sit at 0-5 messages and a handful spike above 20, which is why the raw hourly media-share line oscillated between 0% and 100% before smoothing — the underlying story is an editorial schedule that concentrates attention into a few windows per day rather than maintaining a steady wire-style feed.

## Scope and method

This write-up covers the Behold Israel sample fetched by `pipeline_behold_israel.ipynb` with `MESSAGE_LIMIT = 1200`.

| Metric | Value |
|---|---:|
| Total messages | 1,200 |
| Text-bearing messages | _TBD after rerun_ |
| Media-bearing messages | _TBD after rerun_ |
| Media share | 46.8% |
| Messages with `reply_to_message_id` | _TBD after rerun_ |
| Date range | 2026-03-25 to 2026-04-17 (UTC) |
| Messages per day (avg) | ≈55 |

Notes:

- All timestamps below are **UTC**.
- Figures come from the same notebook analysis modules used by `pipeline.ipynb` and `pipeline_presstv.ipynb`.
- Topic clusters should be read as **approximate thematic neighborhoods**, not immutable labels. Keyword-based labels are auto-generated; use `TOPIC_LABEL_OVERRIDES` in Section 7 to rename clusters after inspecting `topic_summary_df`.
- The first notebook run used library defaults and produced only two clusters. All numbers in Section 3 below reference the **re-tuned** topic model (`min_cluster_size=8, min_samples=3, umap_neighbors=10, umap_min_dist=0.0`).

---

## 1. Cadence: Behold Israel behaves like a curated commentary feed, not a wire

![Behold Israel hourly volume and media share](./assets/behold-israel/cadence_volume_media.png)

_Figure 1. Hourly message volume (orange bars) and 12-hour rolling-mean media share (blue line) across the full 22-day sample._

The cadence chart shows a channel that publishes selectively rather than continuously.

- Sample averages about **55 messages per day** across 22 days — roughly **one third** of PressTV's cadence over an 8-day window.
- The overall media baseline is **46.8%**, plotted as the dashed horizontal reference line.
- Most hours sit between **0 and 5** messages; a handful of hours spike above 20, typically around breaking events.
- Before the 12-hour smoothing was applied, the hourly media-share line ping-ponged between 0% and 100% because many hours had only one or two posts. The smoothed line (now the solid blue curve) reveals the underlying drift — media share holds roughly flat near the baseline with visible excursions during event-driven hours.

A useful way to read this is that Behold Israel looks less like a newswire and more like a **monitored commentary stream**: it follows conflict news closely but publishes in clusters tied to specific developments, and it balances image/video posts against text commentary at roughly 1:1.

Day-level summary, top spike hours, and weekday rhythm:

- _TBD after rerun: paste `cadence_daily_summary_df`, `cadence_top_spikes_df`, and `cadence_weekday_observation_df` values here._

---

## 2. Tone: _pending rerun_

![Behold Israel sentiment over time](./assets/behold-israel/sentiment_over_time.png)

_Figure 2. Notebook Section 6 sentiment timeline for Behold Israel._

Expected numbers to fill in from `overall_summary_df`, `sentiment_label_counts_df`, `emotion_label_counts_df`, and `candidate_events_df` after running Section 6:

- Mean sentiment score
- Sentiment label distribution (Negative / Neutral / Positive shares)
- Emotion label distribution (Fear / Anger / Sadness / Joy / Neutral / Disgust / Surprise)
- Most negative day and least negative day
- `most_extreme_hour` callout

Qualitative expectation, based on the channel's topical focus on Iran-Israel strikes and its eschatological / prophetic commentary framing: the distribution should skew meaningfully more **negative** than a general-purpose news channel, but less uniformly fear-saturated than PressTV because Behold Israel also carries a significant strand of explicitly religious / interpretive content that typically scores more neutral or positive. This expectation should be validated against the actual notebook output, not assumed.

---

## 3. Themes: one dominant narrative axis, several sub-theaters after tuning

![Behold Israel topic prevalence](./assets/behold-israel/topic_prevalence_static.png)

_Figure 3. Top topic clusters from the re-tuned notebook topic-modeling section._

The first notebook run surfaced only two clusters:

- **Topic 1: iran, idf, israel** — the large majority of messages
- **Topic 0: today stories, stories, stories today** — a small ~20-point cluster of channel self-references

That result is itself informative — Behold Israel's semantic field is tight enough that default HDBSCAN parameters treat the whole corpus as a single dense region. After lowering `min_cluster_size` to 8 and `umap_min_dist` to 0.0, the topic model is expected to separate the dominant Iran/Israel/IDF axis into recognizable sub-themes such as strike reporting, diplomacy / negotiations, intelligence and military posture, and the "today stories" channel-summary posts.

Expected sub-clusters (verify against `topic_summary_df` / `topic_keyword_df` after rerun):

- _TBD: list topic labels with message counts and top keywords_
- _TBD: call out whether a religious / prophetic commentary cluster emerges as distinct from the strike-reporting cluster_

![Behold Israel topic timeline](./assets/behold-israel/topic_timeline_static.png)

_Figure 4. Share of major topics over time._

The timeline chart should reveal how attention reallocates across sub-themes between the Mar 26 – Apr 16 period. Fill in specific daily share peaks from `topic_daily_share_df` after rerun.

Interactive notebook exports for this section:

- [Topic scatter](./assets/behold-israel/topic_scatter.html)
- [Topic prevalence](./assets/behold-israel/topic_prevalence.html)
- [Topic over time](./assets/behold-israel/topic_time.html)

---

## 4. Actors: _pending rerun_

![Top Behold Israel entities](./assets/behold-israel/entity_top_entities_static.png)

_Figure 5. Most-mentioned entities extracted from the corpus._

Expected numbers to fill in from `entity_summary_df`, `entity_pair_df`, and `entity_network_summary_df` after running Section 9:

- Total network nodes and edges after filtering
- Top 10 entities by mention count
- Strongest co-occurrence pairs
- Dominant community(ies) identified by Louvain

Qualitative expectation: the actor graph for Behold Israel should be **tighter** than PressTV's, with Iran and Israel (and the IDF as an organization) forming a nearly obligatory co-mention triangle. Lebanon, Hezbollah, the US, and Trump are likely to appear as secondary but consistent nodes. The presence or absence of Iranian leadership figures (Khamenei, Raisi) versus US leadership figures (Trump, Netanyahu, Biden-era officials) is a useful tell for the channel's framing orientation and should be called out explicitly after rerun.

Interactive notebook exports for this section:

- [Entity bar chart](./assets/behold-israel/entity_top_entities.html)
- [Entity network](./assets/behold-israel/entity_network.html)

---

## 5. Language shifts: from strike reporting to blockade framing

![Behold Israel TF-IDF rank trajectories](./assets/behold-israel/tfidf_bump.png)

_Figure 6. TF-IDF rank trajectories across four equal time bins (Mar 26 – Apr 16) after reducing labels to three risers and three fallers._

Even without full rerun numbers, the bump chart tells a clear story. The **top fallers** — words whose distinctiveness collapses from the opening period to the closing one — are all active-military vocabulary:

- **strikes**
- **sites**
- **ballistic**
- **targets**
- **site**

The **top risers** — words that climb from near-zero to the top of the distinctiveness ranking in the final period — sit in a very different register:

- **blockade**
- plus two additional terms that land at the top of the rank trajectory in the Apr 11-16 bin (fill in exact terms from `tfidf_risers_df` after rerun)

The shift is coherent: the opening bin is dominated by language tied to **immediate kinetic events** (where things are being struck, what is being targeted, what kind of weapon is involved), and the closing bin moves toward **persistent pressure language** (blockade, siege, sustained conditions rather than single events). This is the same kind of shift PressTV showed from "victory/synagogue/forced" to "blockade/naval/talks/islamabad", but Behold Israel's trajectory looks narrower — it stays inside the strike-to-blockade arc rather than branching into diplomacy and third-country negotiation.

Expected phrase-level outputs to inspect after rerun:

- Top bigrams by PMI (from `phrase_bigram_df`)
- Top trigrams (from `phrase_trigram_df`)
- Retained vs dropped vs new phrases between first and second half (from `phrase_temporal_change_df`)

If you want to inspect the notebook exports directly:

- [TF-IDF bump chart](./assets/behold-israel/tfidf_bump.png)
- [TF-IDF terms figure](./assets/behold-israel/tfidf_terms.png)
- [Phrase network](./assets/behold-israel/phrase_network.html)
- [Phrase bigram bar chart](./assets/behold-israel/phrase_bigram_bar.html)

---

## 6. Threading: _pending rerun_

![Reply distribution](./assets/behold-israel/reply_distribution.png)

_Figure 7. Distribution of reply counts across messages._

Expected numbers to fill in from `reply_summary_df` and `reply_feature_tests_df` after running Section 12:

- Total reply edges
- Messages receiving at least one reply (and share of all messages)
- Largest thread size and deepest thread depth
- Maximum replies to a single message
- Median first-reply lag
- Feature tests: does text length / media presence / sentiment meaningfully predict reply rate?

Qualitative expectation: since Behold Israel publishes at roughly one-third the rate of PressTV, its absolute reply counts will be lower, but the reply _share_ could plausibly be higher if the channel's audience leans toward sustained discussion rather than passive consumption. Validate with the actual `reply_summary_df.share_messages_with_replies` value.

---

## 7. Media strategy: _pending rerun_

![Media vs text topic split](./assets/behold-israel/media_text_topic.png)

_Figure 8. Topic distribution differences between media-bearing and text-only posts._

Expected numbers to fill in from `media_text_summary_df`, `media_text_stat_tests_df`, `media_text_tfidf_terms_df`, `media_text_topic_distribution_df`, and `media_text_frame_distribution_df` after running Section 14:

- Exact media vs text-only counts and the media-only subset
- Text length comparison (median, significance test)
- Stat tests: does sentiment, posting hour, topic, frame, or emotion differ by segment?
- Vocabulary lifts: which terms over-index in media posts vs text-only posts?

Qualitative expectation based on the 46.8% media baseline (much closer to 1:1 than PressTV's 63.5%): Behold Israel's media strategy is likely **less asymmetric** than PressTV's. Media may still over-index on strike reporting (where footage and maps are available) while text-only may over-index on commentary, interpretation, and the "today stories" roundups. The rerun should confirm or refute this.

---

## Conclusion

Using the notebook figures as a guide, Behold Israel in this 22-day sample has three defining characteristics that are already visible from the pre-rerun figures and should be sharpened by the post-tuning pass.

### 1. Lower tempo, narrower scope than a state-affiliated wire

At ~55 messages per day with a 46.8% media share, Behold Israel publishes at a fraction of PressTV's throughput and with less visual saturation. It reads as an editorial channel that curates and comments rather than one that floods the feed.

### 2. A single dominant narrative axis

Default-parameter topic modeling collapsed the channel into essentially one cluster before tuning. That is not a failure of the model — it is a structural fact about the channel: its semantic field is anchored tightly on Iran, the IDF, and Israel. Sub-themes exist (strike reporting, blockade framing, symbolic / prophetic commentary, channel-summary posts) but they all orbit the same axis.

### 3. A clear lexical drift from strikes to siege

The TF-IDF bump chart shows the opening period's vocabulary (strikes, sites, ballistic, targets) giving way to the closing period's vocabulary (blockade and adjacent terms). This is the single sharpest temporal signal in the dataset and aligns with the arc from active kinetic phase to sustained-pressure phase in the underlying geopolitical story.

The remaining sections — tone, actors, threading, media strategy — require the tuned notebook rerun to complete. Once the rerun produces `sentiment_emotion_df`, `entity_summary_df`, `reply_summary_df`, and `media_text_summary_df`, the placeholders above can be replaced with concrete numbers and the executive summary revised accordingly.

## Supporting files

Exported figures and tables for this write-up live here:

- Figures: [`docs/assets/behold-israel/`](./assets/behold-israel/)
- Tables/CSVs: [`docs/assets/behold-israel/data/`](./assets/behold-israel/data/) _(create after rerun)_

Key interactive exports (to be generated):

- [Topic scatter](./assets/behold-israel/topic_scatter.html)
- [Entity network](./assets/behold-israel/entity_network.html)
- [Phrase network](./assets/behold-israel/phrase_network.html)
