from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from telegram_scraper.models import ChatRecord, ChatType, MessageRecord
from telegram_scraper.snapshot import (
    MESSAGE_COLUMNS,
    build_posts,
    fetch_snapshot,
    load_snapshot,
    posts_to_raw_messages,
    text_preview,
)
from telegram_scraper.telegram_client import TelegramMessageEnvelope

BASE = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


def build_chat(slug="chan", chat_id=7, title="Chan") -> ChatRecord:
    return ChatRecord(chat_id=chat_id, chat_type=ChatType.CHANNEL, title=title, username=slug, slug=slug)


def build_record(chat, message_id, posted_at, *, text="", media_kind="none", grouped_id=None, **extra):
    return MessageRecord(
        chat=chat,
        message_id=message_id,
        posted_at=posted_at,
        edited_at=None,
        sender_id=None,
        sender_name=None,
        direction="incoming",
        reply_to_message_id=extra.pop("reply_to_message_id", None),
        has_media=media_kind != "none",
        text=text,
        media_kind=media_kind,
        grouped_id=grouped_id,
        has_link_preview=media_kind == "webpage",
        **extra,
    )


class FakeClient:
    """Mimics TelegramAccountClient.iter_message_envelopes without honoring the window."""

    def __init__(self, records_by_slug):
        self.records_by_slug = records_by_slug
        self.calls = []

    async def iter_message_envelopes(self, chat, **kwargs):
        self.calls.append((chat.slug, kwargs))
        for record in sorted(self.records_by_slug[chat.slug], key=lambda r: r.posted_at, reverse=True):
            yield TelegramMessageEnvelope(record=record, raw_json={"fwd_from": {"from_id": {"channel_id": 4242}}})


def album_records(chat):
    return [
        build_record(chat, 100, BASE, text="Album caption", media_kind="photo", grouped_id=900, views=10),
        build_record(chat, 101, BASE + timedelta(seconds=1), media_kind="photo", grouped_id=900, views=12),
        build_record(chat, 102, BASE + timedelta(seconds=1), media_kind="photo", grouped_id=900, views=11),
        build_record(chat, 103, BASE + timedelta(hours=1), text="Plain text", views=5, reply_to_message_id=100),
        build_record(chat, 104, BASE + timedelta(hours=2), text="Link https://x.y", media_kind="webpage"),
        build_record(chat, 105, BASE + timedelta(hours=3), text="Clip", media_kind="video", forwards=3),
    ]


def test_fetch_and_load_snapshot_roundtrip(tmp_path):
    chat = build_chat()
    long_text = "word " * 200  # 1,000 chars
    records = album_records(chat) + [build_record(chat, 106, BASE + timedelta(hours=4), text=long_text)]
    client = FakeClient({"chan": records})

    run_dir = asyncio.run(
        fetch_snapshot(
            client,
            [chat],
            start=BASE - timedelta(days=1),
            end=BASE + timedelta(days=1),
            out_dir=tmp_path / "run1",
        )
    )

    assert (run_dir / "chan.parquet").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["run_id"] == "run1"
    assert manifest["channels"][0]["slug"] == "chan"
    assert manifest["channels"][0]["message_count"] == 7
    assert manifest["channels"][0]["min_id"] == 100
    assert manifest["channels"][0]["max_id"] == 106
    assert manifest["channels"][0]["chat_id"] == 7
    assert "fetched_at" in manifest and "package_version" in manifest and "git_sha" in manifest
    slug_call = client.calls[0][1]
    assert slug_call["download_media"] is False
    assert slug_call["since"] == BASE - timedelta(days=1)
    assert slug_call["offset_date"] == BASE + timedelta(days=1)

    df = load_snapshot(run_dir)
    assert list(df.columns) == MESSAGE_COLUMNS
    assert len(df) == 7
    assert str(df["timestamp"].dt.tz) == "UTC"
    assert df.loc[df["message_id"] == 106, "text"].iloc[0] == long_text
    assert len(df.loc[df["message_id"] == 106, "text"].iloc[0]) == 1000
    assert df.loc[df["message_id"] == 106, "text_len"].iloc[0] == 1000
    video = df.loc[df["message_id"] == 105].iloc[0]
    assert video["media_kind"] == "video" and bool(video["has_editorial_media"]) and bool(video["has_media_raw"])
    link = df.loc[df["message_id"] == 104].iloc[0]
    assert link["media_kind"] == "webpage" and not bool(link["has_editorial_media"])
    assert bool(link["has_media_raw"]) and bool(link["has_link_preview"])
    assert df["forwarded_from"].eq(4242).all()
    assert pd.isna(df.loc[df["message_id"] == 100, "reply_to_message_id"].iloc[0])
    assert df.loc[df["message_id"] == 103, "reply_to_message_id"].iloc[0] == 100
    assert list(df["message_id"]) == sorted(df["message_id"])


def test_fetch_snapshot_filters_window_start_inclusive_end_exclusive(tmp_path):
    chat = build_chat()
    start = BASE
    end = BASE + timedelta(hours=2)
    records = [
        build_record(chat, 1, start - timedelta(seconds=1), text="before"),
        build_record(chat, 2, start, text="at start"),
        build_record(chat, 3, start + timedelta(hours=1), text="inside"),
        build_record(chat, 4, end, text="at end"),
        build_record(chat, 5, end + timedelta(hours=1), text="after"),
    ]

    run_dir = asyncio.run(
        fetch_snapshot(FakeClient({"chan": records}), [chat], start=start, end=end, out_dir=tmp_path / "w")
    )

    assert list(load_snapshot(run_dir)["message_id"]) == [2, 3]


