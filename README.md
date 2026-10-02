# Press TV and its neighbours: a Telegram study (28 Feb - 17 Apr 2026)

How does a state-funded Iranian broadcaster (Press TV) differ from, and converge with, other state and private Iranian and Israeli Telegram channels during the first seven weeks of the 2026 war? This repository holds the data snapshot, the analysis library and a numbered series of "story" notebooks that answer the question step by step. Every figure's tidy data is exported so an HTML article can redraw it.

The study replaces a first pass (April 2026 article draft) that had known defects. That work is kept for provenance in [`archive/`](./archive/README.md).

## The design: a 2 x 2 (with one empty cell)

| slug | channel | ownership | country | note |
|---|---|---|---|---|
| `presstv` | Press TV | state (broadcaster) | Iran | IRIB English-language broadcaster |
| `irna-en` | IRNA (English) | state (news agency) | Iran | state news agency |
| `idfofficial` | Israel Defense Forces | state (military) | Israel | military spokesperson, not a broadcaster |
| `iltvnews` | ILTV Israel News | private (TV/online) | Israel | |
| `thetimesofisrael2022` | The Times of Israel | private (newspaper) | Israel | photo posts with a headline and a "Read more" link |
| `jewishbreakingnewstelegram` | Jewish Breaking News (JBN) | private (aggregator) | Israel | ownership unverified |

There is **no private Iranian channel** in the sample, so state-vs-private can only be tested inside Israel. Ownership is shown in charts by line style and marker (state = solid / filled, private = dashed / hollow); Iran uses warm colours, Israel cool ones.

## Layout

```
notebooks/            00_collect ... 06_media: the executed story notebooks (outputs kept)
src/telegram_scraper/
  study.py            channel table, window, load_posts(), clean_text(), verified events, findings.json writer
  viz.py              house chart style (matplotlib + Plotly), save() / export_data()
  snapshot.py         frozen parquet snapshots (fetch_snapshot, load_snapshot, build_posts)
  analysis/           stats, topics (joint model), sentiment, embeddings, validation, ... (library)
scripts/run_notebooks.sh   executes the notebooks in order, in place
scripts/build_article.py   rebuilds docs/study/article.html from the notebook CSVs
data/raw/<run_id>/    the frozen snapshot (parquet per channel + manifest.json)
data/cache/           embeddings, tone scores, topic assignments (git-ignored, rebuilt on demand)
data/validation/      blind coding sheet + private key for the tone-label check
docs/study/           figures/ (PNG, dpi 200), interactive/ (Plotly HTML), data/ (CSV behind every figure), findings.json,
                      article.html (the written article; open in a browser) + article_template.html
archive/              superseded first-pass notebooks, docs and assets (do not cite)
```

## Reproduce

```bash
uv sync --group dev
# spaCy English model (needed by notebook 04; not on PyPI, so install the wheel directly)
uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Only if you need a NEW snapshot (the study uses the frozen one in data/raw/):
cp .env.example .env            # fill TG_API_ID, TG_API_HASH, TG_PHONE
uv run telegram-scraper login
uv run telegram-scraper snapshot \
  --channel presstv --channel irna-en --channel idfofficial --channel iltvnews \
  --channel thetimesofisrael2022 --channel jewishbreakingnewstelegram \
  --start 2026-02-28 --end 2026-04-18 --out data/raw

# Re-run the story (never calls Telegram; the first run downloads three Hugging Face models):
bash scripts/run_notebooks.sh          # all of 00-06, in place
bash scripts/run_notebooks.sh 03 05    # or selected notebooks
uv run --group dev pytest -q

# Rebuild the article from the fresh exports, then open docs/study/article.html
uv run python scripts/build_article.py
```

