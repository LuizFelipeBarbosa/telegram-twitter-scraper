from __future__ import annotations

from telegram_scraper.models import ChatRecord, ChatType
from telegram_scraper.utils import slugify


def classify_chat(entity: object) -> ChatType:
    if getattr(entity, "self", False):
        return ChatType.SAVED
    if getattr(entity, "broadcast", False):
        return ChatType.CHANNEL
    if getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False):
        return ChatType.GROUP
    if getattr(entity, "first_name", None) is not None or getattr(entity, "last_name", None) is not None:
        return ChatType.DIRECT
    return ChatType.GROUP


def display_name(entity: object, fallback: str) -> str:
    if getattr(entity, "self", False):
        return "Saved Messages"
    first = getattr(entity, "first_name", None) or ""
    last = getattr(entity, "last_name", None) or ""
    full_name = " ".join(part for part in (first, last) if part).strip()
    if full_name:
        return full_name
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    return fallback


def build_chat_record(dialog: object) -> ChatRecord:
    entity = getattr(dialog, "entity", dialog)
    chat_id = int(getattr(dialog, "id", None) or getattr(entity, "id"))
    chat_type = classify_chat(entity)
    title = display_name(entity, getattr(dialog, "name", f"chat-{chat_id}"))
    username = getattr(entity, "username", None)
    if chat_type == ChatType.SAVED:
        slug = "saved-messages"
    else:
        slug = slugify(username or title, fallback=f"chat-{chat_id}")
    return ChatRecord(
        chat_id=chat_id,
        chat_type=chat_type,
        title=title,
        username=username,
        slug=slug,
        entity=entity,
    )


def discover_chats(dialogs: list[object]) -> list[ChatRecord]:
    return [build_chat_record(dialog) for dialog in dialogs]


def filter_chats(
    chats: list[ChatRecord],
    chat_types: tuple[ChatType, ...],
    include_chats: tuple[str, ...],
    exclude_chats: tuple[str, ...],
) -> list[ChatRecord]:
    allowed_types = {chat_type.value for chat_type in chat_types}
    include_set = {value.lower() for value in include_chats}
    exclude_set = {value.lower() for value in exclude_chats}

    selected: list[ChatRecord] = []
    for chat in chats:
        selectors = chat.selectors()
        if chat.chat_type.value not in allowed_types:
            continue
        if include_set and not selectors.intersection(include_set):
            continue
        if selectors.intersection(exclude_set):
            continue
        selected.append(chat)
    return selected


def resolve_chat(chats: list[ChatRecord], selector: str) -> ChatRecord:
    normalized = selector.strip().lower().lstrip("@")
    for chat in chats:
        if normalized in chat.selectors():
            return chat
    raise LookupError(f"chat not found for selector: {selector}")
