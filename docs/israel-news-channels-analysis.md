# Three Israeli news channels on Telegram: a multi-channel notebook-based analysis

This article analyzes three Israel-oriented news Telegram channels in parallel using the figures produced by the same analysis sections implemented in [`notebooks/pipeline_israel_news.ipynb`](../notebooks/pipeline_israel_news.ipynb). It is structured to mirror the format of the PressTV write-up in [`docs/presstv-channel-analysis.md`](presstv-channel-analysis.md) so the four channels can be compared section-for-section.

The notebook pulls three channels with `MESSAGE_LIMIT = 1200`:

- **ILTV Israel News 24/7** — [`iltvnews`](https://t.me/iltvnews)
- **Jewish Breaking News - JBN** — [`jewishbreakingnewstelegram`](https://t.me/jewishbreakingnewstelegram)
- **The Times of Israel** — [`thetimesofisrael2022`](https://t.me/thetimesofisrael2022)

> **Status.** This write-up is a first pass. The summary tables, sentiment distributions, topic clusters, entity rankings, and media/text stat tests cited below are read directly from the notebook outputs. Static PNGs and HTML exports are referenced under `docs/assets/israel-news/` on the assumption that the notebook's figure-export cells will write there; if they do not yet exist, rerun the notebook with the export cells enabled to materialize them.

## Executive summary

Four cross-channel patterns stand out most clearly.

1. **Three channels, three different publishing rhythms.** Over the same 1,200-message slice, ILTV covers **104 days** (≈11.5 msgs/day), JBN covers **47 days** (≈25.5 msgs/day), and The Times of Israel covers **122 days** (≈9.8 msgs/day). JBN behaves like a live wire, ILTV like a steady news channel, and TOI like a headline-driven article feed.
2. **Three different media strategies.** Media share is **55.2%** for ILTV, **44.9%** for JBN, and **100%** for The Times of Israel. TOI's 100% figure reflects the fact that every post carries an article link-preview card, so its "media" is structurally different from the video/photo clips on ILTV and JBN.
3. **A shared emotional baseline: fear-heavy and neutral-skewed, never upbeat.** Mean sentiment is **-0.261** (ILTV), **-0.227** (JBN), and **-0.229** (TOI). The positive-label share never exceeds **5.6%** on any channel, and the dominant emotion is **fear** on two of the three channels (ILTV and TOI) and **neutral** on JBN — but with fear as a close second.
4. **A shared cast of actors: Iran, Israel, the US, Israeli forces, and Trump anchor every channel.** The topic-model granularity differs sharply (ILTV collapses into one dominant Iran/Israel cluster, JBN and TOI fragment into dozens of smaller clusters), but the co-mention networks converge on the same handful of actors.

A second-order finding is a structural one: JBN's top "entity" by message count is not a geopolitical actor but the string **WHATSAPP GROUP** (518 messages), which reflects self-promotional boilerplate. This is worth flagging because it inflates JBN's entity network and complicates direct comparisons of entity rankings across channels.

## Scope and method

| Metric | ILTV | JBN | Times of Israel |
|---|---:|---:|---:|
| Total messages | 1,200 | 1,200 | 1,200 |
| Text-bearing messages | 911 | 1,037 | 1,200 |
| Media-bearing messages | 662 | 539 | 1,200 |
| Media share | 55.2% | 44.9% | 100.0% |
| Messages with `reply_to_message_id` | 0 | 1 | 0 |
| Observed days | 104 | 47 | 122 |
| Avg messages / day | 11.5 | 25.5 | 9.8 |
| Start | 2026-01-03 16:08 UTC | 2026-03-01 20:59 UTC | 2025-12-16 23:12 UTC |
| End | 2026-04-16 21:08 UTC | 2026-04-16 23:48 UTC | 2026-04-16 21:01 UTC |

Notes:

- All timestamps below are **UTC**.
- Figures come from the same notebook analysis modules used by `pipeline.ipynb` and `pipeline_presstv.ipynb`, driven per-channel by the `CHANNEL_SLUGS` loop in Section 3.
- Topic clusters should be read as **approximate thematic neighborhoods**, not immutable labels. Keyword-based labels are auto-generated; use `TOPIC_LABEL_OVERRIDES` in Section 7 to rename clusters after inspecting each channel's `topic_summary_df`.
- JBN's entity table is contaminated by promotional boilerplate (WhatsApp group/channel links). The first-pass commentary flags this rather than filtering it out, since the raw rank is itself informative about the channel's posting style.

---

## 1. Cadence: three different publishing rhythms

![ILTV cadence heatmap](./assets/israel-news/iltvnews_cadence_calendar_heatmap.png)

_Figure 1a. ILTV hour-by-hour message volume across the 104-day window._

![JBN cadence heatmap](./assets/israel-news/jewishbreakingnewstelegram_cadence_calendar_heatmap.png)

_Figure 1b. JBN hour-by-hour message volume across the 47-day window._

![Times of Israel cadence heatmap](./assets/israel-news/thetimesofisrael2022_cadence_calendar_heatmap.png)

_Figure 1c. The Times of Israel hour-by-hour message volume across the 122-day window._

Even though each channel fetched the same 1,200-message cap, the cadence profile is sharply different:

- **ILTV** — averages **11.5 messages per day** across 104 days; busiest day is **2026-02-28 (113 messages)**; peak hour is **2026-02-28 09:00 UTC (14 messages)**. Overall media share **55.2%**.
- **JBN** — averages **25.5 messages per day** across 47 days — more than double ILTV's rate. Busiest day is **2026-03-02 (58 messages)**; peak hour is **2026-04-11 21:00 UTC (13 messages)**. Overall media share **44.9%**.
- **Times of Israel** — averages **9.8 messages per day** across 122 days, the slowest tempo of the three. Busiest day is **2026-03-01 (27 messages)**; peak hour is **2026-03-20 14:00 UTC (5 messages)**. Overall media share **100.0%**.

A useful way to read this is that the three channels occupy different editorial roles:

- **JBN** looks the most like a PressTV-style rolling wire — compressed to a 47-day window but dense inside it, with bursts into the low-teens in a single hour.
- **ILTV** looks like a steady Israeli news feed — lower tempo than JBN but more continuous over a longer window, with occasional event-driven spikes.
- **The Times of Israel** looks like a curated article-headline feed — the lowest volume, the widest observation window, the most even distribution across days, and a peak hour of only 5 messages.

The 100% media share on TOI is a structural artifact of its posting format: every post is an article share with a link-preview card, so every message is flagged as media-bearing. That distinction matters in Section 7 below, where the media-vs-text comparison collapses for TOI.

---

## 2. Tone: all three are fear-heavy, negative-leaning, and rarely positive

![ILTV sentiment over time](./assets/israel-news/iltvnews_sentiment_over_time.png)

_Figure 2a. ILTV Section 6 sentiment timeline._

![JBN sentiment over time](./assets/israel-news/jewishbreakingnewstelegram_sentiment_over_time.png)

_Figure 2b. JBN Section 6 sentiment timeline._

![Times of Israel sentiment over time](./assets/israel-news/thetimesofisrael2022_sentiment_over_time.png)

_Figure 2c. Times of Israel Section 6 sentiment timeline._

The three channels share a clearly negative emotional baseline, but they arrive there in slightly different ways.

### ILTV — 910 scored messages

- Mean sentiment score: **-0.261**
- Sentiment labels: **Neutral 493 (54.2%), Negative 366 (40.2%), Positive 51 (5.6%)**
- Emotion labels: **Fear 289 (31.8%), Neutral 235 (25.8%), Anger 163 (17.9%), Sadness 100 (11.0%), Disgust 71 (7.8%), Joy 52 (5.7%)**

### JBN — 1,037 scored messages

- Mean sentiment score: **-0.227**
- Sentiment labels: **Neutral 654 (63.1%), Negative 325 (31.3%), Positive 58 (5.6%)**
- Emotion labels: **Neutral 389 (37.5%), Fear 376 (36.3%), Anger 130 (12.5%), Sadness 89 (8.6%), Disgust 23 (2.2%), Joy 17 (1.6%), Surprise 13 (1.3%)**

### Times of Israel — 1,200 scored messages

- Mean sentiment score: **-0.229**
- Sentiment labels: **Neutral 814 (67.8%), Negative 344 (28.7%), Positive 42 (3.5%)**
- Emotion labels: **Fear 415 (34.6%), Neutral 316 (26.3%), Anger 197 (16.4%), Sadness 169 (14.1%), Joy 52 (4.3%), Disgust 40 (3.3%), Surprise 11 (0.9%)**

Three things follow from this.

First, the **negative aggregate mean coexists with a neutral-label plurality** on every channel. That is the same pattern PressTV showed. Neutral-looking reporting sits inside a framing environment dominated by threat, confrontation, and loss, so the overall sentiment score lands negative even while most individual messages are classified as neutral.

Second, the **positive-label share is almost identical and almost negligible** across the three channels: **5.6% / 5.6% / 3.5%**. None of these channels are publishing celebratory content at meaningful volumes.

Third, the **fear-vs-neutral emotion ordering flips on JBN**. Fear is the dominant emotion on ILTV (31.8%) and TOI (34.6%), but JBN has a marginal neutral-over-fear split (37.5% vs 36.3%). That is consistent with JBN's higher share of short logistical posts (WhatsApp promos, donation prompts, flight notices) that fall into the neutral emotion bucket even while the channel's overall sentiment remains negative.

---

## 3. Themes: one channel collapses into a single cluster, two fragment into many

![ILTV topic prevalence](./assets/israel-news/iltvnews_topic_prevalence_static.png)

_Figure 3a. Top topic clusters for ILTV._

![JBN topic prevalence](./assets/israel-news/jewishbreakingnewstelegram_topic_prevalence_static.png)

_Figure 3b. Top topic clusters for JBN._

![Times of Israel topic prevalence](./assets/israel-news/thetimesofisrael2022_topic_prevalence_static.png)

_Figure 3c. Top topic clusters for The Times of Israel._

The topic-modeling granularity is the single biggest editorial difference across the three channels.

### ILTV collapses into one dominant cluster

ILTV's `topic_summary_df` produces only three clusters with default parameters, and one of them absorbs almost the entire corpus:

- **Topic 2: israel, iran, iranian** — **876 messages** (out of 910 scored)
- Topic 0: truth social, truth, social — 18
- Topic 1: venezuela, maduro, venezuelan — 16

That is the same structural pattern Behold Israel showed on its first pass: the channel's semantic field is tight enough that HDBSCAN treats the whole corpus as a single dense region. The top keywords inside Topic 2 — *israel, iran, iranian, israeli, idf, minister, regime, according, missile, trump* — describe the entire Iran–Israel conflict axis in one bag. Re-tuning `min_cluster_size` and `umap_min_dist` (as was done for Behold Israel) would likely split this into sub-themes, but the raw finding that ILTV is almost entirely one narrative is itself informative.

### JBN fragments into many small clusters dominated by self-promotion

JBN produces **19 clusters** including the noise bucket. The top clusters are all heavily contaminated by channel-promotion language:

- Topic 17: whatsapp, links, jbn links — **150**
- Topic 7: whatsapp, iran, trump — **108**
- Topic 16: whatsapp, missile, links — **101**
- Topic 8: hezbollah, whatsapp, idf — **69**
- Topic 14: whatsapp, ballistic, follow jbn — **67**
- Topic 2: flights, passengers, el — **51**
- Topic 10: iran, whatsapp, group — **50**
- Topic 3: whatsapp, president, trump — **40**
- Topic 4: whatsapp, idf, lebanon — **33**
- Topic 0: soldiers, donate, verified — **33**
- Noise / Mixed — **180**

Once the WhatsApp/donate boilerplate is mentally subtracted, the real editorial themes on JBN are **Iran, IDF, Hezbollah, Lebanon, missile/ballistic reporting, and flight/transport incidents**. The noise cluster (180 messages) is itself the second-largest bucket, which is another signal that JBN's corpus is noisier than ILTV's or TOI's.

### The Times of Israel fragments into many substantive clusters

TOI produces dozens of small but coherent clusters. The top 20 by message count:

- Topic 6: read, missile, injured — **85**
- Topic 8: read, israel, war — **73**
- Topic 14: read, west, police — **64**
- Topic 15: read, bondi, jews — **57**
- Topic 24: trump, iran, read trump — **57**
- Topic 19: briefing, daily briefing, daily — **55**
- Topic 18: netanyahu, read, trump — **47**
- Topic 16: gaza, hamas, read — **43**
- Topic 13: read, iran, idf — **42**
- Topic 3: holocaust, read, jewish — **27**
- Topic 26: read, netanyahu, pm — **25**
- Topic 7: idf, killed, lebanon — **25**
- Topic 4: read, rafah, israel — **23**
- Topic 5: israel, read, lebanon — **22**
- Topic 9: read, killed, iranian — **21**
- Topic 10: hormuz, strait, strait hormuz — **20**
- Topic 12: hezbollah, idf, read idf — **20**
- Topic 11: talks, read, vance — **19**
- Topic 0: study, researchers, scientists — **18**
- Topic 20: khamenei, trump, read — **18**

The word *read* appears in almost every cluster because TOI posts all end with a "Read more:" link, which slips into the top keyword list even after stopword cleaning. That aside, TOI's distribution looks more like a traditional newsroom section lineup: missile-strike reporting, war coverage, West Bank policing, Bondi Beach attack aftermath, Trump/Iran diplomacy, daily-briefing roundups, Netanyahu coverage, Gaza/Hamas, Hormuz maritime pressure, Khamenei, and even a research/science cluster. In other words, **TOI is the only one of the three channels whose topic model clearly separates non-conflict beats from conflict beats**.

Interactive notebook exports for this section (one set per channel):

- [ILTV topic scatter](./assets/israel-news/iltvnews_topic_scatter.html) · [JBN topic scatter](./assets/israel-news/jewishbreakingnewstelegram_topic_scatter.html) · [TOI topic scatter](./assets/israel-news/thetimesofisrael2022_topic_scatter.html)
- [ILTV topic prevalence](./assets/israel-news/iltvnews_topic_prevalence.html) · [JBN topic prevalence](./assets/israel-news/jewishbreakingnewstelegram_topic_prevalence.html) · [TOI topic prevalence](./assets/israel-news/thetimesofisrael2022_topic_prevalence.html)

---

## 4. Actors: three channels, one co-mention triangle

![ILTV top entities](./assets/israel-news/iltvnews_entity_top_entities_static.png)

_Figure 5a. Most-mentioned entities — ILTV._

![JBN top entities](./assets/israel-news/jewishbreakingnewstelegram_entity_top_entities_static.png)

_Figure 5b. Most-mentioned entities — JBN._

![Times of Israel top entities](./assets/israel-news/thetimesofisrael2022_entity_top_entities_static.png)

_Figure 5c. Most-mentioned entities — The Times of Israel._

After filtering each graph to entities appearing in at least three messages with edge weight ≥ 2, the sizes are:

| Channel | Messages with entities | Nodes | Edges |
|---|---:|---:|---:|
| ILTV | 888 / 910 | 193 | 885 |
| JBN | 1,034 / 1,037 | 175 | 935 |
| Times of Israel | 1,172 / 1,200 | 144 | 568 |

The top entities by message count are:

### ILTV (top 12)

Israel (290), Iran (251), Iranian (206), US (166), Israeli (151), Trump (99), Tehran (81), IDF (76), Jewish (55), Hezbollah (50), Gaza (49), Hamas (46)

### JBN (top 12)

WHATSAPP GROUP (518)*, Iran (391), Israel (358), WHATSAPP CHANNEL WHATSAPP GROUP (228)*, Iranian (222), US (182), Israeli (168), Hezbollah (155), Lebanon (128), IDF (122), Trump (89), Tehran (72)

_\* WhatsApp entries are self-promotional boilerplate captured by the NER stage; ignore for narrative interpretation._

### Times of Israel (top 12)

Iran (349), Israel (291), US (246), Trump (134), Iranian (125), Israeli (115), Netanyahu (104), Gaza (85), Hezbollah (83), Daily Briefing (70), Lebanon (68), Jewish (60)

Two cross-channel observations follow.

**First, the core triangle is identical.** Iran, Israel, the US, and their associated demonyms (Iranian, Israeli) are the top five entities on every one of the three channels. Trump appears in the top six on every channel. IDF, Hezbollah, Lebanon, and Tehran appear in the top twelve on every channel. So while the topic models look very different — monolithic on ILTV, noisy on JBN, fragmented-but-substantive on TOI — the **actor layer is almost interchangeable**.

**Second, the hierarchies differ in informative ways.** Israel outranks Iran on ILTV (290 vs 251). Iran outranks Israel on JBN (391 vs 358) and on TOI (349 vs 291). Netanyahu is a top-ten entity only on TOI (104 mentions), which is consistent with TOI's more Israeli-politics-inflected newsroom beat structure. JBN's Hezbollah count (155) is notably higher than on ILTV (50), reflecting the JBN corpus's later sampling window when the Lebanon/Hezbollah front was more active.

Interactive notebook exports for this section:

- [ILTV entity bar chart](./assets/israel-news/iltvnews_entity_top_entities.html) · [ILTV entity network](./assets/israel-news/iltvnews_entity_network.html)
- [JBN entity bar chart](./assets/israel-news/jewishbreakingnewstelegram_entity_top_entities.html) · [JBN entity network](./assets/israel-news/jewishbreakingnewstelegram_entity_network.html)
- [TOI entity bar chart](./assets/israel-news/thetimesofisrael2022_entity_top_entities.html) · [TOI entity network](./assets/israel-news/thetimesofisrael2022_entity_network.html)

---

## 5. Language shifts and phrase signatures

Each channel's TF-IDF bump chart splits its window into equal temporal bins and surfaces rising vs falling terms. For this first pass, the phrase-network outputs tell a sharper story than the bump trajectories, because the phrase signatures make the three channels' editorial fingerprints visible.

**ILTV's top bigrams by PMI** include:

- **eyal zamir, strait hormuz, masoud pezeshkian, reza pahlavi, lindsey graham, lion's roar, bondi beach, los angeles, ultra orthodox, precautionary directive**

That is a mix of Israeli, Iranian, and US political figures; strategic geography (Hormuz); and Israeli civil-society markers (ultra orthodox, precautionary directive). It reads like the signature of a channel covering Iran, Israel, and American commentary with a civil-defense inflection.

**JBN's top bigrams by PMI** include:

- **bint jbeil, white house, bnei brak, naim qassem, litani river, ramat gan, tucker carlson, marine expeditionary, beit shemesh, vision goggles, kharg island, kiryat shmona**

That is a much more operational vocabulary: southern Lebanese border villages (Bint Jbeil, Litani River), Israeli frontline municipalities (Bnei Brak, Ramat Gan, Beit Shemesh, Kiryat Shmona), Hezbollah leadership (Naim Qassem), US marine force structure (marine expeditionary), and Iranian strategic geography (Kharg Island). It is the signature of a near-real-time tactical feed.

**The Times of Israel's top bigrams by PMI** include:

- **ariela karmel, bnei brak, rossella tercatin, sam sokol, movie maven, shin bet, borschel dan, western wall, amanda borschel, ultra orthodox, beit shemesh, jordan hoffman**

This list is dominated by **journalist bylines** — Ariela Karmel, Rossella Tercatin, Sam Sokol, Amanda Borschel[-Dan], Jordan Hoffman — which is how a newsroom feed distinguishes itself at the phrase level: repeat-author attributions cluster together with PMI even after general-news stopword cleaning. Shin Bet and Western Wall complete the signature as Israel-specific institutional markers.

So the three channels have readable phrase-level fingerprints:

- **ILTV** — commentary on Iran/Israel with civilian-defense language.
- **JBN** — operational/tactical reporting across the northern front and maritime choke points.
- **TOI** — a byline-indexed Israeli newsroom with beat sections.

Inspect the notebook exports directly:

- TF-IDF bump charts: [ILTV](./assets/israel-news/iltvnews_tfidf_bump.png) · [JBN](./assets/israel-news/jewishbreakingnewstelegram_tfidf_bump.png) · [TOI](./assets/israel-news/thetimesofisrael2022_tfidf_bump.png)
- Phrase networks: [ILTV](./assets/israel-news/iltvnews_phrase_network.html) · [JBN](./assets/israel-news/jewishbreakingnewstelegram_phrase_network.html) · [TOI](./assets/israel-news/thetimesofisrael2022_phrase_network.html)

---

## 6. Threading: essentially absent on all three channels

![ILTV reply distribution](./assets/israel-news/iltvnews_reply_distribution.png)

_Figure 6. Reply distributions (all three channels produce the same shape: nearly zero)._

Unlike PressTV, these three channels run as **broadcast-only feeds** with reply posting effectively disabled or unused by the audience:

| Channel | Reply edges | Largest thread | Deepest thread | Max replies to one msg | Median first-reply lag |
|---|---:|---:|---:|---:|---:|
| ILTV | 0 | 1 | 0 | 0 | — |
| JBN | 1 | 2 | 1 | 1 | 0.42 min |
| Times of Israel | 0 | 1 | 0 | 0 | — |

The operational consequence is that the reply-based engagement proxy that was so informative on PressTV (which had 171 reply edges, a 22-message leader-memorial thread, and a significant text-length effect on reply rate) **cannot be run meaningfully on these three channels**. Section 12's `reply_feature_tests_df` for ILTV and TOI explicitly reports that its Chi-square test was skipped due to zero expected frequencies.

This is itself a finding: **these three Israeli channels are not built for sustained comment discussion**. They are built to dispatch and move on. Any engagement-style analysis of them needs to come from external platforms (reactions via Telegram's built-in reaction counts, or cross-posted discussion on other platforms) rather than from reply threading.

---

## 7. Media strategy: different roles on each channel

![ILTV media vs text topic split](./assets/israel-news/iltvnews_media_text_topic.png)

_Figure 7a. Topic distribution difference between media-bearing and text-only posts — ILTV._

![JBN media vs text topic split](./assets/israel-news/jewishbreakingnewstelegram_media_text_topic.png)

_Figure 7b. Topic distribution difference between media-bearing and text-only posts — JBN._

_Figure 7c for TOI is intentionally omitted: TOI is 100% media-bearing (all 1,200 posts carry link-preview cards), so a media-vs-text split does not exist for this channel._

### ILTV — media and text-only are almost the same editorial product

- Media 662 (55.2%), text-only 538
- Median text length: **Media 487 vs Text-only 263** (Mann-Whitney U, p < 0.001, effect size -0.47)
- Sentiment score: **not significant** (p = 0.384)
- Dominant sentiment: **not significant** (p = 0.506)
- Dominant emotion: **marginal** (p = 0.055)
- Dominant topic: **not significant** (p = 0.888) — because the whole channel is one topic
- Dominant frame: **significant** (p = 0.006)
- Posting hour distribution: **significant** (p < 0.001)

On ILTV, the media/text-only split barely changes what the posts are about. The topic model does not distinguish them because the corpus is overwhelmingly one topic. The meaningful differences are structural: media posts are **longer** and appear at **different hours** than text-only posts. That suggests ILTV uses media mostly to thicken its prime-hour coverage rather than to segregate subject matter by format.

### JBN — media and text-only are strongly different products

- Media 539 (44.9%), text-only 661
- Median text length: **Media 451.5 vs Text-only 544** (p < 0.001, effect size +0.27 — note the sign: text-only is _longer_ on JBN)
- Sentiment score: **significant** (p = 0.003) — media posts are marginally less negative (-0.21 vs -0.31)
- Dominant sentiment: **marginally significant** (p = 0.038)
- Dominant emotion: **strongly significant** (p < 0.001, effect size 0.20)
- Dominant topic: **very strongly significant** (p < 0.001, effect size 0.44)
- Dominant frame: **strongly significant** (p = 0.00001, effect size 0.18)
- Posting hour distribution: not significant (p = 0.498)

JBN is the channel where media vs text-only genuinely picks out two different editorial streams. The very large topic effect size (0.44) is the key number: media posts and text-only posts on JBN really are about **different things**, not just the same content in different wrappers. The text-only stream carries more of the WhatsApp/donate/solidarity boilerplate; the media stream carries more of the strike/Hezbollah/Lebanon tactical content.

### Times of Israel — no media/text split to measure

All 1,200 posts carry a link-preview media card, so `media_text_summary_df` reports 1,200 media and 0 text-only. The stat-test battery is correspondingly skipped. Any variation within TOI has to be measured along a different axis (e.g. article-section, headline-vs-summary length, or time of day) rather than along the media-vs-text axis that the notebook's Section 14 provides.

---

## Conclusion

Using the notebook figures as a guide, the three Israeli news channels in this sample describe three different kinds of editorial operation, but with an overlapping actor and emotional baseline.

### 1. Different publishing rhythms

- **JBN** is a compressed, high-tempo wire (47 days, 25.5/day).
- **ILTV** is a steady medium-tempo feed (104 days, 11.5/day).
- **TOI** is a low-tempo curated headline feed (122 days, 9.8/day).

### 2. A shared emotional register

All three channels land at a negative aggregate sentiment mean between -0.22 and -0.26, a neutral label plurality, a positive-label share of 3.5-5.6%, and fear as the dominant or co-dominant emotion. Reporting style varies; emotional climate does not.

### 3. Very different topic-model shapes, same actor layer

ILTV collapses into one Iran-Israel cluster. JBN fragments into many clusters contaminated by channel-promotion boilerplate. TOI fragments into many substantive newsroom-section clusters. But the entity co-mention layer converges on the same triangle — Iran, Israel, the US — with IDF, Iranian, Israeli, Trump, Tehran, Hezbollah, and Lebanon as consistent secondary nodes on every channel.

### 4. Different media roles

ILTV's media and text-only posts are editorially similar; JBN's are sharply different; TOI has no text-only posts to compare. That means any cross-channel media-strategy claim has to be made channel-by-channel, not in aggregate.

### 5. Broadcast, not discussion

None of the three channels supports meaningful reply-thread analysis. For engagement signals, external proxies are needed. Comparisons with PressTV's reply-based findings therefore have to be framed as a structural difference between the channels, not as a weakness on the Israeli-news side.

Taken together, the three channels look less like clones of each other and more like a **three-piece coverage stack**: JBN supplies the fast tactical wire, ILTV supplies the steady commentary feed, and TOI supplies the curated article index. They share a narrative center of gravity (the Iran-Israel-US triangle) and a negative emotional baseline, but they occupy different editorial positions around that shared center.

## Supporting files

Exported figures and tables for this write-up are expected to live here once the notebook's export cells are rerun:

- Figures: [`docs/assets/israel-news/`](./assets/israel-news/) _(populate on rerun)_
- Tables/CSVs: [`docs/assets/israel-news/data/`](./assets/israel-news/data/) _(populate on rerun)_

Key interactive exports (to be generated per channel):

- Topic scatter — one HTML per channel
- Entity network — one HTML per channel
- Phrase network — one HTML per channel
