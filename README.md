# Telegram Scraper + Knowledge Graph

This repository contains two related runtimes built on the same Telegram account session:

- a Telegram archive scraper that exports selected chats to Markdown under a local output root
- a Telegram channel knowledge graph pipeline that stores raw messages, segmented stories, typed semantic nodes, and read models for a visualization UI

The current KG is node-based. Canonical node kinds are `event`, `person`, `nation`, `org`, `place`, and `theme`. User-facing reads use stable `{kind, slug}` identifiers instead of opaque topic IDs. Legacy `kg-topics-*` commands and `/api/topics/*` routes still exist as deprecated theme-only aliases.

## What Lives Here

- `src/telegram_scraper/`: archive CLI, Telegram client, KG pipeline, and FastAPI visualization API
- `viz-web/`: React + Vite frontend for the knowledge graph
- `tests/`: backend and API tests
- `docs/superpowers/`: design and planning notes for the current frontend work

## Archive Scope

Supported archive sources:

- direct messages
- private groups and supergroups you are in
- channels you joined
- saved messages

Currently out of scope:

- secret chats
- non-image media download
- contacts sync
- multi-account support

## Pipeline Overview

1. Archive commands such as `sync-all` and `sync-chat` write Markdown exports plus a local SQLite message database under `OUTPUT_ROOT`.
2. KG producers such as `kg-backfill` and `kg-listen` stream Telegram channel messages into Redis.
3. `kg-segment-worker` consumes those raw messages, persists them in Postgres, stores English translations for non-English content, segments stories, extracts typed nodes, updates Pinecone vectors, and refreshes read projections.
4. `viz-api` serves a read-only FastAPI surface, and `viz-web` renders the React frontend on top of it.

There is no standalone scheduler command in the current CLI. Projection refresh happens inside `kg-segment-worker` after each processed batch.

## Requirements

