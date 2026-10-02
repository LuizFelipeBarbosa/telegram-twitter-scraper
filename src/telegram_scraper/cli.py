from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

try:
    import typer
except ImportError:  # pragma: no cover - exercised only without runtime deps.
    typer = None

from telegram_scraper.chat_discovery import discover_chats, filter_chats, resolve_chat
from telegram_scraper.config import ConfigError, Settings
from telegram_scraper.markdown_writer import MarkdownWriter
from telegram_scraper.snapshot import fetch_snapshot
from telegram_scraper.state_store import StateStore
from telegram_scraper.sync_service import SyncService
from telegram_scraper.telegram_client import TelegramAccountClient, TelegramClientError


def _load_settings(env_file: Path, *, require_output_root: bool = True) -> Settings:
    settings = Settings.load(env_file)
    if require_output_root:
        settings.validate_output_root()
    return settings


def _build_client(settings: Settings) -> TelegramAccountClient:
    return TelegramAccountClient(
        api_id=settings.api_id or 0,
        api_hash=settings.api_hash,
        session_path=settings.session_path,
        output_root=settings.output_root,
        phone=settings.phone,
    )


def _build_service(settings: Settings) -> tuple[TelegramAccountClient, SyncService]:
    client = _build_client(settings)
    state_store = StateStore(settings.output_root, settings.messages_db_path)
    writer = MarkdownWriter(state_store)
    service = SyncService(settings, client, state_store, writer)
    return client, service


def _format_chat_line(chat: object, selected: bool) -> str:
    marker = "*" if selected else " "
    username = getattr(chat, "username", None)
    username_text = f" @{username}" if username else ""
    return f"{marker} {chat.chat_type.value:<7} {chat.chat_id:<12} {chat.slug}{username_text} | {chat.title}"


def _parse_day(value: str, *, option: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"{option} must be a date in YYYY-MM-DD format, got: {value!r}") from None


def _format_snapshot_table(channels: list[dict[str, object]]) -> str:
    header = f"{'channel':<32} {'messages':>9}  first_ts -> last_ts"
    lines = [header]
    for channel in channels:
        lines.append(
            f"{str(channel['slug']):<32} {channel['message_count']:>9}  "
            f"{channel['first_ts'] or '-'} -> {channel['last_ts'] or '-'}"
        )
    return "\n".join(lines)


def _exit_with_error(message: str) -> "typer.Exit":
    typer.echo(message, err=True)
    return typer.Exit(code=1)