The notebooks read `study.SNAPSHOT_DIR`; to analyse a different snapshot, change `SNAPSHOT_RUN` in `src/telegram_scraper/study.py`. Models used: `BAAI/bge-small-en-v1.5` (embeddings), `cardiffnlp/twitter-roberta-base-sentiment-latest` and `j-hartmann/emotion-english-distilroberta-base` (tone), spaCy `en_core_web_sm` (entities). The first execution of notebooks 03 and 05 takes several minutes (embedding 12k posts, topic-stability grid, scoring tone); later runs use `data/cache/`.

## Notebook guide

| notebook | question it answers |
|---|---|
| `00_collect` | What is in the snapshot (14,620 messages = 12,221 posts, 6 channels, 49 days) and how is it fetched? The fetch cell is guarded by `RUN_FETCH = False`. |
| `01_corpus` | Is the corpus clean? Album grouping, media mix, text lengths, boilerplate cleaning rules with before/after examples, corrections to the first pass, and which of seven candidate events the posts themselves support. |
| `02_tempo` | Who posts how much? Posts/day with bootstrap CIs, Press TV rate ratios in equal windows (full, 7-14 Apr, 10-17 Apr), state vs private within each country, event timelines, hour-of-day rhythm, views per post. |
| `03_agenda` | What does each channel talk about? One joint topic model (stability-tested), channel x topic shares, channel-specific vs shared topics, a map of all posts, and a symmetric test of the "Khamenei memorial = state fingerprint" claim. |
| `04_actors` | Who is named? spaCy entities per channel, actor-emphasis shares, and the Iran-Israel-US co-mention triangle. |
| `05_tone` | Do channels converge in tone? Sentiment and emotion per channel, TOST equivalence tests, tone around events, and the blind validation sheet and agreement check. |
| `06_media` | Do visuals carry a different message? Media mix with CIs, Press TV media-vs-topic recomputed correctly (chi-square, bias-corrected Cramer's V), the old "visuals for diplomacy" claim, views by media kind, one BH correction. |

Each notebook opens with a Question / Answer box, interprets every figure in prose, ends with "What this means for the article", and writes its key numbers into `docs/study/findings.json` under its own key. Helpers: `study.record_findings(key, payload)`; `viz.save(fig, name)` and `viz.export_data(df, name)` write `docs/study/figures/<name>.png` / `interactive/<name>.html` / `data/<name>.csv`.

## Validation status (tone labels)

`data/validation/coding_sheet.csv` (900 posts, 150 per channel, blind to channel) and the private key `coding_sheet_key.csv` exist. **No second coder has filled the sheet yet**; it will be an LLM, not a human, so the check measures agreement with another model. Until `data/validation/coding_sheet_coded.csv` exists and notebook 05 reports kappa >= 0.6 for a label, all sentiment and emotion results are exploratory and must not be presented as findings. Notebook 05 branches on this automatically.

## Known limitations

- **Design**: no private Iranian channel; the IDF is a military spokesperson (state, not a broadcaster); JBN's ownership is unverified; six channels are a convenience sample of English-language Telegram feeds, not of the two media systems.
- **Gaps**: JBN has no post on 28 Feb; JBN, ILTV and IRNA have a few zero or near-zero days (notebook 02). The snapshot cannot distinguish silence from deletion.
- **Late counts**: views and forwards were read on 2 Oct 2026, not in April.
- **Templated posts**: 46% of IDF posts are exact duplicates of another IDF post (alert templates), which shapes its topic and tone profile.
- **Topic model**: one third of posts are unassigned; labels are hand-written summaries; the selection rule for `min_cluster_size` was amended once (see notebook 03).
- **Keyword measures** (commemoration, actors, triangle) are proxies with some false positives; matches are printed in the notebooks.
- **Tone models** are off-the-shelf, unvalidated on war reporting, and truncate at 512 tokens.
- **Events** are "verified" only in the sense that the channels' own posts cluster around them.

## Telegram archive CLI (legacy)

The original archive tooling still works (`uv run telegram-scraper --help`: `login`, `list-chats`, `sync-all`, `sync-chat`, `backfill`, `repair-media`, `snapshot`); it is configured through `.env` (see `.env.example`).
