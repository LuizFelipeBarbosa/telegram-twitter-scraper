from __future__ import annotations

import json
import time
from base64 import b64encode
from dataclasses import dataclass
from datetime import date, datetime

from telegram_scraper.kg.models import MediaRef, RawMessage
from telegram_scraper.utils import parse_isoformat_z


@dataclass(frozen=True)
class RedisStreamEntry:
    entry_id: str
    payload: RawMessage


class RedisRawMessageStream:
    def __init__(self, redis_url: str, *, stream_key: str, consumer_group: str, retention_ms: int):
        self.redis_url = redis_url
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.retention_ms = retention_ms

    def _client(self):
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError("redis is not installed. Install project dependencies before using KG commands.") from exc
        return redis.Redis.from_url(self.redis_url, decode_responses=True)

    def ensure_group(self) -> None:
        client = self._client()
        try:
            client.xgroup_create(name=self.stream_key, groupname=self.consumer_group, id="0", mkstream=True)
        except Exception as exc:  # pragma: no cover - redis library response classes vary by version.
            if "BUSYGROUP" not in str(exc):
                raise

    def add(self, message: RawMessage) -> str:
        client = self._client()
        entry_id = client.xadd(
            self.stream_key,
            {
                "channel_id": str(message.channel_id),
                "message_id": str(message.message_id),
                "payload": json.dumps(_serialize_raw_message(message)),
            },
        )
        cutoff = int(time.time() * 1000) - self.retention_ms
        try:
            client.xtrim(self.stream_key, minid=f"{cutoff}-0", approximate=True)
        except TypeError:  # pragma: no cover - older redis-py versions use different kwargs.
            pass
        return str(entry_id)

    def read(self, *, consumer_name: str, count: int) -> list[RedisStreamEntry]:
        client = self._client()
        response = client.xreadgroup(
            groupname=self.consumer_group,
            consumername=consumer_name,
            streams={self.stream_key: "0"},
            count=count,
        )
        if not _has_stream_items(response):
            response = client.xreadgroup(
                groupname=self.consumer_group,
                consumername=consumer_name,
                streams={self.stream_key: ">"},
                count=count,
                block=1000,
            )
        entries: list[RedisStreamEntry] = []
        for _, items in response:
            for entry_id, fields in items:
                payload = json.loads(fields["payload"])
                entries.append(RedisStreamEntry(entry_id=str(entry_id), payload=_deserialize_raw_message(payload)))
        return entries

    def ack(self, entry_ids: list[str]) -> None:
        if not entry_ids:
            return
        client = self._client()
        client.xack(self.stream_key, self.consumer_group, *entry_ids)


def _serialize_raw_message(message: RawMessage) -> dict[str, object]:
    return {
        "channel_id": message.channel_id,
        "message_id": message.message_id,
        "timestamp": message.timestamp.isoformat().replace("+00:00", "Z"),
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "text": message.text,
        "media_refs": [
            {
                "media_type": media.media_type,
                "storage_path": media.storage_path,
                "mime_type": media.mime_type,
                "file_name": media.file_name,
            }
            for media in message.media_refs
        ],
        "forwarded_from": message.forwarded_from,
        "reply_to_message_id": message.reply_to_message_id,
        "raw_json": _json_ready(message.raw_json),
    }


def _has_stream_items(response: object) -> bool:
    if not isinstance(response, list):
        return False
    for item in response:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        entries = item[1]
        if entries:
            return True
    return False


def _json_ready(value: object) -> object:
    if isinstance(value, (bytes, bytearray)):
        return {"__type__": "bytes", "base64": b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _deserialize_raw_message(payload: dict[str, object]) -> RawMessage:
    timestamp = parse_isoformat_z(str(payload["timestamp"]))
    if timestamp is None:
        raise ValueError("stream payload is missing timestamp")
    media_refs = tuple(
        MediaRef(
            media_type=str(item.get("media_type") or "file"),
            storage_path=str(item["storage_path"]) if item.get("storage_path") is not None else None,
            mime_type=str(item["mime_type"]) if item.get("mime_type") is not None else None,
            file_name=str(item["file_name"]) if item.get("file_name") is not None else None,
        )
        for item in payload.get("media_refs", [])
        if isinstance(item, dict)
    )
    return RawMessage(
        channel_id=int(payload["channel_id"]),
        message_id=int(payload["message_id"]),
        timestamp=timestamp,
        sender_id=int(payload["sender_id"]) if payload.get("sender_id") is not None else None,
        sender_name=str(payload["sender_name"]) if payload.get("sender_name") is not None else None,
        text=str(payload["text"]) if payload.get("text") is not None else None,
        media_refs=media_refs,
        forwarded_from=int(payload["forwarded_from"]) if payload.get("forwarded_from") is not None else None,
        reply_to_message_id=(
            int(payload["reply_to_message_id"]) if payload.get("reply_to_message_id") is not None else None
        ),
        raw_json=dict(payload.get("raw_json") or {}),
    )
