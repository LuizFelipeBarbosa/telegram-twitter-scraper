from __future__ import annotations

import asyncio
from pathlib import Path

try:
    import typer
except ImportError:  # pragma: no cover - exercised only without runtime deps.
    typer = None

from telegram_scraper.chat_discovery import filter_chats
from telegram_scraper.config import ConfigError, Settings
from telegram_scraper.markdown_writer import MarkdownWriter
from telegram_scraper.state_store import StateStore
from telegram_scraper.sync_service import SyncService
from telegram_scraper.telegram_client import TelegramAccountClient, TelegramClientError


def _load_settings(env_file: Path, *, require_output_root: bool = True) -> Settings:
    settings = Settings.load(env_file)
    if require_output_root:
        settings.validate_output_root()
    return settings


def _build_service(settings: Settings) -> tuple[TelegramAccountClient, SyncService]:
    client = TelegramAccountClient(
        api_id=settings.api_id or 0,
        api_hash=settings.api_hash,
        session_path=settings.session_path,
        output_root=settings.output_root,
        phone=settings.phone,
    )
    state_store = StateStore(settings.output_root)
    writer = MarkdownWriter(state_store)
    service = SyncService(settings, client, state_store, writer)
    return client, service


def _format_chat_line(chat: object, selected: bool) -> str:
    marker = "*" if selected else " "
    username = getattr(chat, "username", None)
    username_text = f" @{username}" if username else ""
    return f"{marker} {chat.chat_type.value:<7} {chat.chat_id:<12} {chat.slug}{username_text} | {chat.title}"


def _exit_with_error(message: str) -> "typer.Exit":
    typer.echo(message, err=True)
    return typer.Exit(code=1)


if typer is not None:
    app = typer.Typer(help="Export Telegram account chats to Markdown.")

    @app.command()
    def login(env_file: Path = typer.Option(Path(".env"), help="Path to environment file.")) -> None:
        """Authenticate the Telegram account and create the session file."""
        try:
            settings = _load_settings(env_file, require_output_root=False)
            settings.require_credentials()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client, _ = _build_service(settings)

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
else:  # pragma: no cover - exercised only without runtime deps.
    app = None
