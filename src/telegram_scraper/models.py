from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Set


class ChatType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"
    CHANNEL = "channel"
    SAVED = "saved"


@dataclass(frozen=True)
class ChatRecord:
    chat_id: int
    chat_type: ChatType
    title: str
    username: Optional[str]
    slug: str
    entity: object | None = None

    def selectors(self) -> Set[str]:
        values = {
            str(self.chat_id).lower(),
            self.slug.lower(),
            self.title.lower(),
        }
        if self.username:
            values.add(self.username.lower())
            values.add(self.username.lower().lstrip("@"))
            values.add(f"@{self.username.lower().lstrip('@')}")
        return {value for value in values if value}


@dataclass(frozen=True)
class MediaRecord:
    media_type: str
    relative_path: str | None
    mime_type: str | None = None
    file_name: str | None = None


@dataclass(frozen=True)
class MessageRecord:
    chat: ChatRecord
    message_id: int
    posted_at: datetime
    edited_at: datetime | None
    sender_id: int | None
    sender_name: str | None
    direction: str
    reply_to_message_id: int | None
    has_media: bool
    text: str
    media_files: tuple[MediaRecord, ...] = ()


@dataclass(frozen=True)
class SyncState:
    chat_id: int
    chat_type: str
    chat_slug: str
    last_message_id: int = 0
    last_synced_at: str | None = None
    last_status: str = "never"
    last_error: str | None = None

    @classmethod
    def initial(cls, chat: ChatRecord) -> "SyncState":
        return cls(
            chat_id=chat.chat_id,
            chat_type=chat.chat_type.value,
            chat_slug=chat.slug,
        )

    def success(self, synced_at: str, last_message_id: int) -> "SyncState":
        return SyncState(
            chat_id=self.chat_id,
            chat_type=self.chat_type,
            chat_slug=self.chat_slug,
            last_message_id=max(self.last_message_id, last_message_id),
            last_synced_at=synced_at,
            last_status="ok",
            last_error=None,
        )

    def error(self, synced_at: str, message: str, last_message_id: int | None = None) -> "SyncState":
        return SyncState(
            chat_id=self.chat_id,
            chat_type=self.chat_type,
            chat_slug=self.chat_slug,
            last_message_id=self.last_message_id if last_message_id is None else max(self.last_message_id, last_message_id),
            last_synced_at=synced_at,
            last_status="error",
            last_error=message,
        )


@dataclass(frozen=True)
class SyncResult:
    chat: ChatRecord
    exported_messages: int
    last_message_id: int
    status: str
    error: str | None = None


@dataclass(frozen=True)
class MediaRepairResult:
    chat: ChatRecord
    scanned_messages: int
    repaired_messages: int
