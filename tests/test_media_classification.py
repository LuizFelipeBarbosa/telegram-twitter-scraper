from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telegram_scraper.models import ChatRecord, ChatType
from telegram_scraper.notebook_pipeline import RawMessage, normalize_message_record
from telegram_scraper.telegram_client import classify_media_kind, normalize_message


# Fakes named after the Telethon classes; classification is by class name.
class MessageMediaPhoto:
    pass


class MessageMediaWebPage:
    def __init__(self, photo=None):
        self.webpage = SimpleNamespace(photo=photo)


class MessageMediaPoll:
    pass


class MessageMediaGeo:
    pass


class MessageMediaContact:
    pass


class MessageMediaEmpty:
    pass


class MessageMediaDocument:
    def __init__(self, mime_type, attributes=()):
        self.document = SimpleNamespace(mime_type=mime_type, attributes=list(attributes))


class DocumentAttributeVideo:
    def __init__(self, round_message=False):
        self.round_message = round_message


class DocumentAttributeAnimated:
    pass


class DocumentAttributeAudio:
    def __init__(self, voice=False):
        self.voice = voice


class DocumentAttributeSticker:
    pass


class DocumentAttributeFilename:
    pass


def fake_message(media, **extra):
    base = dict(
        id=10,
        date=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        edit_date=None,
        sender_id=None,
        out=False,
        reply_to=None,
        message="",
        media=media,
        # Telethon's message.photo is truthy for link previews with a photo; must be ignored.
        photo=object() if isinstance(media, (MessageMediaPhoto, MessageMediaWebPage)) else None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def build_chat() -> ChatRecord:
    return ChatRecord(chat_id=7, chat_type=ChatType.CHANNEL, title="Chan", username="chan", slug="chan")


@pytest.mark.parametrize(
    "media, expected",
    [
        (None, "none"),
        (MessageMediaEmpty(), "none"),
        (MessageMediaPhoto(), "photo"),
        (MessageMediaWebPage(photo=object()), "webpage"),
        (MessageMediaWebPage(), "webpage"),
        (MessageMediaPoll(), "poll"),
        (MessageMediaGeo(), "geo"),
        (MessageMediaContact(), "other"),
        (MessageMediaDocument("video/mp4", [DocumentAttributeVideo()]), "video"),
        (MessageMediaDocument("video/mp4", [DocumentAttributeVideo(round_message=True)]), "video"),
        (MessageMediaDocument("video/webm"), "video"),
        (MessageMediaDocument("video/mp4", [DocumentAttributeVideo(), DocumentAttributeAnimated()]), "animation"),
        (MessageMediaDocument("image/gif"), "animation"),
        (MessageMediaDocument("audio/mpeg", [DocumentAttributeAudio(voice=False)]), "audio"),
        (MessageMediaDocument("audio/ogg", [DocumentAttributeAudio(voice=True)]), "voice"),
        (MessageMediaDocument("image/jpeg", [DocumentAttributeFilename()]), "photo"),
        (MessageMediaDocument("image/webp", [DocumentAttributeSticker()]), "other"),
        (MessageMediaDocument("application/pdf", [DocumentAttributeFilename()]), "document"),
    ],
)
def test_classify_media_kind(media, expected):
    assert classify_media_kind(fake_message(media)) == expected


def test_webpage_with_preview_photo_is_not_editorial_media():
    message = fake_message(MessageMediaWebPage(photo=object()), message="read https://example.com")

    record = normalize_message(build_chat(), message)
    raw = normalize_message_record(record)

    assert record.has_media is True  # raw truth
    assert record.media_kind == "webpage"
    assert record.has_link_preview is True
    assert raw.has_editorial_media is False
    assert raw.is_media_only is False


def test_normalize_message_populates_new_fields():
    message = fake_message(
        MessageMediaDocument("video/mp4", [DocumentAttributeVideo()]),
        grouped_id=555,
        views=1200,
        forwards=14,
    )

    record = normalize_message(build_chat(), message)

    assert record.media_kind == "video"
    assert record.grouped_id == 555
    assert record.views == 1200
    assert record.forwards == 14
    assert record.has_link_preview is False
    assert record.has_media is True


def test_normalize_message_defaults_for_plain_text():
    record = normalize_message(build_chat(), fake_message(None, message="hello"))

    assert record.media_kind == "none"
    assert record.grouped_id is None
    assert record.views is None
    assert record.has_media is False


def test_has_editorial_media_and_is_media_only():
    ts = datetime(2026, 4, 7, tzinfo=timezone.utc)

    def raw(kind, text=None):
        return RawMessage(
            channel_id=1, message_id=1, timestamp=ts, sender_id=None, sender_name=None, text=text, media_kind=kind
        )

    for kind in ("photo", "video", "animation", "audio", "voice", "document"):
        assert raw(kind).has_editorial_media is True
        assert raw(kind).is_media_only is True
        assert raw(kind, "caption").is_media_only is False
    for kind in ("none", "webpage", "poll", "geo", "other"):
        assert raw(kind).has_editorial_media is False
        assert raw(kind).is_media_only is False


def test_long_text_survives_normalization():
    long_text = "x" * 1000

    record = normalize_message(build_chat(), fake_message(None, message=long_text))
    raw = normalize_message_record(record)

    assert len(record.text) == 1000
    assert raw.text == long_text
