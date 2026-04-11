from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

from telegram_scraper.models import ChatRecord, MediaRecord, MessageRecord
from telegram_scraper.utils import chat_output_dir


class TelegramClientError(RuntimeError):
    """Raised when Telethon is unavailable or Telegram operations fail."""


@dataclass(frozen=True)
class TelegramMessageEnvelope:
    record: MessageRecord
    raw_json: dict[str, object]


def _sender_name(message: object) -> str | None:
    sender = getattr(message, "sender", None)
    if sender is not None:
        first = getattr(sender, "first_name", None) or ""
        last = getattr(sender, "last_name", None) or ""
        name = " ".join(part for part in (first, last) if part).strip()
        if name:
            return name
        username = getattr(sender, "username", None)
        if username:
            return username
    post_author = getattr(message, "post_author", None)
    if post_author:
        return str(post_author)
    return None


def _reply_to_id(message: object) -> int | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is not None and getattr(reply_to, "reply_to_msg_id", None) is not None:
        return int(reply_to.reply_to_msg_id)
    value = getattr(message, "reply_to_msg_id", None)
    return int(value) if value is not None else None


def _raw_message_payload(message: object) -> dict[str, object]:
    if hasattr(message, "to_dict"):
        payload = message.to_dict()
        if isinstance(payload, dict):
            return payload
    if hasattr(message, "to_json"):
        raw_json = message.to_json()
        if isinstance(raw_json, str):
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
    return {
        "id": int(getattr(message, "id")),
        "date": getattr(message, "date").isoformat() if getattr(message, "date", None) is not None else None,
        "message": getattr(message, "message", "") or "",
        "reply_to_msg_id": _reply_to_id(message),
        "sender_id": getattr(message, "sender_id", None),
    }


def _event_chat_id(event: object) -> int | None:
    value = getattr(event, "chat_id", None)
    if value is not None:
        return int(value)
    message = getattr(event, "message", None)
    if message is None:
        return None
    peer_id = getattr(message, "peer_id", None)
    for attribute in ("channel_id", "chat_id", "user_id"):
        nested = getattr(peer_id, attribute, None)
        if nested is not None:
            return int(nested)
    return None


def normalize_message(chat: ChatRecord, message: object, *, media_files: tuple[MediaRecord, ...] = ()) -> MessageRecord:
    return MessageRecord(
        chat=chat,
        message_id=int(getattr(message, "id")),
        posted_at=getattr(message, "date"),
        edited_at=getattr(message, "edit_date", None),
        sender_id=getattr(message, "sender_id", None),
        sender_name=_sender_name(message),
        direction="outgoing" if getattr(message, "out", False) else "incoming",
        reply_to_message_id=_reply_to_id(message),
        has_media=getattr(message, "media", None) is not None,
        text=getattr(message, "message", "") or "",
        media_files=media_files,
    )


def _normalize_image_extension(message: object) -> str:
    file = getattr(message, "file", None)
    ext = getattr(file, "ext", None) or ""
    if not ext:
        name = getattr(file, "name", None)
        ext = Path(name).suffix if name else ""
    if not ext:
        mime_type = getattr(file, "mime_type", None) or getattr(getattr(message, "document", None), "mime_type", None)
        if mime_type:
            subtype = str(mime_type).split("/", 1)[-1].split("+", 1)[0].lower()
            ext = ".jpg" if subtype == "jpeg" else f".{subtype}"
    if not ext:
        ext = ".jpg"
    if not ext.startswith("."):
        ext = f".{ext}"
    return ext.lower()


def _is_image_message(message: object) -> bool:
    if getattr(message, "photo", None) is not None:
        return True
    document = getattr(message, "document", None)
    if document is None:
        return False
    file = getattr(message, "file", None)
    mime_type = getattr(file, "mime_type", None) or getattr(document, "mime_type", None)
    return bool(mime_type and str(mime_type).startswith("image/"))


