"""Reproducible on-disk raw snapshots of Telegram channels.

A snapshot is a directory ``<out_dir>/`` holding one parquet file per channel (one row
per Telegram message, FULL text) plus a ``manifest.json``. Analyses should load the
snapshot instead of fetching live, and group album messages into posts with
``build_posts``.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from telegram_scraper import __version__
from telegram_scraper.models import ChatRecord
from telegram_scraper.notebook_pipeline import EDITORIAL_MEDIA_KINDS, RawMessage, _extract_forwarded_from
from telegram_scraper.utils import ensure_utc

MESSAGE_COLUMNS = [
    "channel_slug",
    "channel_title",
    "channel_id",
    "message_id",
    "timestamp",
    "text",
    "text_len",
    "media_kind",
    "has_media_raw",
    "has_editorial_media",
    "has_link_preview",
    "grouped_id",
    "reply_to_message_id",
    "forwarded_from",
    "views",
    "forwards",
    "edited_at",
]

POST_COLUMNS = [
    "channel_slug",
    "channel_title",
    "channel_id",
    "post_id",
    "first_message_id",
    "grouped_id",
    "timestamp",
    "text",
    "text_len",
    "n_items",
    "media_kinds",
    "has_editorial_media",
    "has_photo",
    "has_video",
    "has_link_preview",
    "reply_to_message_id",
    "views",
    "forwards",
]

_INT_COLUMNS = ("channel_id", "message_id", "text_len")
_NULLABLE_INT_COLUMNS = ("grouped_id", "reply_to_message_id", "forwarded_from", "views", "forwards")
_BOOL_COLUMNS = ("has_media_raw", "has_editorial_media", "has_link_preview")
_VIDEO_KINDS = frozenset({"video", "animation"})
_MANIFEST_NAME = "manifest.json"


def text_preview(text: str | None, n: int = 200) -> str:
    """Display-only shortening of a text. Never use the result for analysis."""
    value = text or ""
    if len(value) <= n:
        return value
    return value[:n].rstrip() + "..."


def _git_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = completed.stdout.strip()
    return sha if completed.returncode == 0 and sha else None


def _coerce_messages_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.reindex(columns=MESSAGE_COLUMNS).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["edited_at"] = pd.to_datetime(frame["edited_at"], utc=True)
    for column in _INT_COLUMNS:
        frame[column] = frame[column].astype("int64")
    for column in _NULLABLE_INT_COLUMNS:
        frame[column] = frame[column].astype("Int64")
    for column in _BOOL_COLUMNS:
        frame[column] = frame[column].astype(bool)
    for column in ("channel_slug", "channel_title", "text", "media_kind"):
        frame[column] = frame[column].astype(object)
    return frame


def _message_row(chat: ChatRecord, envelope: Any) -> dict[str, Any]:
    record = envelope.record
    text = record.text or ""
    return {
        "channel_slug": chat.slug,
        "channel_title": chat.title,
        "channel_id": chat.chat_id,
        "message_id": record.message_id,
        "timestamp": ensure_utc(record.posted_at),
        "text": text,
        "text_len": len(text),
        "media_kind": record.media_kind,
        "has_media_raw": bool(record.has_media),
        "has_editorial_media": record.media_kind in EDITORIAL_MEDIA_KINDS,
        "has_link_preview": bool(record.has_link_preview),
        "grouped_id": record.grouped_id,
        "reply_to_message_id": record.reply_to_message_id,
        "forwarded_from": _extract_forwarded_from(envelope.raw_json or {}),
        "views": record.views,
        "forwards": record.forwards,
        "edited_at": ensure_utc(record.edited_at),
    }


def _iso(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


async def fetch_snapshot(
    client: Any,
    chats: Sequence[ChatRecord],
    *,
    start: datetime,
    end: datetime,
    out_dir: Path,
    download_media: bool = False,
    run_id: str | None = None,
) -> Path:
    """Fetch every message with ``start <= date < end`` for each chat and write a snapshot.

    Writes ``out_dir/<slug>.parquet`` per chat and ``out_dir/manifest.json``; returns ``out_dir``.
    ``run_id`` defaults to the directory name.
    """
    start_utc = ensure_utc(start)
    end_utc = ensure_utc(end)
    if start_utc is None or end_utc is None or start_utc >= end_utc:
        raise ValueError("snapshot requires start < end")
    slugs = [chat.slug for chat in chats]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"duplicate channel slugs in snapshot request: {slugs}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc)

    channels_manifest: list[dict[str, Any]] = []
    for chat in chats:
        rows: list[dict[str, Any]] = []
        async for envelope in client.iter_message_envelopes(
            chat,
            reverse=False,
            download_media=download_media,
            offset_date=end_utc,
            since=start_utc,
        ):
            posted_at = ensure_utc(envelope.record.posted_at)
            if posted_at is None or posted_at < start_utc or posted_at >= end_utc:
                continue
            rows.append(_message_row(chat, envelope))

        frame = _coerce_messages_frame(pd.DataFrame(rows, columns=MESSAGE_COLUMNS))
        frame = frame.drop_duplicates(subset=["channel_id", "message_id"], keep="last")
        frame = frame.sort_values(["timestamp", "message_id"]).reset_index(drop=True)
        frame.to_parquet(out_dir / f"{chat.slug}.parquet", index=False, engine="pyarrow")

        channels_manifest.append(
            {
                "slug": chat.slug,
                "title": chat.title,
                "chat_id": chat.chat_id,
                "username": chat.username,
                "message_count": int(len(frame)),
                "min_id": int(frame["message_id"].min()) if len(frame) else None,
                "max_id": int(frame["message_id"].max()) if len(frame) else None,
                "first_ts": _iso(frame["timestamp"].min()) if len(frame) else None,
                "last_ts": _iso(frame["timestamp"].max()) if len(frame) else None,
            }
        )

    manifest = {
        "run_id": run_id or out_dir.name or uuid.uuid4().hex,
        "fetched_at": fetched_at.isoformat(),
        "start": start_utc.isoformat(),
        "end": end_utc.isoformat(),
        "download_media": download_media,
        "git_sha": _git_sha(),
        "package_version": __version__,
        "channels": channels_manifest,
    }
    (out_dir / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_dir


def load_snapshot(run_dir: str | Path) -> pd.DataFrame:
    """Load all channel parquet files of a snapshot into one messages DataFrame."""
    run_path = Path(run_dir)
    files = sorted(run_path.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files found in snapshot directory: {run_path}")
    frames: list[pd.DataFrame] = []
    for path in files:
        frame = pd.read_parquet(path, engine="pyarrow")
        missing = [column for column in MESSAGE_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"{path.name} is missing snapshot columns: {missing}")
        frames.append(_coerce_messages_frame(frame))
    messages_df = pd.concat(frames, ignore_index=True)
    return messages_df.sort_values(["channel_slug", "timestamp", "message_id"]).reset_index(drop=True)


def _join_texts(values: pd.Series) -> str:
    return "\n\n".join(value for value in values if isinstance(value, str) and value.strip())


def _join_kinds(values: pd.Series) -> str:
    kinds = sorted({str(value) for value in values})
    present = [kind for kind in kinds if kind != "none"]
    return ",".join(present) if present else "none"


def build_posts(messages_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse messages into posts: album items sharing a ``grouped_id`` become one post."""
    if messages_df.empty:
        return pd.DataFrame(columns=POST_COLUMNS)

    df = messages_df.sort_values(["channel_slug", "timestamp", "message_id"]).reset_index(drop=True)
    grouped = df["grouped_id"].notna()
    grouped_labels = df["grouped_id"].astype("Int64").astype(str)
    df["post_id"] = (
        df["channel_slug"].astype(str)
        + ":"
        + grouped.map({True: "g", False: "m"})
        + grouped_labels.where(grouped, df["message_id"].astype(str))
    )
    # Album items are ordered by message id so the first item (caption/reply) is stable.
    df = df.sort_values(["post_id", "message_id"], kind="stable").reset_index(drop=True)
    df["_is_photo"] = df["media_kind"] == "photo"
    df["_is_video"] = df["media_kind"].isin(_VIDEO_KINDS)

    by_post = df.groupby("post_id", sort=False)
    aggregated = by_post.agg(
        timestamp=("timestamp", "min"),
        n_items=("message_id", "size"),
        has_editorial_media=("has_editorial_media", "any"),
        has_photo=("_is_photo", "any"),
        has_video=("_is_video", "any"),
        has_link_preview=("has_link_preview", "any"),
        views=("views", "max"),
        forwards=("forwards", "max"),
    )
    aggregated["text"] = by_post["text"].agg(_join_texts)
    aggregated["media_kinds"] = by_post["media_kind"].agg(_join_kinds)

    first_items = df.drop_duplicates("post_id", keep="first").set_index("post_id")
    posts = aggregated.join(
        first_items[["channel_slug", "channel_title", "channel_id", "message_id", "grouped_id", "reply_to_message_id"]]
    ).reset_index()
    posts = posts.rename(columns={"message_id": "first_message_id"})
    posts["text_len"] = posts["text"].str.len().astype("int64")
    for column in ("grouped_id", "reply_to_message_id", "views", "forwards"):
        posts[column] = posts[column].astype("Int64")
    posts["n_items"] = posts["n_items"].astype("int64")
    posts["channel_id"] = posts["channel_id"].astype("int64")
    posts["first_message_id"] = posts["first_message_id"].astype("int64")
    posts = posts[POST_COLUMNS]
    return posts.sort_values(["channel_slug", "timestamp", "first_message_id"]).reset_index(drop=True)


