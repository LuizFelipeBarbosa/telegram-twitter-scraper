from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:  # pragma: no cover - exercised only without runtime deps.
    typer = None

from telegram_scraper.chat_discovery import filter_chats
from telegram_scraper.config import ConfigError, Settings, parse_since_date
from telegram_scraper.kg.config import KGSettings
from telegram_scraper.kg.event_hierarchy import KGEventHierarchyService
from telegram_scraper.kg.models import ChannelProfile
from telegram_scraper.kg.runtime import (
    build_embedder,
    build_message_translator,
    build_repository,
    build_semantic_extractor,
    build_stream,
    build_vector_store,
)
from telegram_scraper.kg.segmentation import parse_delimiter_patterns
from telegram_scraper.kg.services import (
    KGBackfillService,
    KGChannelMaintenanceService,
    KGChannelRepairService,
    KGListenerService,
    KGProcessingWorker,
    KGProfileService,
    KGQueryService,
)
from telegram_scraper.markdown_writer import MarkdownWriter
from telegram_scraper.state_store import StateStore
from telegram_scraper.sync_service import SyncService
from telegram_scraper.telegram_client import TelegramAccountClient, TelegramClientError
from telegram_scraper.viz_api.app import create_app


def _load_settings(env_file: Path, *, require_output_root: bool = True) -> Settings:
    settings = Settings.load(env_file)
    if require_output_root:
        settings.validate_output_root()
    return settings


def _load_kg_settings(env_file: Path) -> KGSettings:
    return KGSettings.load(env_file)


def _json_ready(value: object) -> object:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


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