def test_fetch_snapshot_multiple_channels_and_empty_channel(tmp_path):
    a, b = build_chat("alpha", 1, "Alpha"), build_chat("beta", 2, "Beta")
    client = FakeClient({"alpha": [build_record(a, 1, BASE, text="a")], "beta": []})

    run_dir = asyncio.run(
        fetch_snapshot(client, [a, b], start=BASE - timedelta(days=1), end=BASE + timedelta(days=1), out_dir=tmp_path / "m")
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert [c["message_count"] for c in manifest["channels"]] == [1, 0]
    assert manifest["channels"][1]["first_ts"] is None
    df = load_snapshot(run_dir)
    assert list(df["channel_slug"]) == ["alpha"]


def test_build_posts_groups_album_into_one_post(tmp_path):
    chat = build_chat()
    run_dir = asyncio.run(
        fetch_snapshot(
            FakeClient({"chan": album_records(chat)}),
            [chat],
            start=BASE - timedelta(days=1),
            end=BASE + timedelta(days=1),
            out_dir=tmp_path / "p",
        )
    )

    posts = build_posts(load_snapshot(run_dir))

    assert len(posts) == 4  # album + text + webpage + video
    album = posts[posts["post_id"] == "chan:g900"].iloc[0]
    assert album["n_items"] == 3
    assert album["text"] == "Album caption"
    assert album["text_len"] == len("Album caption")
    assert bool(album["has_photo"]) and not bool(album["has_video"])
    assert bool(album["has_editorial_media"])
    assert album["media_kinds"] == "photo"
    assert album["first_message_id"] == 100
    assert album["views"] == 12
    assert album["timestamp"] == pd.Timestamp(BASE)

    text_post = posts[posts["post_id"] == "chan:m103"].iloc[0]
    assert text_post["n_items"] == 1
    assert text_post["media_kinds"] == "none"
    assert text_post["reply_to_message_id"] == 100

    link_post = posts[posts["post_id"] == "chan:m104"].iloc[0]
    assert bool(link_post["has_link_preview"]) and not bool(link_post["has_editorial_media"])

    video_post = posts[posts["post_id"] == "chan:m105"].iloc[0]
    assert bool(video_post["has_video"]) and video_post["forwards"] == 3


def test_build_posts_joins_multiple_captions_and_keeps_same_id_in_other_channels_apart():
    a, b = build_chat("alpha", 1), build_chat("beta", 2)
    rows = [
        build_record(a, 1, BASE, text="one", media_kind="photo", grouped_id=5),
        build_record(a, 2, BASE, text="two", media_kind="photo", grouped_id=5),
        build_record(b, 1, BASE, text="other", media_kind="photo", grouped_id=5),
    ]
    messages = _messages_frame(rows)

    posts = build_posts(messages)

    assert sorted(posts["post_id"]) == ["alpha:g5", "beta:g5"]
    assert posts.loc[posts["post_id"] == "alpha:g5", "text"].iloc[0] == "one\n\ntwo"


def _messages_frame(records):
    from telegram_scraper.snapshot import _coerce_messages_frame, _message_row

    rows = [_message_row(r.chat, TelegramMessageEnvelope(record=r, raw_json={})) for r in records]
    return _coerce_messages_frame(pd.DataFrame(rows, columns=MESSAGE_COLUMNS))


def test_posts_to_raw_messages_roundtrip():
    chat = build_chat()
    long_text = "y" * 1000
    records = [
        build_record(chat, 10, BASE, text="Caption", media_kind="photo", grouped_id=1, views=3),
        build_record(chat, 11, BASE, media_kind="photo", grouped_id=1, views=4),
        build_record(chat, 12, BASE + timedelta(hours=1), media_kind="video", text=long_text),
        build_record(chat, 13, BASE + timedelta(hours=2), media_kind="webpage", text="link"),
        build_record(chat, 14, BASE + timedelta(hours=3), media_kind="audio"),
        build_record(chat, 15, BASE + timedelta(hours=4), text="plain"),
    ]

    raws = posts_to_raw_messages(build_posts(_messages_frame(records)))

    by_id = {raw.message_id: raw for raw in raws}
    album = by_id[10]
    assert album.channel_id == 7
    assert album.text == "Caption"
    assert album.media_kind == "photo" and album.grouped_id == 1 and album.views == 4
    assert album.timestamp == BASE and album.timestamp.tzinfo is not None
    assert by_id[12].media_kind == "video" and by_id[12].text == long_text
    assert by_id[13].media_kind == "webpage" and by_id[13].has_link_preview and not by_id[13].has_editorial_media
    assert by_id[14].media_kind == "audio" and by_id[14].text is None and by_id[14].is_media_only
    assert by_id[15].media_kind == "none" and by_id[15].grouped_id is None


def test_text_preview_is_display_only():
    long_text = "z" * 1000

    assert len(text_preview(long_text)) <= 203
    assert text_preview("short") == "short"
    assert text_preview(None) == ""
    assert len(long_text) == 1000
