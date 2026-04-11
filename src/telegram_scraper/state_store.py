from __future__ import annotations

import json
from pathlib import Path

from telegram_scraper.models import ChatRecord, ChatType, SyncState
from telegram_scraper.utils import (
    atomic_write_text,
    chat_output_dir,
    parse_frontmatter_document,
    render_frontmatter,
)


class StateStore:
    def __init__(self, output_root: Path, messages_db_path: Path | None = None):
        self.output_root = output_root
        self._messages_db_path = messages_db_path or (output_root / "telegram_messages.db")

    def chat_type_dir(self, chat: ChatRecord) -> Path:
        return self.output_root / chat.chat_type.value

    def chat_dir(self, chat: ChatRecord) -> Path:
        return chat_output_dir(self.output_root, chat)

    def state_path(self, chat: ChatRecord) -> Path:
        return self.chat_dir(chat) / "_state.json"

    def chat_note_path(self, chat: ChatRecord) -> Path:
        return self.chat_dir(chat) / "_chat.md"

    def messages_db_path(self) -> Path:
        return self._messages_db_path

    def legacy_messages_db_path(self, chat: ChatRecord) -> Path:
        return self.chat_dir(chat) / "_messages.db"

    def legacy_messages_json_path(self, chat: ChatRecord) -> Path:
        return self.chat_dir(chat) / "_messages.json"

    def load_state(self, chat: ChatRecord) -> SyncState:
        path = self.state_path(chat)
        if not path.exists():
            return SyncState.initial(chat)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SyncState(
            chat_id=int(payload["chat_id"]),
            chat_type=str(payload["chat_type"]),
            chat_slug=str(payload["chat_slug"]),
            last_message_id=int(payload.get("last_message_id", 0)),
            last_synced_at=payload.get("last_synced_at"),
            last_status=str(payload.get("last_status", "never")),
            last_error=payload.get("last_error"),
        )

    def save_state(self, chat: ChatRecord, state: SyncState) -> Path:
        payload = {
            "chat_id": state.chat_id,
            "chat_type": state.chat_type,
            "chat_slug": state.chat_slug,
            "last_message_id": state.last_message_id,
            "last_synced_at": state.last_synced_at,
            "last_status": state.last_status,
            "last_error": state.last_error,
        }
        path = self.state_path(chat)
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
        return path

    def write_chat_note(self, chat: ChatRecord, state: SyncState) -> Path:
        metadata = render_frontmatter(
            (
                ("chat_id", chat.chat_id),
                ("chat_type", chat.chat_type.value),
                ("chat_title", chat.title),
                ("chat_username", chat.username),
                ("chat_slug", chat.slug),
                ("last_synced_at", state.last_synced_at),
                ("last_status", state.last_status),
                ("source", "telegram"),
            )
        )
        body = "\n".join(
            [
                metadata,
                "",
                f"# {chat.title}",
                "",
                f"- Chat type: `{chat.chat_type.value}`",
                f"- Chat ID: `{chat.chat_id}`",
                f"- Username: `{chat.username or 'none'}`",
                f"- Folder: `{self.chat_dir(chat)}`",
            ]
        )
        path = self.chat_note_path(chat)
        atomic_write_text(path, body + "\n")
        return path

    def iter_chat_dirs(self) -> list[Path]:
        chat_dirs: list[Path] = []
        for chat_type in ChatType:
            type_dir = self.output_root / chat_type.value
            if not type_dir.exists():
                continue
            for child in type_dir.iterdir():
                if child.is_dir():
                    chat_dirs.append(child)
        return chat_dirs

    def load_chat_from_dir(self, chat_dir: Path) -> ChatRecord | None:
        chat_note = chat_dir / "_chat.md"
        if chat_note.exists():
            payload, _ = parse_frontmatter_document(chat_note.read_text(encoding="utf-8"))
            chat_type_raw = str(payload.get("chat_type") or "")
            try:
                chat_type = ChatType(chat_type_raw)
            except ValueError:
                return None
            return ChatRecord(
                chat_id=int(payload["chat_id"]),
                chat_type=chat_type,
                title=str(payload.get("chat_title") or chat_dir.name),
                username=str(payload["chat_username"]) if payload.get("chat_username") is not None else None,
                slug=str(payload.get("chat_slug") or chat_dir.name),
            )

        state_path = chat_dir / "_state.json"
        if not state_path.exists():
            return None

        payload = json.loads(state_path.read_text(encoding="utf-8"))
        chat_type_raw = str(payload.get("chat_type") or "")
        try:
            chat_type = ChatType(chat_type_raw)
        except ValueError:
            return None

        return ChatRecord(
            chat_id=int(payload["chat_id"]),
            chat_type=chat_type,
            title=chat_dir.name,
            username=None,
            slug=str(payload.get("chat_slug") or chat_dir.name),
        )

    def iter_archived_chats(self) -> list[ChatRecord]:
        chats: list[ChatRecord] = []
        for chat_dir in self.iter_chat_dirs():
            chat = self.load_chat_from_dir(chat_dir)
            if chat is not None:
                chats.append(chat)
        return chats
