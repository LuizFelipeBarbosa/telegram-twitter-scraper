from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from telegram_scraper.models import ChatRecord, MediaRecord, MessageRecord
from telegram_scraper.state_store import StateStore
from telegram_scraper.utils import (
    isoformat_z,
    parse_isoformat_z,
)


class MarkdownWriter:
    """Persists chat notes and raw messages for incremental scraping."""

    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    def chat_store_path(self) -> Path:
        return self.state_store.messages_db_path()

    def legacy_chat_db_path(self, chat: ChatRecord) -> Path:
        return self.state_store.legacy_messages_db_path(chat)

    def legacy_chat_json_path(self, chat: ChatRecord) -> Path:
        return self.state_store.legacy_messages_json_path(chat)

    def _connect(self) -> sqlite3.Connection:
        path = self.chat_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        self._ensure_schema(connection)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat_position ON messages (chat_id, position)"
        )

    def _serialize_media_file(self, media_file: MediaRecord) -> dict[str, object]:
        return {
            "media_type": media_file.media_type,
            "relative_path": media_file.relative_path,
            "mime_type": media_file.mime_type,
            "file_name": media_file.file_name,
        }

    def _serialize_message(self, message: MessageRecord) -> dict[str, object]:
        return {
            "message_id": message.message_id,
            "posted_at": isoformat_z(message.posted_at),
            "edited_at": isoformat_z(message.edited_at),
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "direction": message.direction,
            "reply_to_message_id": message.reply_to_message_id,
            "has_media": message.has_media,
            "text": message.text,
            "media_files": [self._serialize_media_file(media_file) for media_file in message.media_files],
        }

    def _deserialize_media_file(self, payload: dict[str, object]) -> MediaRecord:
        return MediaRecord(
            media_type=str(payload.get("media_type") or "file"),
            relative_path=str(payload["relative_path"]) if payload.get("relative_path") is not None else None,
            mime_type=str(payload["mime_type"]) if payload.get("mime_type") is not None else None,
            file_name=str(payload["file_name"]) if payload.get("file_name") is not None else None,
        )

    def _deserialize_message(self, chat: ChatRecord, payload: dict[str, object]) -> MessageRecord:
        posted_at = parse_isoformat_z(payload.get("posted_at"))  # type: ignore[arg-type]
        if posted_at is None:
            raise ValueError("message payload is missing posted_at")
        return MessageRecord(
            chat=chat,
            message_id=int(payload["message_id"]),
            posted_at=posted_at,
            edited_at=parse_isoformat_z(payload.get("edited_at")),  # type: ignore[arg-type]
            sender_id=int(payload["sender_id"]) if payload.get("sender_id") is not None else None,
            sender_name=str(payload["sender_name"]) if payload.get("sender_name") is not None else None,
            direction=str(payload.get("direction") or "incoming"),
            reply_to_message_id=(
                int(payload["reply_to_message_id"]) if payload.get("reply_to_message_id") is not None else None
            ),
            has_media=bool(payload.get("has_media", False)),
            text=str(payload.get("text") or ""),
            media_files=tuple(
                self._deserialize_media_file(item)
                for item in payload.get("media_files", [])
                if isinstance(item, dict)
            ),
        )

    def _load_legacy_json_messages(self, chat: ChatRecord) -> list[MessageRecord]:
        store_path = self.legacy_chat_json_path(chat)
        if not store_path.exists():
            return []
        payload = json.loads(store_path.read_text(encoding="utf-8"))
        return [
            self._deserialize_message(chat, item)
            for item in payload.get("messages", [])
            if isinstance(item, dict)
        ]

    def _load_legacy_database_messages(self, chat: ChatRecord) -> list[MessageRecord]:
        store_path = self.legacy_chat_db_path(chat)
        if not store_path.exists():
            return []
        with sqlite3.connect(store_path) as connection:
            rows = connection.execute("SELECT payload FROM messages ORDER BY position").fetchall()
        return [self._deserialize_message(chat, json.loads(row[0])) for row in rows]

    def _load_database_messages(self, chat: ChatRecord) -> list[MessageRecord]:
        store_path = self.chat_store_path()
        if not store_path.exists():
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM messages WHERE chat_id = ? ORDER BY position",
                (chat.chat_id,),
            ).fetchall()
        return [self._deserialize_message(chat, json.loads(row[0])) for row in rows]

    def _migrate_legacy_store(self, chat: ChatRecord) -> None:
        if self._load_database_messages(chat):
            return
        legacy_messages = self._load_legacy_database_messages(chat)
        if not legacy_messages:
            legacy_messages = self._load_legacy_json_messages(chat)
        if not legacy_messages:
            return
        self._save_messages(chat, legacy_messages)

    def load_messages(self, chat: ChatRecord) -> list[MessageRecord]:
        self._migrate_legacy_store(chat)
        return self._load_database_messages(chat)

    def _save_messages(self, chat: ChatRecord, messages: list[MessageRecord]) -> Path:
        path = self.chat_store_path()
        rows = [
            (
                chat.chat_id,
                message.message_id,
                position,
                json.dumps(self._serialize_message(message)),
            )
            for position, message in enumerate(messages)
        ]
        with self._connect() as connection:
            connection.execute("DELETE FROM messages WHERE chat_id = ?", (chat.chat_id,))
            connection.executemany(
                "INSERT INTO messages (chat_id, message_id, position, payload) VALUES (?, ?, ?, ?)",
                rows,
            )
            connection.commit()
        return path

    def _merge_messages(
        self,
        existing_messages: list[MessageRecord],
        incoming_messages: list[MessageRecord],
    ) -> list[MessageRecord]:
        merged_messages = list(existing_messages)
        positions = {message.message_id: index for index, message in enumerate(merged_messages)}
        for message in incoming_messages:
            existing_index = positions.get(message.message_id)
            if existing_index is None:
                positions[message.message_id] = len(merged_messages)
                merged_messages.append(message)
            else:
                merged_messages[existing_index] = message
        return merged_messages

    def write_message(self, message: MessageRecord) -> Path:
        return self.write_messages([message])[message.chat.chat_id]

    def write_messages(self, messages: list[MessageRecord]) -> dict[int, Path]:
        grouped: dict[int, tuple[ChatRecord, list[MessageRecord]]] = {}
        for message in messages:
            if message.chat.chat_id not in grouped:
                grouped[message.chat.chat_id] = (message.chat, [])
            grouped[message.chat.chat_id][1].append(message)

        paths: dict[int, Path] = {}
        for chat_id, (chat, chat_messages) in grouped.items():
            existing_messages = self.load_messages(chat)
            merged_messages = self._merge_messages(existing_messages, chat_messages)
            paths[chat_id] = self._save_messages(chat, merged_messages)
        return paths
