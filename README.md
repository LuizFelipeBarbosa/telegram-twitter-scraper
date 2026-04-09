# Telegram Account Chat Scraper

This project logs into your Telegram account with Telethon and exports the chats you can access into local scrape archives under `/Volumes/T7/theVault/raw/telegram`.

## Scope

Supported sources:

- direct messages
- private groups and supergroups you are in
- channels you joined
- saved messages

Out of scope:

- secret chats
- non-image media download
- contacts sync
- real-time streaming
- multi-account support
- topic modeling, clustering, translation, or reindexing

## Setup

Use `uv` for environment management, installs, and commands.

```bash
uv sync
cp .env.example .env
uv run telegram-scraper login
uv run telegram-scraper list-chats
```

Required settings:

- `TG_API_ID`
- `TG_API_HASH`
- `TG_PHONE`

Optional settings:

- `SESSION_PATH`
- `OUTPUT_ROOT`
- `SINCE_DATE`
- `CHAT_TYPES`
- `INCLUDE_CHATS`
- `EXCLUDE_CHATS`

## Commands

- `uv run telegram-scraper login`
- `uv run telegram-scraper list-chats`
- `uv run telegram-scraper sync-all`
- `uv run telegram-scraper sync-chat --chat <id-or-slug>`
- `uv run telegram-scraper backfill --chat <id-or-slug> --limit <n>`
- `uv run telegram-scraper repair-media [--chat <id-or-slug>]`

## Output Layout

```text
/Volumes/T7/theVault/raw/telegram/
├── direct/
│   └── alice-smith_123456789/
│       ├── _chat.md
│       ├── _state.json
│       ├── _messages.json
│       └── media/
│           └── msg-1043.jpg
├── group/
│   └── market-research_987654321/
│       ├── _chat.md
│       ├── _state.json
│       ├── _messages.json
│       └── media/
├── channel/
│   └── example-channel_111222333/
│       ├── _chat.md
│       ├── _state.json
│       ├── _messages.json
│       └── media/
└── saved/
    └── saved-messages/
        ├── _chat.md
        ├── _state.json
        ├── _messages.json
        └── media/
```

`_messages.json` stores the raw deduplicated Telegram messages for a chat. `_state.json` stores incremental sync state. `_chat.md` stores a lightweight metadata note for the archived chat.

## Development

Run the test and verification commands with:

```bash
uv run python -m unittest discover -s tests -v
uv run python -m compileall src tests
uv run telegram-scraper --help
```