- Python 3.9+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+
- Docker with Compose
- Telegram API credentials from [my.telegram.org](https://my.telegram.org/)
- OpenAI API key for embeddings, translation, and semantic extraction
- Pinecone API key plus three indexes: story, theme, and event

## Setup

Install backend and frontend dependencies:

```bash
uv sync
cp .env.example .env
cd viz-web && npm install
```

The backend reads configuration from `.env` by default. Start from [`.env.example`](./.env.example) and change the paths before running anything if you are not using `/Volumes/T7`.

## Configuration

[`.env.example`](./.env.example) is the canonical template for supported variables. These are the important groups:

### Telegram Access

- `TG_API_ID`
- `TG_API_HASH`
- `TG_PHONE`
- `SESSION_PATH`

These are required for any command that talks to Telegram, including `login`, `list-chats`, archive sync commands, `kg-backfill`, and `kg-listen`.

### Archive Runtime

- `OUTPUT_ROOT`
- `MESSAGES_DB_PATH`
- `SINCE_DATE`
- `CHAT_TYPES`
- `INCLUDE_CHATS`
- `EXCLUDE_CHATS`

Notes:

- `OUTPUT_ROOT` must already exist, be a directory, and be writable.
- The parent directory of `MESSAGES_DB_PATH` must already exist and be writable.
- `SINCE_DATE` accepts `YYYY-MM-DD` or a full ISO timestamp.
- `CHAT_TYPES` defaults to `group,channel,saved`.
- `INCLUDE_CHATS` and `EXCLUDE_CHATS` accept comma-separated selectors.

### KG Infrastructure

- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX_STORY`
- `PINECONE_INDEX_THEME`
- `PINECONE_INDEX_EVENT`

These are required for the KG write path. `viz-api` only needs `DATABASE_URL`, with optional Redis caching when `REDIS_URL` is configured.

### KG Model and Worker Tuning

- `EMBEDDING_MODEL`
- `KG_SEMANTIC_MODEL`
- `KG_TRANSLATION_MODEL`
- `KG_STREAM_KEY`
- `KG_CONSUMER_GROUP`
- `KG_CROSS_CHANNEL_THRESHOLD`
- `KG_VECTOR_DIMENSION`
- `KG_SEGMENT_BATCH_SIZE`
- `KG_STREAM_RETENTION_MS`
- `KG_SEMANTIC_MAX_CHARS`
- `KG_SEMANTIC_BATCH_SIZE`
- `KG_HISTORICAL_EXTRACTION_WORKERS`
- `KG_THEME_MATCH_THRESHOLD`
- `KG_EVENT_MATCH_THRESHOLD`
- `KG_EVENT_MATCH_WINDOW_DAYS`

Notes:

- `PINECONE_INDEX_TOPIC` is still accepted as a deprecated fallback for `PINECONE_INDEX_THEME`.
- The default embedding model is `text-embedding-3-small`.
- The default semantic and translation models are `gpt-5-mini`.

### Visualization Ports

- `VIZ_API_PORT`
- `VIZ_WEB_PORT`

These are used by Compose port publishing. The local CLI defaults are still `8000` for `viz-api` and `5173` for the Vite dev server.

## Quick Start

### Archive Only

Log in once and inspect the chats visible to the Telegram account:

```bash
uv run telegram-scraper login
uv run telegram-scraper list-chats
```

Export every selected chat:

```bash
uv run telegram-scraper sync-all
```

Export or backfill a single chat:

```bash
uv run telegram-scraper sync-chat --chat <id-or-slug>
uv run telegram-scraper backfill --chat <id-or-slug> --limit 100
```

Repair missing archived images:

```bash
uv run telegram-scraper repair-media
uv run telegram-scraper repair-media --chat <id-or-slug>
```

### Full KG + Visualization Stack

Start Postgres and Redis:

```bash
docker compose up -d postgres redis
```

Start the worker and visualization services:

```bash
docker compose up -d kg-segment-worker viz-api viz-web
```

Run the historical producer:

```bash
uv run telegram-scraper kg-backfill
```

Optional first pass with smaller scope:

```bash
uv run telegram-scraper kg-backfill --limit-per-chat 200
```

Optional live ingestion after `login` has created a valid session:

```bash
docker compose --profile live up -d kg-listen
```

If you prefer to run the live listener outside Docker:

```bash
uv run telegram-scraper kg-listen
```

Useful inspection commands:

```bash
uv run telegram-scraper kg-themes-now
uv run telegram-scraper kg-events-list --limit 20
uv run telegram-scraper kg-people-list --limit 20
uv run telegram-scraper kg-node-show --kind theme --slug ceasefire-peace-negotiations
```

Local endpoints:

- API health: `http://localhost:8000/api/health`
- channels: `http://localhost:8000/api/channels`
- theme heat: `http://localhost:8000/api/themes/heat`
- graph snapshot: `http://localhost:8000/api/graph/snapshot`
- frontend: `http://localhost:5173`

## Local Development

If you only want infrastructure in Docker, keep Postgres and Redis in Compose and run the app processes locally:

```bash
docker compose up -d postgres redis
uv run telegram-scraper kg-segment-worker --consumer local-dev --loop
uv run telegram-scraper viz-api --host 0.0.0.0 --port 8000
cd viz-web && npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000` by default. Override that with `VIZ_API_PROXY_TARGET` if needed.

Compose-specific notes:

- `docker-compose.yml` overrides `DATABASE_URL` and `REDIS_URL` inside containers so services talk to `postgres` and `redis` by hostname.
- The optional `kg-listen` container mounts `/Volumes/T7`. If your archive path lives somewhere else, update [`docker-compose.yml`](./docker-compose.yml) or run `kg-listen` locally.
- The frontend container runs `npm install` on startup and serves the Vite dev server on port `5173`.

## KG Workflow Notes

- `kg-backfill` and `kg-listen` ingest Telegram channels only.
- Channel profiles are created automatically during KG ingestion. Use `kg-profile-upsert` only when you need to tune segmentation for a specific channel.
- `kg-segment-preview --channel <id>` previews segmentation without writing stories.
- Semantic extraction emits strict typed buckets for `events`, `people`, `nations`, `orgs`, `places`, and `themes`.
- Event hierarchy is two levels only: top-level parent event plus leaf sub-events. Named operations/campaigns outrank generic grouping.
- Generic `strike` and `airstrike` families are consolidated at the actor level. For example, `Iranian strikes in Tel Aviv` and `Iranian strikes in Haifa` roll up under `Iranian strikes`, while location and organization browsing happens on the parent event page through child-event metadata.
- `GET /api/events` and `GET /api/graph/snapshot` collapse event children by default. Use `include_children=true` only when you explicitly need leaf events in those list views.
- Parent event detail payloads expose enriched `child_events[]` rows with `last_updated`, `event_start_at`, `primary_location`, `location_labels`, and `organization_labels`. Child event detail payloads expose `parent_event` for breadcrumbs.
- Person canonicalization collapses simple middle-initial variants into one node. For example, `Donald Trump`, `Donald J Trump`, and `Donald J. Trump` resolve to the same person, with alternate forms retained as aliases.
- Event pages and theme pages expose sectioned related nodes. The frontend derives the `Actors` grouping from `people + nations + orgs`.

## Rebuild and Repair

Preview or override a channel profile:

```bash
uv run telegram-scraper kg-profile-show --channel <id>
uv run telegram-scraper kg-segment-preview --channel <id>
uv run telegram-scraper kg-profile-upsert --channel <id> --file channel-profile.json
```

Inspect ingest lag for one or more channels:

```bash
uv run telegram-scraper kg-sync-status --channel <id>
```

Repair channel history gaps and rebuild stories plus semantics from preserved raw messages:

```bash
uv run telegram-scraper kg-repair-channels --channel <id-a> --channel <id-b> --workers 8
```

`kg-repair-channels` fetches Telegram messages from `SINCE_DATE` through now, upserts missing `raw_messages`, rebuilds `story_units`, stores English translations for non-English content, reruns semantic extraction, and refreshes projections once at the end.

Rebuild semantic state for one channel without re-fetching Telegram:

```bash
uv run telegram-scraper kg-reset-channel --channel <id> --yes
uv run telegram-scraper kg-resegment-channel --channel <id>
```

Rebuild semantic state for multiple channels with the historical path:

```bash
uv run telegram-scraper kg-resegment-channels --channel <id-a> --channel <id-b> --workers 8
```

Rebuild the event hierarchy after changing hierarchy logic or after a bulk semantic repair:

```bash
uv run telegram-scraper kg-rebuild-event-hierarchy
```

Keep live sync running after repairs if you want new Telegram messages to continue landing in `raw_messages`:

```bash
uv run telegram-scraper kg-listen
```

## CLI Reference

Archive commands:

- `uv run telegram-scraper login`
- `uv run telegram-scraper list-chats`
- `uv run telegram-scraper sync-all`
- `uv run telegram-scraper sync-chat --chat <id-or-slug>`
- `uv run telegram-scraper backfill --chat <id-or-slug> --limit <n>`
- `uv run telegram-scraper repair-media [--chat <id-or-slug>]`

KG write-path commands:

- `uv run telegram-scraper kg-profile-show --channel <id>`
- `uv run telegram-scraper kg-profile-upsert --channel <id> --file channel-profile.json`
- `uv run telegram-scraper kg-segment-preview --channel <id> [--limit <n>]`
- `uv run telegram-scraper kg-backfill [--limit-per-chat <n>]`
- `uv run telegram-scraper kg-listen`
- `uv run telegram-scraper kg-segment-worker [--consumer <name>] [--batch-size <n>] [--loop] [--poll-interval-seconds <n>]`
- `uv run telegram-scraper kg-sync-status --channel <id>...`
- `uv run telegram-scraper kg-repair-channels --channel <id>... [--since <iso>] [--workers <n>]`
- `uv run telegram-scraper kg-reset-channel --channel <id> --yes`
- `uv run telegram-scraper kg-resegment-channel --channel <id> [--workers <n>]`
- `uv run telegram-scraper kg-resegment-channels --channel <id>... [--workers <n>]`
- `uv run telegram-scraper kg-rebuild-event-hierarchy`

KG read-path commands:

- `uv run telegram-scraper kg-themes-now`
- `uv run telegram-scraper kg-themes-emerging`
- `uv run telegram-scraper kg-themes-fading`
- `uv run telegram-scraper kg-themes-history --slug <slug>`
- `uv run telegram-scraper kg-events-list`
- `uv run telegram-scraper kg-people-list`
- `uv run telegram-scraper kg-nations-list`
- `uv run telegram-scraper kg-orgs-list`
- `uv run telegram-scraper kg-places-list`
- `uv run telegram-scraper kg-node-show --kind <kind> --slug <slug>`

Deprecated compatibility aliases:

- `uv run telegram-scraper kg-topics-now`
- `uv run telegram-scraper kg-topics-emerging`
- `uv run telegram-scraper kg-topics-fading`
- `uv run telegram-scraper kg-topic-history --topic <theme-slug>`

Visualization:

- `uv run telegram-scraper viz-api [--host 0.0.0.0] [--port 8000]`

## Visualization API

Primary read endpoints:

- `GET /api/health`
- `GET /api/channels`
- `GET /api/themes/heat`
- `GET /api/themes/{slug}/history`
- `GET /api/events`
- `GET /api/people`
- `GET /api/nations`
- `GET /api/orgs`
- `GET /api/places`
- `GET /api/themes`
- `GET /api/nodes/{kind}/{slug}`
- `GET /api/graph/snapshot`

Important query parameters:

- `window`: one of `1d`, `3d`, `5d`, `7d`, `14d`, `31d`
- `phase`: optional theme phase filter on heat and graph endpoints
- `limit` and `offset`: paging controls on list endpoints
- `kind`: repeatable filter on `GET /api/graph/snapshot`
- `include_children`: optional boolean on `GET /api/events` and `GET /api/graph/snapshot`. Defaults to `false`, which means event browse surfaces return top-level parent events only.

Event-detail hierarchy behavior:

- Parent event detail returns rolled-up `article_count`, rolled-up stories, direct related nodes, and a `child_events[]` array for sub-event browsing.
- Each `child_events[]` row includes `node_id`, `slug`, `display_name`, `summary`, `article_count`, `last_updated`, `event_start_at`, `primary_location`, `location_labels`, and `organization_labels`.
- Child event detail keeps its own direct stories and related nodes and exposes a lightweight `parent_event` reference for breadcrumb navigation.

Deprecated theme-only aliases:

- `GET /api/topics/heat`
- `GET /api/topics/{slug}/timeline`
- `GET /api/topics/{slug}/related`
- `GET /api/topics/{slug}/stories`

Frontend routes:

- `/`: landscape view
- `/node/:kind/:slug`: node detail view
- `/trends`: placeholder
- `/propagation`: placeholder
- `/evolution`: placeholder

## Output Layout

```text
/Volumes/T7/
├── telegram_messages.db
└── theVault/
    └── raw/
        └── telegram/
            ├── direct/
            │   └── alice-smith_123456789/
            │       ├── _chat.md
            │       ├── _state.json
            │       └── media/
            │           └── msg-1043.jpg
            ├── group/
            │   └── market-research_987654321/
            │       ├── _chat.md
            │       ├── _state.json
            │       └── media/
            ├── channel/
            │   └── example-channel_111222333/
            │       ├── _chat.md
            │       ├── _state.json
            │       └── media/
            └── saved/
                └── saved-messages/
                    ├── _chat.md
                    ├── _state.json
                    └── media/
```

`telegram_messages.db` stores deduplicated raw Telegram messages in SQLite. `_state.json` stores incremental sync state, and `_chat.md` stores lightweight metadata for each archived chat.

## Development

Useful verification commands:

```bash
uv run pytest
uv run telegram-scraper --help
uv run telegram-scraper viz-api --help
cd viz-web && npm run test
cd viz-web && npm run build
```
