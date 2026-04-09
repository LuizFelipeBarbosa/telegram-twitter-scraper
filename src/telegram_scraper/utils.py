from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def slugify(value: str | None, fallback: str = "chat") -> str:
    if not value:
        return fallback
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or fallback


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_z(value: datetime | None) -> str | None:
    converted = ensure_utc(value)
    if converted is None:
        return None
    return converted.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_isoformat_z(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ensure_utc(parsed)


def filename_timestamp(value: datetime) -> str:
    converted = ensure_utc(value)
    if converted is None:
        raise ValueError("timestamp is required")
    return converted.strftime("%Y-%m-%dT%H%M%SZ")


def chat_output_dir(output_root: Path, chat: object) -> Path:
    chat_type = getattr(getattr(chat, "chat_type", None), "value", getattr(chat, "chat_type", ""))
    if chat_type == "saved":
        return output_root / str(chat_type) / "saved-messages"
    return output_root / str(chat_type) / f"{getattr(chat, 'slug')}_{getattr(chat, 'chat_id')}"


def day_output_dir(output_root: Path, chat: object, value: datetime) -> Path:
    converted = ensure_utc(value)
    if converted is None:
        raise ValueError("timestamp is required")
    year = converted.strftime("%Y")
    month = converted.strftime("%Y-%m")
    day = converted.strftime("%Y-%m-%d")
    return chat_output_dir(output_root, chat) / year / month / day


def frontmatter_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def render_frontmatter(pairs: Iterable[tuple[str, Any]]) -> str:
    lines = ["---"]
    for key, value in pairs:
        lines.append(f"{key}: {frontmatter_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def parse_frontmatter_document(content: str) -> tuple[dict[str, object], str]:
    if not content.startswith("---\n"):
        raise ValueError("document is missing YAML frontmatter")
    marker = "\n---\n"
    end_index = content.find(marker, 4)
    if end_index == -1:
        raise ValueError("document has an invalid YAML frontmatter block")

    payload: dict[str, object] = {}
    frontmatter = content[4:end_index]
    for line in frontmatter.splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(": ")
        if not separator:
            raise ValueError(f"invalid frontmatter line: {line}")
        payload[key] = json.loads(value)

    body = content[end_index + len(marker) :]
    return payload, body


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)
