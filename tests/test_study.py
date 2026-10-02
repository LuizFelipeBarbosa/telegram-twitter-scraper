from __future__ import annotations

import json

import numpy as np
import pandas as pd

from telegram_scraper import study


def test_clean_text_strips_presstv_signoffs() -> None:
    raw = "Iran says talks continue\n\n@PressTV"
    assert study.clean_text(raw, "presstv") == "Iran says talks continue"
    assert study.clean_text("\U0001F53A Academic says X.\n\n@PalestineDeclassified", "presstv") == "Academic says X."
    assert study.clean_text("Documentary clip\n\nWatch in full\n@Unscripted_PTV\n#IranToday", "presstv") == "Documentary clip"
    # a handle inside a sentence is content and stays
    assert "@Khamenei_en" in study.clean_text("Leader posted on @Khamenei_en today", "presstv")


def test_clean_text_irna_dateline_signoff_and_zero_width() -> None:
    raw = "\U0001F4AC Headline here\n\n\U0001F4CC Tehran, IRNA – The minister said talks resume.\n​\n\U0001F4F2 @Irna_en​"
    assert study.clean_text(raw, "irna-en") == "Headline here\n\nThe minister said talks resume."


def test_clean_text_jbn_call_to_action_block() -> None:
    raw = (
        "BREAKING: Missiles launched toward Israel.\n\n"
        "\U0001F1FA\U0001F1F8 WHATSAPP GROUP \U0001F517 https://chat.whatsapp.com/abc\n\n"
        "\U0001F1EE\U0001F1F1 TELEGRAM \U0001F517 https://t.me/JewishBreakingNewsTelegram\n\n"
        "\U0001F517 FOLLOW ALL JBN LINKS: https://link.me/jbn"
    )
    assert study.clean_text(raw, "jewishbreakingnewstelegram") == "BREAKING: Missiles launched toward Israel."
    assert study.clean_text("Story\n\nRead the FULL story >>> https://jewishbreakingnews.com/x", "jewishbreakingnewstelegram") == "Story"


def test_clean_text_toi_read_more_and_idf_prefix() -> None:
    assert study.clean_text("Strike kills IRGC chief\n\nRead more: https://toi.li/ILUHR1", "thetimesofisrael2022") == "Strike kills IRGC chief"
    assert study.clean_text("IDF: Troops struck targets.\n\nAttached is related footage: https://x.co/a", "idfofficial") == "Troops struck targets."


def test_clean_text_drops_urls_emoji_only_and_media_only_posts() -> None:
    assert study.clean_text("See https://example.com/a now", "iltvnews") == "See now"
    assert study.clean_text("\U0001F6A8\U0001F6A8\n\U0001F1EE\U0001F1F1", "iltvnews") == ""
    assert study.clean_text(None, "presstv") == ""
    assert study.clean_text("@PressTV", "presstv") == ""
    # paragraph structure survives
    assert study.clean_text("One.\n\nTwo.", "iltvnews") == "One.\n\nTwo."


def test_record_findings_merges_keys_and_makes_values_json_safe(tmp_path) -> None:
    path = tmp_path / "findings.json"
    study.record_findings("a", {"x": np.float64(1.5), "n": np.int64(3), "nan": float("nan"), "frame": pd.DataFrame({"k": [1, 2]})}, path)
    document = study.record_findings("b", {"y": [1, 2, 3]}, path)
    assert set(document) == {"a", "b"}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["a"]["x"] == 1.5 and loaded["a"]["n"] == 3 and loaded["a"]["nan"] is None
    assert loaded["a"]["frame"] == [{"k": 1}, {"k": 2}]
    # re-recording a key replaces only that key
    study.record_findings("a", {"x": 2}, path)
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["a"] == {"x": 2} and reloaded["b"] == {"y": [1, 2, 3]}


def test_verify_events_requires_posts_in_several_channels() -> None:
    day = pd.Timestamp("2026-04-13T12:00:00", tz="UTC")
    rows = [{"timestamp": day, "channel_slug": slug, "clean_text": "US naval blockade announced"} for slug in ("presstv", "iltvnews") for _ in range(5)]
    posts = pd.DataFrame(rows)
    events = [
        {"key": "blockade", "date": "2026-04-13", "label": "blockade", "short": "b", "evidence_query": r"blockade"},
        {"key": "absent", "date": "2026-04-13", "label": "absent", "short": "a", "evidence_query": r"volcano"},
    ]
    verdict = study.verify_events(posts, events).set_index("key")
    assert bool(verdict.loc["blockade", "verified"]) and not bool(verdict.loc["absent", "verified"])
