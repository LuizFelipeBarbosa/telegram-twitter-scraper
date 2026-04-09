from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from telegram_scraper.models import ChatType
from telegram_scraper.utils import split_csv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values


def parse_since_date(value: str | None) -> datetime | None:
    if not value:
        return None

    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigError(f"invalid SINCE_DATE value: {value}") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Settings:
    api_id: int | None
    api_hash: str
    phone: str
    session_path: Path
    output_root: Path
    since_date: datetime | None
    chat_types: tuple[ChatType, ...]
    include_chats: tuple[str, ...]
    exclude_chats: tuple[str, ...]

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "Settings":
        env_path = Path(env_file)
        file_values = load_dotenv(env_path)
        values = {**file_values, **os.environ}
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "Settings":
        chat_types_raw = split_csv(values.get("CHAT_TYPES")) or (
            ChatType.GROUP.value,
            ChatType.CHANNEL.value,
            ChatType.SAVED.value,
        )
        try:
            chat_types = tuple(ChatType(value.lower()) for value in chat_types_raw)
        except ValueError as exc:
            raise ConfigError(f"invalid CHAT_TYPES value: {exc}") from exc

        api_id_raw = values.get("TG_API_ID")
        api_id = int(api_id_raw) if api_id_raw else None

        return cls(
            api_id=api_id,
            api_hash=values.get("TG_API_HASH", "").strip(),
            phone=values.get("TG_PHONE", "").strip(),
            session_path=Path(values.get("SESSION_PATH", "sessions/telegram")),
            output_root=Path(values.get("OUTPUT_ROOT", "/Volumes/T7/theVault/raw/telegram")),
            since_date=parse_since_date(values.get("SINCE_DATE")),
            chat_types=chat_types,
            include_chats=tuple(item.lower() for item in split_csv(values.get("INCLUDE_CHATS"))),
            exclude_chats=tuple(item.lower() for item in split_csv(values.get("EXCLUDE_CHATS"))),
        )

    def require_credentials(self) -> None:
        missing: list[str] = []
        if self.api_id is None:
            missing.append("TG_API_ID")
        if not self.api_hash:
            missing.append("TG_API_HASH")
        if not self.phone:
            missing.append("TG_PHONE")
        if missing:
            joined = ", ".join(missing)
            raise ConfigError(f"missing required settings: {joined}")

    def validate_output_root(self) -> None:
        if not self.output_root.exists():
            raise ConfigError(f"output root does not exist: {self.output_root}")
        if not self.output_root.is_dir():
            raise ConfigError(f"output root is not a directory: {self.output_root}")
        if not os.access(self.output_root, os.W_OK):
            raise ConfigError(f"output root is not writable: {self.output_root}")
