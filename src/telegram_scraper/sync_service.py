from __future__ import annotations

from datetime import datetime, timezone

from telegram_scraper.chat_discovery import discover_chats, filter_chats, resolve_chat
from telegram_scraper.config import Settings
from telegram_scraper.markdown_writer import MarkdownWriter
from telegram_scraper.models import ChatRecord, MediaRepairResult, SyncResult
from telegram_scraper.state_store import StateStore
from telegram_scraper.utils import ensure_utc


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SyncService:
    def __init__(
        self,
        settings: Settings,
        telegram_client: object,
        state_store: StateStore,
        writer: MarkdownWriter,
    ):
        self.settings = settings
        self.telegram_client = telegram_client
        self.state_store = state_store
        self.writer = writer

    async def discover_all_chats(self) -> list[ChatRecord]:
        dialogs = await self.telegram_client.get_dialogs()
        return discover_chats(dialogs)

    async def discover_target_chats(self) -> list[ChatRecord]:
        chats = await self.discover_all_chats()
        return filter_chats(
            chats,
            chat_types=self.settings.chat_types,
            include_chats=self.settings.include_chats,
            exclude_chats=self.settings.exclude_chats,
        )

    async def get_chat(self, selector: str) -> ChatRecord:
        chats = await self.discover_all_chats()
        return resolve_chat(chats, selector)

    async def sync_all(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        for chat in await self.discover_target_chats():
            try:
                results.append(await self.sync_chat(chat))
            except Exception as exc:
                state = self.state_store.load_state(chat)
                results.append(
                    SyncResult(
                        chat=chat,
                        exported_messages=0,
                        last_message_id=state.last_message_id,
                        status="error",
                        error=str(exc),
                    )
                )
        return results

    async def sync_chat_by_selector(self, selector: str) -> SyncResult:
        chat = await self.get_chat(selector)
        return await self.sync_chat(chat)

    async def backfill_chat_by_selector(self, selector: str, limit: int) -> SyncResult:
        chat = await self.get_chat(selector)
        return await self.sync_chat(chat, limit=limit, backfill=True)

    async def repair_media_by_selector(self, selector: str) -> MediaRepairResult:
        chat = await self.get_chat(selector)
        return await self.repair_missing_media(chat)

    def _iter_missing_media_ids(self, chat: ChatRecord) -> list[int]:
        message_ids: list[int] = []
        for message in self.writer.load_messages(chat):
            if message.has_media and not message.media_files:
                message_ids.append(message.message_id)
        return message_ids

    async def repair_missing_media(self, chat: ChatRecord, *, batch_size: int = 100) -> MediaRepairResult:
        pending_ids = self._iter_missing_media_ids(chat)
        repaired_messages = 0

        for start in range(0, len(pending_ids), batch_size):
            chunk = pending_ids[start : start + batch_size]
            refreshed = await self.telegram_client.get_messages_by_ids(chat, chunk)
            repaired = [
                message
                for message in refreshed
                if any(media_file.relative_path for media_file in message.media_files)
            ]
            if not repaired:
                continue
            repaired_messages += len(repaired)
            self.writer.write_messages(repaired)

        return MediaRepairResult(
            chat=chat,
            scanned_messages=len(pending_ids),
            repaired_messages=repaired_messages,
        )

    async def repair_missing_media_for_targets(self) -> list[MediaRepairResult]:
        results: list[MediaRepairResult] = []
        for chat in await self.discover_target_chats():
            results.append(await self.repair_missing_media(chat))
        return results

    async def sync_chat(
        self,
        chat: ChatRecord,
        *,
        limit: int | None = None,
        backfill: bool = False,
    ) -> SyncResult:
        state = self.state_store.load_state(chat)
        exported = 0
        newest_message_id = state.last_message_id
        newest_first = backfill or (state.last_message_id == 0 and self.settings.since_date is not None)
        messages_to_write = []

        try:
            iter_kwargs = {
                "limit": limit,
                "reverse": not newest_first,
            }
            if backfill:
                iter_kwargs["offset_id"] = state.last_message_id + 1 if state.last_message_id else 0
            elif state.last_message_id:
                iter_kwargs["min_message_id"] = state.last_message_id

            async for message in self.telegram_client.iter_messages(chat, **iter_kwargs):
                if self.settings.since_date is not None:
                    posted_at = ensure_utc(message.posted_at)
                    if posted_at is not None and posted_at < self.settings.since_date:
                        if newest_first:
                            break
                        continue
                messages_to_write.append(message)
                exported += 1
                newest_message_id = max(newest_message_id, message.message_id)

            self.writer.write_messages(messages_to_write)
            updated_state = state.success(utc_now(), newest_message_id)
            self.state_store.save_state(chat, updated_state)
            self.state_store.write_chat_note(chat, updated_state)
            return SyncResult(
                chat=chat,
                exported_messages=exported,
                last_message_id=updated_state.last_message_id,
                status="ok",
            )
        except Exception as exc:
            errored = state.error(utc_now(), str(exc), newest_message_id)
            self.state_store.save_state(chat, errored)
            self.state_store.write_chat_note(chat, errored)
            raise