if typer is not None:
    app = typer.Typer(
        help=(
            "Export Telegram account chats to Markdown. "
            "Notebook-only message translation, embedding, and analysis live in notebooks/pipeline.ipynb."
        )
    )

    @app.command()
    def login(env_file: Path = typer.Option(Path(".env"), help="Path to environment file.")) -> None:
        """Authenticate the Telegram account and create the session file."""
        try:
            settings = _load_settings(env_file, require_output_root=False)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client = _build_client(settings)

        async def _run() -> None:
            try:
                me = await client.login()
                name = getattr(me, "first_name", None) or getattr(me, "username", None) or getattr(me, "id")
                typer.echo(f"Authorized Telegram account: {name}")
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("list-chats")
    def list_chats(env_file: Path = typer.Option(Path(".env"), help="Path to environment file.")) -> None:
        """List chats available to the account and mark the ones selected by config."""
        try:
            settings = _load_settings(env_file, require_output_root=False)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client, service = _build_service(settings)

        async def _run() -> None:
            try:
                chats = await service.discover_all_chats()
                selected = {
                    chat.chat_id
                    for chat in filter_chats(
                        chats,
                        chat_types=settings.chat_types,
                        include_chats=settings.include_chats,
                        exclude_chats=settings.exclude_chats,
                    )
                }
                for chat in chats:
                    typer.echo(_format_chat_line(chat, chat.chat_id in selected))
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("sync-all")
    def sync_all(
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Sync all chats selected by the configured filters."""
        try:
            settings = _load_settings(env_file)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client, service = _build_service(settings)

        async def _run() -> None:
            try:
                results = await service.sync_all()
                for result in results:
                    if result.status == "ok":
                        typer.echo(
                            f"ok {result.chat.chat_type.value} {result.chat.slug}: "
                            f"{result.exported_messages} exported, last_message_id={result.last_message_id}"
                        )
                    else:
                        typer.echo(f"error {result.chat.chat_type.value} {result.chat.slug}: {result.error}")
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("sync-chat")
    def sync_chat(
        chat: str = typer.Option(..., "--chat", help="Chat selector: id, username, title, or slug."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Sync a single selected chat."""
        try:
            settings = _load_settings(env_file)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client, service = _build_service(settings)

        async def _run() -> None:
            try:
                result = await service.sync_chat_by_selector(chat)
                typer.echo(
                    f"ok {result.chat.chat_type.value} {result.chat.slug}: "
                    f"{result.exported_messages} exported, last_message_id={result.last_message_id}"
                )
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (LookupError, TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

    @app.command()
    def backfill(
        chat: str = typer.Option(..., "--chat", help="Chat selector: id, username, title, or slug."),
        limit: int = typer.Option(100, "--limit", min=1, help="Maximum number of older messages to fetch."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Fetch older messages for a single chat."""
        try:
            settings = _load_settings(env_file)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client, service = _build_service(settings)

        async def _run() -> None:
            try:
                result = await service.backfill_chat_by_selector(chat, limit)
                typer.echo(
                    f"ok {result.chat.chat_type.value} {result.chat.slug}: "
                    f"{result.exported_messages} exported during backfill"
                )
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (LookupError, TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("repair-media")
    def repair_media(
        chat: str = typer.Option("", "--chat", help="Optional chat selector: id, username, title, or slug."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Refetch cached media-bearing messages that are missing local image downloads."""
        try:
            settings = _load_settings(env_file)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client, service = _build_service(settings)

        async def _run() -> None:
            try:
                if chat:
                    results = [await service.repair_media_by_selector(chat)]
                else:
                    results = await service.repair_missing_media_for_targets()
                for result in results:
                    typer.echo(
                        f"ok {result.chat.chat_type.value} {result.chat.slug}: "
                        f"scanned={result.scanned_messages}, repaired={result.repaired_messages}"
                    )
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (LookupError, TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

    @app.command()
    def snapshot(
        channel: List[str] = typer.Option(
            ..., "--channel", help="Channel selector: id, username, title, or slug. Repeatable."
        ),
        start: str = typer.Option(..., "--start", help="Inclusive start date (UTC), YYYY-MM-DD."),
        end: str = typer.Option(..., "--end", help="Exclusive end date (UTC), YYYY-MM-DD."),
        out: Path = typer.Option(Path("data/raw"), "--out", help="Parent directory for snapshot runs."),
        download_media: bool = typer.Option(
            False, "--download-media/--no-download-media", help="Also download image files to the archive output root."
        ),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Write a reproducible parquet snapshot of full-text messages to <out>/<run_id>/."""
        try:
            start_dt = _parse_day(start, option="--start")
            end_dt = _parse_day(end, option="--end")
            if start_dt >= end_dt:
                raise ValueError("--start must be before --end")
            settings = _load_settings(env_file, require_output_root=download_media)
            settings.require_credentials()
        except (ConfigError, ValueError) as exc:
            raise _exit_with_error(str(exc))

        client = _build_client(settings)
        fetched_label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{start_dt:%Y-%m-%d}_{end_dt:%Y-%m-%d}_{fetched_label}"
        run_dir = out / run_id

        async def _run() -> None:
            try:
                dialogs = await client.get_dialogs()
                available = discover_chats(dialogs)
                chats = []
                for selector in channel:
                    resolved = resolve_chat(available, selector)
                    if resolved.slug not in {chat.slug for chat in chats}:
                        chats.append(resolved)
                await fetch_snapshot(
                    client,
                    chats,
                    start=start_dt,
                    end=end_dt,
                    out_dir=run_dir,
                    download_media=download_media,
                    run_id=run_id,
                )
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (LookupError, ValueError, TelegramClientError, OSError) as exc:
            raise _exit_with_error(str(exc))

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        typer.echo(_format_snapshot_table(manifest["channels"]))
        typer.echo(f"snapshot written to {run_dir}")
else:  # pragma: no cover - exercised only without typer installed.
    app = None