def _post_media_kind(row: Any) -> str:
    if row.has_video:
        return "video"
    if row.has_photo:
        return "photo"
    for kind in str(row.media_kinds).split(","):
        if kind in EDITORIAL_MEDIA_KINDS:
            return kind
    if row.has_link_preview:
        return "webpage"
    return "none"


def _optional_int(value: Any) -> int | None:
    return None if pd.isna(value) else int(value)


def posts_to_raw_messages(posts_df: pd.DataFrame) -> list[RawMessage]:
    """Adapt posts to ``RawMessage`` so existing analysis modules can run on posts."""
    messages: list[RawMessage] = []
    for row in posts_df.itertuples(index=False):
        text = row.text if isinstance(row.text, str) and row.text.strip() else None
        messages.append(
            RawMessage(
                channel_id=int(row.channel_id),
                message_id=int(row.first_message_id),
                timestamp=pd.Timestamp(row.timestamp).to_pydatetime(),
                sender_id=None,
                sender_name=None,
                text=text,
                reply_to_message_id=_optional_int(row.reply_to_message_id),
                raw_json={"post_id": row.post_id, "n_items": int(row.n_items)},
                media_kind=_post_media_kind(row),
                grouped_id=_optional_int(row.grouped_id),
                views=_optional_int(row.views),
                forwards=_optional_int(row.forwards),
                has_link_preview=bool(row.has_link_preview),
            )
        )
    return messages
