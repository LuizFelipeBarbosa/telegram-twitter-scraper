# Telegram Scraper

This repository now has one supported purpose:

- export Telegram account chats to Markdown plus a local SQLite message cache
- inspect channel messages in a notebook-only workflow that fetches, translates, embeds, and analyzes messages entirely in memory, including sentiment, topics, entities, cadence, rhetoric, reply threading, phrase networks, and media-vs-text comparisons

The old frontend, visualization API, and KG ingestion/runtime stack have been removed.

## What Lives Here

- `src/telegram_scraper/`: archive CLI, Telegram client, notebook helpers, local storage code, and reusable notebook analysis modules under `src/telegram_scraper/analysis/`
- `notebooks/pipeline.ipynb`: the supported thin orchestration notebook workflow, now covering Sections 1-14
- `docs/`: analysis plans that correspond to the reusable notebook sections, including `docs/09_media_vs_text_comparison.md`
- `tests/`: archive and notebook-helper tests

## Setup

Install dependencies:

```bash
uv sync --group dev
cp .env.example .env
```

The notebook and all notebook-only analysis sections use packages from the `dev` dependency group.

## Environment

Use [`.env.example`](./.env.example) as the template.

Required for archive CLI:

- `TG_API_ID`
- `TG_API_HASH`
- `TG_PHONE`
- `SESSION_PATH`
- `OUTPUT_ROOT`
- `MESSAGES_DB_PATH`

Required for the notebook-only translation and embedding flow:

- `OPENAI_API_KEY`
- `EMBEDDING_MODEL`
- `KG_TRANSLATION_MODEL`
- `KG_SEMANTIC_MAX_CHARS`
- `KG_SEMANTIC_BATCH_SIZE`

Optional chat filtering:

- `SINCE_DATE`
- `CHAT_TYPES`
- `INCLUDE_CHATS`
- `EXCLUDE_CHATS`

## CLI

Authenticate once:

```bash
uv run telegram-scraper login
```

List visible chats:

```bash
uv run telegram-scraper list-chats
```

Export all selected chats:

```bash
uv run telegram-scraper sync-all
```

Export or backfill one chat:

```bash
uv run telegram-scraper sync-chat --chat <id-or-slug>
uv run telegram-scraper backfill --chat <id-or-slug> --limit 100
```

Repair missing image downloads:

```bash
uv run telegram-scraper repair-media
uv run telegram-scraper repair-media --chat <id-or-slug>
```

## Notebook

Launch JupyterLab:

```bash
uv run jupyter lab
```

Then open [notebooks/pipeline.ipynb](./notebooks/pipeline.ipynb).

That notebook:

1. connects to Telegram
2. lists channels
3. fetches recent channel messages into memory
4. translates messages into English in memory
5. embeds messages in memory
6. analyzes sentiment and emotion over time
7. maps topic clusters with UMAP + HDBSCAN
8. tracks vocabulary shifts with TF-IDF and period word clouds
9. maps named-entity co-occurrence networks and ego graphs
10. profiles messaging cadence with hourly heatmaps, spike tables, and media overlays
11. classifies rhetorical framing over time, builds a first-half vs second-half frame reallocation view, and surfaces example messages for manual review
12. analyzes reply threading and simple engagement proxies from `reply_to_message_id`
13. builds bigram / trigram phrase tables, phrase networks, and temporal phrase-shift views
14. compares media-bearing messages against text-only posts across timing, length, sentiment, topics, rhetoric, TF-IDF terms, and optional entity distributions

It does not write to Postgres, Redis, or Pinecone.

All notebook analysis dependencies used by Sections 6-14 are included in `uv sync --group dev`, including `transformers`, `torch`, `seaborn`, `plotly`, `umap-learn`, `hdbscan`, `nltk`, `scikit-learn`, `matplotlib`, `networkx`, `python-louvain`, `spacy`, `nbformat`, `wordcloud`, and `scipy`.

## Tests

Run the remaining automated tests with:

```bash
uv run pytest
```