def _exit_with_error(message: str) -> "typer.Exit":
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def _echo_json(value: object) -> None:
    typer.echo(json.dumps(_json_ready(value), indent=2, default=str))


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

    @app.command("kg-profile-show")
    def kg_profile_show(
        channel: int = typer.Option(..., "--channel", help="Telegram channel ID."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Show the active segmentation profile for a channel."""
        try:
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_database()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        service = KGProfileService(build_repository(kg_settings))
        try:
            _echo_json(service.show(channel))
        except RuntimeError as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-profile-upsert")
    def kg_profile_upsert(
        channel: int = typer.Option(..., "--channel", help="Telegram channel ID."),
        file: Path = typer.Option(..., "--file", exists=True, dir_okay=False, help="Path to a JSON profile file."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Create or update a channel segmentation profile."""
        try:
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_database()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        payload = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise _exit_with_error("profile file must contain a JSON object")

        profile = ChannelProfile(
            channel_id=channel,
            delimiter_patterns=parse_delimiter_patterns(payload.get("delimiter_patterns", [])),
            media_group_window_seconds=int(payload.get("media_group_window_seconds", 60)),
            time_gap_minutes=int(payload.get("time_gap_minutes", 10)),
            similarity_merge_threshold=float(payload.get("similarity_merge_threshold", 0.7)),
            lookback_message_count=int(payload.get("lookback_message_count", payload.get("lookback_story_count", 5))),
            notes=str(payload["notes"]) if payload.get("notes") is not None else None,
            channel_title=str(payload["channel_title"]) if payload.get("channel_title") is not None else None,
            channel_slug=str(payload["channel_slug"]) if payload.get("channel_slug") is not None else None,
            channel_username=str(payload["channel_username"]) if payload.get("channel_username") is not None else None,
        )

        service = KGProfileService(build_repository(kg_settings))
        try:
            _echo_json(service.upsert(profile))
        except RuntimeError as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-backfill")
    def kg_backfill(
        limit_per_chat: int = typer.Option(
            0,
            "--limit-per-chat",
            min=0,
            help="Optional cap on messages per channel. 0 means no limit.",
        ),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Stream historical Telegram channel messages into the KG raw-message stream."""
        try:
            settings = _load_settings(env_file)
            settings.require_credentials()
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_stream()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client = _build_client(settings)
        stream = build_stream(kg_settings)
        repository = build_repository(kg_settings) if kg_settings.database_url else None
        service = KGBackfillService(settings, client, stream, repository=repository)

        async def _run() -> None:
            try:
                result = await service.backfill(limit_per_chat=limit_per_chat or None)
                typer.echo(
                    f"ok kg-backfill: channels={result.chats_processed}, streamed={result.messages_streamed}"
                )
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (TelegramClientError, OSError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-listen")
    def kg_listen(
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Listen for live Telegram channel messages and append them to the KG raw-message stream."""
        try:
            settings = _load_settings(env_file)
            settings.require_credentials()
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_stream()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        client = _build_client(settings)
        stream = build_stream(kg_settings)
        repository = build_repository(kg_settings) if kg_settings.database_url else None
        service = KGListenerService(settings, client, stream, repository=repository)

        async def _run() -> None:
            try:
                typer.echo("listening for Telegram channel events...")
                await service.listen()
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            raise typer.Exit(code=0)
        except (TelegramClientError, OSError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    def _build_query_service(env_file: Path) -> KGQueryService:
        kg_settings = _load_kg_settings(env_file)
        kg_settings.require_database()
        repository = build_repository(kg_settings)
        repository.ensure_schema()
        return KGQueryService(repository)

    def _build_channel_maintenance_service(env_file: Path) -> tuple[KGSettings, KGChannelMaintenanceService]:
        kg_settings = _load_kg_settings(env_file)
        kg_settings.require_database()
        kg_settings.require_vector_store()
        kg_settings.require_embeddings()
        kg_settings.require_semantic_extraction()
        return (
            kg_settings,
            KGChannelMaintenanceService(
                repository=build_repository(kg_settings),
                vector_store=build_vector_store(kg_settings),
                embedder=build_embedder(kg_settings),
                extractor=build_semantic_extractor(kg_settings),
                settings=kg_settings,
                translator=build_message_translator(kg_settings),
            ),
        )

    def _build_channel_repair_service(env_file: Path) -> tuple[Settings, KGSettings, TelegramAccountClient, KGChannelRepairService]:
        settings = _load_settings(env_file)
        settings.require_credentials()
        kg_settings = _load_kg_settings(env_file)
        kg_settings.require_database()
        kg_settings.require_vector_store()
        kg_settings.require_embeddings()
        kg_settings.require_semantic_extraction()
        kg_settings.require_translation()
        client = _build_client(settings)
        repository = build_repository(kg_settings)
        vector_store = build_vector_store(kg_settings)
        embedder = build_embedder(kg_settings)
        extractor = build_semantic_extractor(kg_settings)
        translator = build_message_translator(kg_settings)
        maintenance_service = KGChannelMaintenanceService(
            repository=repository,
            vector_store=vector_store,
            embedder=embedder,
            extractor=extractor,
            settings=kg_settings,
            translator=translator,
        )
        return (
            settings,
            kg_settings,
            client,
            KGChannelRepairService(
                app_settings=settings,
                telegram_client=client,
                repository=repository,
                vector_store=vector_store,
                embedder=embedder,
                extractor=extractor,
                settings=kg_settings,
                translator=translator,
                maintenance_service=maintenance_service,
            ),
        )

    @app.command("kg-process-worker")
    def kg_process_worker(
        consumer: str = typer.Option("local-worker", "--consumer", help="Redis stream consumer name."),
        batch_size: int = typer.Option(25, "--batch-size", min=1, max=500, help="Redis batch size."),
        loop: bool = typer.Option(False, "--loop", help="Keep polling Redis and process batches continuously."),
        poll_interval_seconds: float = typer.Option(5.0, "--poll-interval-seconds", min=0.1, help="Idle poll interval."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Persist raw messages, embed, and assign typed semantic nodes (message-atomic pipeline)."""
        try:
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_database()
            kg_settings.require_stream()
            kg_settings.require_embeddings()
            kg_settings.require_semantic_extraction()
            kg_settings.require_vector_store()
            kg_settings.require_translation()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        worker = KGProcessingWorker(
            repository=build_repository(kg_settings),
            stream=build_stream(kg_settings),
            embedder=build_embedder(kg_settings),
            vector_store=build_vector_store(kg_settings),
            settings=kg_settings,
            extractor=build_semantic_extractor(kg_settings),
            translator=build_message_translator(kg_settings),
        )

        try:
            if loop:
                result = worker.run_loop(
                    consumer_name=consumer,
                    batch_size=batch_size,
                    poll_interval_seconds=poll_interval_seconds,
                )
            else:
                result = worker.process_batch(consumer_name=consumer, batch_size=batch_size)
            typer.echo(
                "ok kg-process-worker: "
                f"messages={result.messages_processed}, "
                f"embedded={result.messages_embedded}, "
                f"assignments={result.assignments_created}, "
                f"nodes_created={result.nodes_created}, "
                f"cross_channel_matches={result.cross_channel_matches}"
            )
        except RuntimeError as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-reset-channel")
    def kg_reset_channel(
        channel: int = typer.Option(..., "--channel", help="Telegram channel ID to clear semantic state for."),
        yes: bool = typer.Option(False, "--yes", help="Confirm semantic-state deletion."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Clear derived node state for a channel while preserving raw messages."""
        if not yes:
            raise _exit_with_error("kg-reset-channel requires --yes")
        try:
            kg_settings, service = _build_channel_maintenance_service(env_file)
            del kg_settings
        except ConfigError as exc:
            raise _exit_with_error(str(exc))
        try:
            result = service.reset_channel(channel)
            typer.echo(
                "ok kg-reset-channel: "
                f"stories_preserved={result.stories_preserved}, "
                f"nodes_deleted={result.nodes_deleted}"
            )
        except RuntimeError as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-repair-channels")
    def kg_repair_channels(
        channel: list[int] = typer.Option(..., "--channel", help="Telegram channel ID to repair and rebuild."),
        since: Optional[str] = typer.Option(None, "--since", help="Optional ISO timestamp override. Defaults to SINCE_DATE."),
        workers: Optional[int] = typer.Option(None, "--workers", min=1, help="Optional extractor worker count."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Fetch missing raw messages for channels, rebuild KG state, translate non-English text, and rerun KG semantics."""
        try:
            _settings, _kg_settings, client, service = _build_channel_repair_service(env_file)
            effective_since = parse_since_date(since) if since else None
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        def _echo_progress(progress) -> None:
            typer.echo(
                f"progress kg-repair-channels: "
                f"channel={progress.channel_id} "
                f"processed={progress.channel_message_processed}/{progress.channel_message_total} "
                f"assignments={progress.assignments_created} "
                f"nodes_created={progress.nodes_created} "
                f"failures={progress.failures} "
                f"rate={progress.rate_per_sec:.2f}/s"
            )

        async def _run() -> None:
            try:
                result = await service.repair_channels(
                    channel,
                    since=effective_since,
                    workers=workers,
                    progress_callback=_echo_progress,
                )
                typer.echo(
                    "ok kg-repair-channels: "
                    f"channels={result.channels_processed}, "
                    f"messages_upserted={result.messages_upserted}, "
                    f"stories_rebuilt={result.stories_rebuilt}, "
                    f"assignments={result.assignments_created}, "
                    f"nodes_created={result.nodes_created}, "
                    f"relations={result.relations_created}"
                )
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (LookupError, TelegramClientError, OSError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-sync-status")
    def kg_sync_status(
        channel: list[int] = typer.Option(..., "--channel", help="Telegram channel ID to inspect."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Compare Telegram-visible latest timestamps with ingested raw messages and rebuilt stories."""
        try:
            _settings, _kg_settings, client, service = _build_channel_repair_service(env_file)
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        async def _run() -> None:
            try:
                _echo_json(await service.sync_status(channel))
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except (LookupError, TelegramClientError, OSError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-themes-now")
    def kg_themes_now(
        limit: int = typer.Option(20, "--limit", min=1, max=200, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List the hottest themes in the last 24 hours."""
        try:
            _echo_json(_build_query_service(env_file).themes_now(limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-themes-emerging")
    def kg_themes_emerging(
        limit: int = typer.Option(20, "--limit", min=1, max=200, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List emerging themes based on current heat phases."""
        try:
            _echo_json(_build_query_service(env_file).themes_emerging(limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-themes-fading")
    def kg_themes_fading(
        limit: int = typer.Option(20, "--limit", min=1, max=200, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List fading themes based on current heat phases."""
        try:
            _echo_json(_build_query_service(env_file).themes_fading(limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-themes-history")
    def kg_themes_history(
        slug: str = typer.Option(..., "--slug", help="Theme slug."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Show daily article-count and drift history for a theme."""
        try:
            _echo_json(_build_query_service(env_file).theme_history(slug))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-topics-now")
    def kg_topics_now(
        limit: int = typer.Option(20, "--limit", min=1, max=200, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Deprecated alias for `kg-themes-now`."""
        kg_themes_now(limit=limit, env_file=env_file)

    @app.command("kg-topics-emerging")
    def kg_topics_emerging(
        limit: int = typer.Option(20, "--limit", min=1, max=200, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Deprecated alias for `kg-themes-emerging`."""
        kg_themes_emerging(limit=limit, env_file=env_file)

    @app.command("kg-topics-fading")
    def kg_topics_fading(
        limit: int = typer.Option(20, "--limit", min=1, max=200, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Deprecated alias for `kg-themes-fading`."""
        kg_themes_fading(limit=limit, env_file=env_file)

    @app.command("kg-topic-history")
    def kg_topic_history(
        topic: str = typer.Option(..., "--topic", help="Theme slug."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Deprecated alias for `kg-themes-history`."""
        kg_themes_history(slug=topic, env_file=env_file)

    @app.command("kg-events-list")
    def kg_events_list(
        limit: int = typer.Option(50, "--limit", min=1, max=500, help="Maximum number of rows to return."),
        include_children: bool = typer.Option(False, "--include-children", help="Include child events in addition to top-level parent events."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List canonical event nodes."""
        try:
            _echo_json(_build_query_service(env_file).list_nodes(kind="event", limit=limit, include_children=include_children))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-rebuild-event-hierarchy")
    def kg_rebuild_event_hierarchy(
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Recompute parent-child event hierarchy links and synthetic parent events."""
        try:
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_database()
            service = KGEventHierarchyService(build_repository(kg_settings))
            _echo_json(service.rebuild())
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-people-list")
    def kg_people_list(
        limit: int = typer.Option(50, "--limit", min=1, max=500, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List canonical person nodes."""
        try:
            _echo_json(_build_query_service(env_file).list_nodes(kind="person", limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-nations-list")
    def kg_nations_list(
        limit: int = typer.Option(50, "--limit", min=1, max=500, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List canonical nation nodes."""
        try:
            _echo_json(_build_query_service(env_file).list_nodes(kind="nation", limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-orgs-list")
    def kg_orgs_list(
        limit: int = typer.Option(50, "--limit", min=1, max=500, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List canonical organization nodes."""
        try:
            _echo_json(_build_query_service(env_file).list_nodes(kind="org", limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-places-list")
    def kg_places_list(
        limit: int = typer.Option(50, "--limit", min=1, max=500, help="Maximum number of rows to return."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """List canonical place nodes."""
        try:
            _echo_json(_build_query_service(env_file).list_nodes(kind="place", limit=limit))
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))

    @app.command("kg-node-show")
    def kg_node_show(
        kind: str = typer.Option(..., "--kind", help="Node kind: person, nation, org, place, event, or theme."),
        slug: str = typer.Option(..., "--slug", help="Stable node slug."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Show a sectioned node detail payload by kind and slug (message-atomic pipeline)."""
        if kind not in {"person", "nation", "org", "place", "event", "theme"}:
            raise _exit_with_error("kg-node-show requires --kind to be one of person, nation, org, place, event, theme")
        try:
            detail = _build_query_service(env_file).node_show(kind=kind, slug=slug)
        except (ConfigError, RuntimeError) as exc:
            raise _exit_with_error(str(exc))
        if detail is None:
            raise _exit_with_error("node not found")
        _echo_json(detail)

    @app.command("viz-api")
    def viz_api(
        host: str = typer.Option("0.0.0.0", "--host", help="Host interface to bind the visualization API server."),
        port: int = typer.Option(8000, "--port", min=1, max=65535, help="Port to bind the visualization API server."),
        env_file: Path = typer.Option(Path(".env"), help="Path to environment file."),
    ) -> None:
        """Run the read-only visualization API for the KG frontend."""
        try:
            kg_settings = _load_kg_settings(env_file)
            kg_settings.require_database()
        except ConfigError as exc:
            raise _exit_with_error(str(exc))

        try:
            import uvicorn
        except ImportError as exc:
            raise _exit_with_error(
                "uvicorn is not installed. Install project dependencies before running viz-api."
            ) from exc

        app_instance = create_app(kg_settings)
        uvicorn.run(app_instance, host=host, port=port, log_level="info")
else:  # pragma: no cover - exercised only without runtime deps.
    app = None