@dataclass
class TelegramAccountClient:
    api_id: int
    api_hash: str
    session_path: Path
    output_root: Path
    phone: str
    _client: object | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        try:
            from telethon import TelegramClient  # type: ignore
        except ImportError as exc:
            raise TelegramClientError(
                "Telethon is not installed. Install project dependencies before using the CLI."
            ) from exc

        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = TelegramClient(str(self.session_path), self.api_id, self.api_hash)
        await self._client.connect()

    async def disconnect(self) -> None:
        if self._client is None:
            return
        await self._client.disconnect()
        self._client = None

    async def login(self) -> object:
        await self.connect()
        assert self._client is not None
        await self._client.start(phone=self.phone)
        me = await self._client.get_me()
        if me is None:
            raise TelegramClientError("Telegram authorization did not return a user.")
        return me

    async def get_dialogs(self) -> list[object]:
        await self.connect()
        assert self._client is not None
        dialogs: list[object] = []
        async for dialog in self._client.iter_dialogs():
            dialogs.append(dialog)
        return dialogs

    async def _download_message_media(self, chat: ChatRecord, message: object) -> tuple[MediaRecord, ...]:
        if not _is_image_message(message):
            return ()

        chat_dir = chat_output_dir(self.output_root, chat)
        media_dir = chat_dir / "media"
        ext = _normalize_image_extension(message)
        download_path = media_dir / f"msg-{int(getattr(message, 'id'))}{ext}"
        relative_path = download_path.relative_to(chat_dir).as_posix()
        file = getattr(message, "file", None)
        mime_type = getattr(file, "mime_type", None) or getattr(getattr(message, "document", None), "mime_type", None)

        if download_path.exists():
            return (
                MediaRecord(
                    media_type="image",
                    relative_path=relative_path,
                    mime_type=str(mime_type) if mime_type is not None else None,
                    file_name=download_path.name,
                ),
            )

        media_dir.mkdir(parents=True, exist_ok=True)
        try:
            downloaded = await message.download_media(file=str(download_path))
        except Exception:
            return (
                MediaRecord(
                    media_type="image",
                    relative_path=None,
                    mime_type=str(mime_type) if mime_type is not None else None,
                    file_name=download_path.name,
                ),
            )

        resolved_path = Path(str(downloaded)) if downloaded else download_path
        return (
            MediaRecord(
                media_type="image",
                relative_path=resolved_path.relative_to(chat_dir).as_posix() if resolved_path.exists() else None,
                mime_type=str(mime_type) if mime_type is not None else None,
                file_name=resolved_path.name,
            ),
        )

    async def iter_messages(
        self,
        chat: ChatRecord,
        *,
        min_message_id: int = 0,
        limit: int | None = None,
        reverse: bool = True,
        offset_id: int = 0,
    ) -> AsyncIterator[MessageRecord]:
        await self.connect()
        assert self._client is not None
        entity = chat.entity or chat.chat_id
        async for message in self._client.iter_messages(
            entity,
            limit=limit,
            min_id=min_message_id,
            reverse=reverse,
            offset_id=offset_id,
        ):
            media_files = await self._download_message_media(chat, message)
            yield normalize_message(chat, message, media_files=media_files)

    async def iter_message_envelopes(
        self,
        chat: ChatRecord,
        *,
        min_message_id: int = 0,
        limit: int | None = None,
        reverse: bool = True,
        offset_id: int = 0,
    ) -> AsyncIterator[TelegramMessageEnvelope]:
        await self.connect()
        assert self._client is not None
        entity = chat.entity or chat.chat_id
        async for message in self._client.iter_messages(
            entity,
            limit=limit,
            min_id=min_message_id,
            reverse=reverse,
            offset_id=offset_id,
        ):
            media_files = await self._download_message_media(chat, message)
            yield TelegramMessageEnvelope(
                record=normalize_message(chat, message, media_files=media_files),
                raw_json=_raw_message_payload(message),
            )

    async def get_messages_by_ids(self, chat: ChatRecord, ids: list[int]) -> list[MessageRecord]:
        if not ids:
            return []

        await self.connect()
        assert self._client is not None
        entity = chat.entity or chat.chat_id
        fetched = await self._client.get_messages(entity, ids=ids)
        if fetched is None:
            return []
        if not isinstance(fetched, list):
            fetched = [fetched]

        messages: list[MessageRecord] = []
        for message in fetched:
            if message is None:
                continue
            media_files = await self._download_message_media(chat, message)
            messages.append(normalize_message(chat, message, media_files=media_files))
        return messages

    async def get_message_envelopes_by_ids(self, chat: ChatRecord, ids: list[int]) -> list[TelegramMessageEnvelope]:
        if not ids:
            return []

        await self.connect()
        assert self._client is not None
        entity = chat.entity or chat.chat_id
        fetched = await self._client.get_messages(entity, ids=ids)
        if fetched is None:
            return []
        if not isinstance(fetched, list):
            fetched = [fetched]

        messages: list[TelegramMessageEnvelope] = []
        for message in fetched:
            if message is None:
                continue
            media_files = await self._download_message_media(chat, message)
            messages.append(
                TelegramMessageEnvelope(
                    record=normalize_message(chat, message, media_files=media_files),
                    raw_json=_raw_message_payload(message),
                )
            )
        return messages

    async def listen_channel_messages(
        self,
        chats: list[ChatRecord],
        handler: Callable[[TelegramMessageEnvelope], Awaitable[None]],
    ) -> None:
        await self.connect()
        assert self._client is not None
        if not chats:
            return
        try:
            from telethon import events  # type: ignore
        except ImportError as exc:
            raise TelegramClientError(
                "Telethon is not installed. Install project dependencies before using the CLI."
            ) from exc

        chat_map = {chat.chat_id: chat for chat in chats}
        entities = [chat.entity or chat.chat_id for chat in chats]
        stop_signal = asyncio.Event()

        @self._client.on(events.NewMessage(chats=entities))
        async def _listener(event: object) -> None:
            chat_id = _event_chat_id(event)
            if chat_id is None or chat_id not in chat_map:
                return
            message = getattr(event, "message", None)
            if message is None:
                return
            chat = chat_map[chat_id]
            media_files = await self._download_message_media(chat, message)
            await handler(
                TelegramMessageEnvelope(
                    record=normalize_message(chat, message, media_files=media_files),
                    raw_json=_raw_message_payload(message),
                )
            )

        await stop_signal.wait()
