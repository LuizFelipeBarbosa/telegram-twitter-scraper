from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("seaborn")
import matplotlib.pyplot as plt

from telegram_scraper.analysis.cadence import MessagingCadenceConfig, run_messaging_cadence_analysis
from telegram_scraper.notebook_pipeline import MediaRef, RawMessage


MEDIA = (MediaRef(media_type="image", storage_path="media/example.jpg", mime_type="image/jpeg", file_name="example.jpg"),)


def build_message(
    *,
    message_id: int,
    timestamp: datetime,
    text: str | None = None,
    has_media: bool = False,
    english_text: str | None = None,
) -> RawMessage:
    return RawMessage(
        channel_id=99,
        message_id=message_id,
        timestamp=timestamp,
        sender_id=None,
        sender_name=None,
        text=text,
        media_refs=MEDIA if has_media else (),
        media_kind="photo" if has_media else "none",
        raw_json={},
        english_text=english_text,
    )


def test_run_messaging_cadence_analysis_aggregates_counts_and_media_ratio() -> None:
    messages = [
        build_message(
            message_id=1,
            timestamp=datetime(2026, 4, 6, 0, 5, tzinfo=timezone.utc),
            text="Opening text update",
        ),
        build_message(
            message_id=2,
            timestamp=datetime(2026, 4, 6, 0, 35, tzinfo=timezone.utc),
            text="اصل خبر",
            english_text="Translated burst message",
            has_media=True,
        ),
        build_message(
            message_id=3,
            timestamp=datetime(2026, 4, 6, 2, 15, tzinfo=timezone.utc),
            has_media=True,
        ),
        build_message(
            message_id=4,
            timestamp=datetime(2026, 4, 7, 13, 0, tzinfo=timezone.utc),
            has_media=True,
        ),
        build_message(
            message_id=5,
            timestamp=datetime(2026, 4, 7, 13, 25, tzinfo=timezone.utc),
            text="Afternoon analysis",
        ),
    ]

    result = run_messaging_cadence_analysis(
        messages,
        channel_label="Cadence Test Channel",
        config=MessagingCadenceConfig(annotated_spikes=2),
    )

    hourly_00 = result.cadence_hourly_counts_df.loc[
        result.cadence_hourly_counts_df["timestamp"] == pd.Timestamp("2026-04-06 00:00:00+00:00")
    ].iloc[0]
    media_00 = result.cadence_media_hourly_df.loc[
        result.cadence_media_hourly_df["timestamp"] == pd.Timestamp("2026-04-06 00:00:00+00:00")
    ].iloc[0]
    apr6_summary = result.cadence_daily_summary_df.loc[
        result.cadence_daily_summary_df["date"] == pd.Timestamp("2026-04-06 00:00:00+00:00")
    ].iloc[0]

    assert len(result.cadence_messages_df) == 5
    assert hourly_00["message_count"] == 2
    assert media_00["media_count"] == 1
    assert media_00["media_pct"] == 50.0
    assert result.cadence_top_spikes_df.iloc[0]["timestamp"] == pd.Timestamp("2026-04-06 00:00:00+00:00")
    assert result.cadence_top_spikes_df.iloc[0]["representative_preview"] == "Translated burst message"
    assert apr6_summary["total_messages"] == 3
    assert apr6_summary["with_media"] == 2
    assert apr6_summary["text_only"] == 1
    assert apr6_summary["peak_hour"] == "00:00"
    assert apr6_summary["peak_count"] == 2
    assert result.cadence_structural_rhythm_df.loc["Mon", 0] == 2.0
    assert len(result.cadence_event_annotations_df) == 2

    plt.close("all")


def test_run_messaging_cadence_analysis_respects_manual_event_annotations() -> None:
    messages = [
        build_message(
            message_id=1,
            timestamp=datetime(2026, 4, 6, 9, 1, tzinfo=timezone.utc),
            text="First update",
        ),
        build_message(
            message_id=2,
            timestamp=datetime(2026, 4, 6, 9, 20, tzinfo=timezone.utc),
            text="Second update",
            has_media=True,
        ),
    ]

    result = run_messaging_cadence_analysis(
        messages,
        channel_label="Cadence Test Channel",
        event_annotations=[
            {"timestamp": "2026-04-06 09:44:00+00:00", "label": "Manual spike label"},
        ],
    )

    assert result.cadence_event_annotations_df.to_dict("records") == [
        {
            "timestamp": pd.Timestamp("2026-04-06 09:00:00+00:00"),
            "label": "Manual spike label",
        }
    ]

    plt.close("all")


def test_cadence_media_flag_uses_editorial_media_kind_not_media_refs() -> None:
    ts = datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)

    def kinded(message_id: int, kind: str, text: str | None) -> RawMessage:
        return RawMessage(
            channel_id=99,
            message_id=message_id,
            timestamp=ts + timedelta(minutes=message_id),
            sender_id=None,
            sender_name=None,
            text=text,
            raw_json={},
            media_kind=kind,
            has_link_preview=kind == "webpage",
        )

    result = run_messaging_cadence_analysis(
        [kinded(1, "video", "clip"), kinded(2, "webpage", "link card"), kinded(3, "none", "plain"), kinded(4, "photo", None)],
        channel_label="Kinds",
        config=MessagingCadenceConfig(annotated_spikes=1),
    )

    df = result.cadence_messages_df.set_index("message_id")
    assert df["has_media"].to_dict() == {1: True, 2: False, 3: False, 4: True}
    assert df["media_kind"].to_dict() == {1: "video", 2: "webpage", 3: "none", 4: "photo"}
    assert df["is_media_only"].to_dict() == {1: False, 2: False, 3: False, 4: True}
