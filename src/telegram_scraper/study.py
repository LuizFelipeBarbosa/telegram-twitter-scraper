"""Shared constants and loaders for the Feb 28 - Apr 17, 2026 Iran/Israel Telegram story notebooks.

Every ``notebooks/0X_*.ipynb`` imports this module for the channel table, the study window,
the cleaned post frame, the verified event list and the ``findings.json`` writer.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from telegram_scraper.snapshot import build_posts, load_snapshot

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_RUN = "2026-02-28_2026-04-18_20261002T081854Z"
SNAPSHOT_DIR = ROOT / "data" / "raw" / SNAPSHOT_RUN
CACHE_DIR = ROOT / "data" / "cache"
EMBEDDING_CACHE_DIR = CACHE_DIR / "embeddings"
TONE_CACHE_PATH = CACHE_DIR / "tone.parquet"
VALIDATION_DIR = ROOT / "data" / "validation"
STUDY_DIR = ROOT / "docs" / "study"
FIGURES_DIR = STUDY_DIR / "figures"
INTERACTIVE_DIR = STUDY_DIR / "interactive"
EXPORT_DATA_DIR = STUDY_DIR / "data"
FINDINGS_PATH = STUDY_DIR / "findings.json"

SEED = 42

# ---------------------------------------------------------------------------
# Design: 2 x 2 (ownership x country) channel table
# ---------------------------------------------------------------------------

WINDOW_START = pd.Timestamp("2026-02-28", tz="UTC")
WINDOW_END = pd.Timestamp("2026-04-18", tz="UTC")  # exclusive
WINDOW = (WINDOW_START, WINDOW_END)

CHANNELS: dict[str, dict[str, str]] = {
    "presstv": {
        "name": "Press TV",
        "short": "Press TV",
        "ownership": "state",
        "ownership_label": "state (broadcaster)",
        "country": "Iran",
        "role": "IRIB English-language state broadcaster",
        "color": "#9B1B30",  # deep crimson
    },
    "irna-en": {
        "name": "IRNA (English)",
        "short": "IRNA",
        "ownership": "state",
        "ownership_label": "state (news agency)",
        "country": "Iran",
        "role": "Iranian state news agency, English service",
        "color": "#E08E0B",  # amber
    },
    "idfofficial": {
        "name": "Israel Defense Forces",
        "short": "IDF",
        "ownership": "state",
        "ownership_label": "state (military)",
        "country": "Israel",
        "role": "Military spokesperson channel (state, but not a broadcaster)",
        "color": "#1F3A5F",  # navy
    },
    "iltvnews": {
        "name": "ILTV Israel News",
        "short": "ILTV",
        "ownership": "private",
        "ownership_label": "private (TV/online)",
        "country": "Israel",
        "role": "Private English-language TV and online news",
        "color": "#1B998B",  # teal
    },
    "thetimesofisrael2022": {
        "name": "The Times of Israel",
        "short": "ToI",
        "ownership": "private",
        "ownership_label": "private (newspaper)",
        "country": "Israel",
        "role": "Private newspaper; photo posts with a headline and a 'Read more' link",
        "color": "#3D7EBB",  # blue
    },
    "jewishbreakingnewstelegram": {
        "name": "Jewish Breaking News",
        "short": "JBN",
        "ownership": "private",
        "ownership_label": "private (aggregator)",
        "country": "Israel",
        "role": "Israel-focused news aggregator; ownership unverified",
        "color": "#6B7A8F",  # slate
    },
}
CHANNEL_ORDER = list(CHANNELS)
SHORT_NAMES = {slug: meta["short"] for slug, meta in CHANNELS.items()}
COUNTRY_TZ = {"Iran": "Asia/Tehran", "Israel": "Asia/Jerusalem"}
CHANNEL_TZ = {slug: COUNTRY_TZ[meta["country"]] for slug, meta in CHANNELS.items()}


def channel_table() -> pd.DataFrame:
    """The channel design table (one row per channel, in plotting order)."""
    rows = [{"channel_slug": slug, **meta} for slug, meta in CHANNELS.items()]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_ZERO_WIDTH_RE = re.compile("[​‌‍‎‏⁠﻿]")
_URL_RE = re.compile(r"(?:https?://|www\.|t\.me/|toi\.li/)\S*", re.IGNORECASE)
# Pictographs, dingbats, flags, variation selectors and joiners (decorative leading marks).
_EMOJI_CLASS = (
    "\U0001F000-\U0001FAFF←-⇿⌀-⏿①-⓿■-◿☀-➿"
    "⤀-⥿⬀-⯿〰〽㊗㊙︎️‍\U000E0020-\U000E007F"
)
_EMOJI_LEAD_RE = re.compile(rf"(?m)^[ \t]*[{_EMOJI_CLASS}][{_EMOJI_CLASS} \t]*")
_EMOJI_RE = re.compile(f"[{_EMOJI_CLASS}]")
_NO_LETTERS_RE = re.compile(r"^[\W_]*$")  # a line with no letters/digits at all

#: slug -> list of (rule_name, compiled regex, replacement, human description). Applied in order,
#: line-oriented (``(?m)``), BEFORE the generic URL / emoji / empty-line passes.
BOILERPLATE_RULES: dict[str, list[tuple[str, re.Pattern[str], str, str]]] = {
    "presstv": [
        (
            "presstv_handle_line",
            re.compile(r"(?m)^[ \t]*(?:[^\w\s@#]+[ \t]*)?(?:@\w+[ \t]*)+$"),
            "",
            "Line that is only @handles (sign-off '@PressTV', '@Unscripted_PTV', '@PalestineDeclassified', ...)",
        ),
        (
            "presstv_trailing_handle",
            re.compile(r"[ \t]*@(?:PressTV|Press_TV)\b[ \t]*$", re.IGNORECASE | re.MULTILINE),
            "",
            "'@PressTV' sign-off at the end of a content line",
        ),
        (
            "presstv_watch_in_full",
            re.compile(r"(?im)^[ \t]*(?:[^\w\s]+[ \t]*)?watch (?:in full|the full|full)(?: here)?[ \t]*:?[ \t]*$"),
            "",
            "'Watch in full (here)' call to action",
        ),
        (
            "presstv_hashtag_line",
            re.compile(r"(?m)^[ \t]*(?:#\w+[ \t]*)+$"),
            "",
            "Line that is only #hashtags (programme tags such as #IranToday)",
        ),
        (
            "presstv_khamenei_ir_footer",
            re.compile(r"(?im)^.*KHAMENEI\.IR.*$"),
            "",
            "'KHAMENEI.IR | X (Official)' footer line on reposted Leader statements",
        ),
    ],
    "irna-en": [
        (
            "irna_handle_line",
            re.compile(r"(?m)^[ \t]*(?:[^\w\s@#]+[ \t]*)?(?:@\w+[ \t]*)+$"),
            "",
            "Line that is only @Irna_en (sign-off, usually after an emoji)",
        ),
        (
            "irna_dateline",
            re.compile(r"(?m)^([ \t]*)(?:[^\w\s]+[ \t]*)?[A-Z][A-Za-z .'-]{1,30},[ \t]*IRNA[ \t]*[-–—]+[ \t]*"),
            r"\1",
            "Dateline prefix 'Tehran, IRNA -' (the sentence continues after it)",
        ),
    ],
    "jewishbreakingnewstelegram": [
        (
            "jbn_cta_line",
            re.compile(
                r"(?im)^.*(?:whatsapp (?:group|channel)|follow all jbn links|see all jbn links"
                r"|donate now|tax deductible|\u2611\ufe0f? ?verified|>>>).*$"
            ),
            "",
            "WhatsApp / 'JBN links' / donate / tax-deductible / verified-badge / 'Read ... >>>' call-to-action lines",
        ),
        (
            "jbn_telegram_link_line",
            re.compile(r"(?im)^[ \t]*(?:[^\w\s]+[ \t]*)*telegram[ \t]*(?:[^\w\s]+[ \t]*)*(?:https?://\S*)?[ \t]*$"),
            "",
            "'TELEGRAM <link>' follow line (only an emoji, the word TELEGRAM and a link)",
        ),
        (
            "jbn_read_more_link",
            re.compile(r"(?im)^[ \t]*(?:[^\w\s]+[ \t]*)?read (?:more|the (?:full )?(?:story|details))\b[^\n]*$"),
            "",
            "'READ MORE: <link>' line pointing to jewishbreakingnews.com",
        ),
    ],
    "thetimesofisrael2022": [
        (
            "toi_read_more",
            re.compile(r"(?im)^[ \t]*read more:?[ \t]*(?:https?://\S*)?[ \t]*$"),
            "",
            "Trailing 'Read more: https://toi.li/...' link line (present on every photo post)",
        ),
    ],
    "idfofficial": [
        (
            "idf_prefix",
            re.compile(r"^[ \t]*IDF:[ \t]*"),
            "",
            "Channel prefix 'IDF:' at the start of a post",
        ),
        (
            "idf_attached",
            re.compile(r"(?im)^[ \t]*attached (?:is|are)\b[^\n]*$"),
            "",
            "'Attached is a related graphic/footage: <url>' link-out line",
        ),
    ],
    "iltvnews": [
        (
            "iltv_cta",
            re.compile(r"(?im)^.*(?:to comment, follow this link|reporting live from israel).*$"),
            "",
            "'To comment, follow this link' / '... Reporting live from Israel' tag lines",
        ),
    ],
}

#: Generic passes (all channels), listed in the order they are applied after the channel rules.
GENERIC_RULES: list[tuple[str, str]] = [
    ("zero_width", r"[​‌‍‎‏⁠﻿] -> '' (zero-width / bidi marks; IRNA pads lines with U+200B)"),
    ("urls", r"(?:https?://|www\.|t\.me/|toi\.li/)\S* -> '' (bare URLs, incl. toi.li short links)"),
    ("leading_emoji", "emoji / pictograph markers at the start of a line are removed (decorative bullets like pin, warning)"),
    ("no_letter_lines", "lines with no letter or digit at all (emoji-only, punctuation-only) are dropped"),
    ("whitespace", "runs of blank lines collapse to one blank line; spaces collapse; text is stripped"),
]


def clean_text(text: str | None, slug: str | None = None) -> str:
    """Strip channel boilerplate (sign-offs, call-to-action lines, link-outs) from a post.

    Channel-specific line rules come first (see ``BOILERPLATE_RULES``), then the generic passes in
    ``GENERIC_RULES``. Content words are never altered; the result is ``""`` for posts that are only
    boilerplate (e.g. a bare sign-off or a media-only post).
    """
    value = "" if text is None else str(text)
    value = _ZERO_WIDTH_RE.sub("", value)
    for _, pattern, replacement, _ in BOILERPLATE_RULES.get(slug or "", []):
        value = pattern.sub(replacement, value)
    value = _URL_RE.sub("", value)
    value = _EMOJI_LEAD_RE.sub("", value)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    lines = [line for line in lines if line == "" or not _NO_LETTERS_RE.match(line)]
    # Blank separator lines between paragraphs are kept (single) so paragraph structure survives.
    kept: list[str] = []
    for line in lines:
        if line == "" and (not kept or kept[-1] == ""):
            continue
        kept.append(line)
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept).strip()


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


def media_class(row: Any) -> str:
    """Editorial media class of a post: video > photo > link preview > text only."""
    if row.has_video:
        return "video"
    if row.has_photo:
        return "photo"
    if row.has_editorial_media:
        return "other media"
    if row.has_link_preview:
        return "link preview"
    return "text only"


MEDIA_CLASSES = ["video", "photo", "link preview", "other media", "text only"]


def load_posts(run_dir: str | Path | None = None) -> pd.DataFrame:
    """Snapshot -> posts (album-grouped) joined with channel metadata and ``clean_text``.

    Added columns: ``short_name, name, ownership, ownership_label, country, role, color, quadrant,
    clean_text, has_clean_text, media_class, date (UTC day), hour_utc``.
    """
    messages = load_snapshot(run_dir or SNAPSHOT_DIR)
    posts = build_posts(messages)
    meta = channel_table().rename(columns={"short": "short_name"})
    posts = posts.merge(meta, on="channel_slug", how="left", validate="many_to_one")
    unknown = posts.loc[posts["short_name"].isna(), "channel_slug"].unique()
    if len(unknown):
        raise ValueError(f"channels missing from study.CHANNELS: {list(unknown)}")
    posts["clean_text"] = [clean_text(text, slug) for text, slug in zip(posts["text"], posts["channel_slug"])]
    posts["has_clean_text"] = posts["clean_text"] != ""
    posts["media_class"] = [media_class(row) for row in posts.itertuples(index=False)]
    posts["quadrant"] = posts["country"] + " / " + posts["ownership"]
    posts["date"] = posts["timestamp"].dt.floor("D")
    posts["hour_utc"] = posts["timestamp"].dt.hour
    channel_order = pd.Categorical(posts["channel_slug"], categories=CHANNEL_ORDER, ordered=True)
    posts = posts.assign(_order=channel_order).sort_values(["_order", "timestamp", "first_message_id"]).drop(columns="_order")
    return posts.reset_index(drop=True)


def add_local_time(posts: pd.DataFrame) -> pd.DataFrame:
    """Add ``local_hour`` (Tehran time for Iranian channels, Jerusalem time for Israeli ones)."""
    out = posts.copy()
    local_hours = np.zeros(len(out), dtype=int)
    for slug, tz in CHANNEL_TZ.items():
        mask = (out["channel_slug"] == slug).to_numpy()
        if mask.any():
            local_hours[mask] = out.loc[mask, "timestamp"].dt.tz_convert(tz).dt.hour.to_numpy()
    out["local_hour"] = local_hours
    return out


# ---------------------------------------------------------------------------
# Events (each must be verified in the data before it is drawn)
# ---------------------------------------------------------------------------

EVENTS: list[dict[str, Any]] = [
    {
        "key": "war_start",
        "date": "2026-02-28",
        "label": "US-Israeli strikes on Iran begin",
        "short": "War begins",
        "evidence_query": r"Roaring Lion|(?:strikes?|attacks?|attacked|struck|bombed) (?:on |against )?Iran|US-Israeli (?:aggression|attack|strikes?)|Israel has launched",
    },
    {
        "key": "khamenei_death",
        "date": "2026-03-01",
        "label": "Khamenei's death announced",
        "short": "Khamenei dead",
        "evidence_query": r"Khamenei.{0,60}(?:dead|death|martyr|killed|funeral)|(?:death|martyrdom|assassination|killing) of .{0,40}Khamenei",
    },
    {
        "key": "ceasefire",
        "date": "2026-04-08",
        "label": "US-Iran ceasefire announced",
        "short": "Ceasefire",
        "evidence_query": r"cease-?fire|truce",
    },
    {
        "key": "mourning_40",
        "date": "2026-04-09",
        "label": "40th-day mourning for Khamenei",
        "short": "40th day",
        "evidence_query": r"(?:40th|fortieth|forty[- ]day|40[- ]day).{0,80}(?:mourn|martyr|passing|demise|memorial|ceremon|Leader|Khamenei|commemorat)|(?:mourn|martyr|memorial|Khamenei|ceremon|commemorat).{0,80}(?:40th|fortieth|forty[- ]day|40[- ]day|40 days)",
    },
    {
        "key": "islamabad",
        "date": "2026-04-11",
        "label": "Islamabad Iran-US talks",
        "short": "Islamabad talks",
        "evidence_query": r"Islamabad",
    },
    {
        "key": "hormuz_blockade",
        "date": "2026-04-13",
        "label": "US naval blockade of Hormuz",
        "short": "Hormuz blockade",
        "evidence_query": r"blockade",
    },
    {
        "key": "yom_hashoah",
        "date": "2026-04-14",
        "label": "Yom HaShoah (Holocaust Remembrance Day)",
        "short": "Yom HaShoah",
        "evidence_query": r"Yom HaShoah|Holocaust",
    },
]


def verify_events(
    posts: pd.DataFrame,
    events: list[dict[str, Any]] | None = None,
    *,
    window_days: int = 1,
    min_posts: int = 8,
    min_channels: int = 2,
    text_col: str = "clean_text",
) -> pd.DataFrame:
    """Count posts matching each event's ``evidence_query`` within +/- ``window_days`` of its date.

    An event is ``verified`` when at least ``min_posts`` posts from at least ``min_channels`` channels
    match inside that window.
    """
    rows = []
    for event in events if events is not None else EVENTS:
        day = pd.Timestamp(event["date"], tz="UTC")
        in_window = (posts["timestamp"] >= day - pd.Timedelta(days=window_days)) & (
            posts["timestamp"] < day + pd.Timedelta(days=window_days + 1)
        )
        matches = posts[in_window & posts[text_col].str.contains(event["evidence_query"], case=False, regex=True)]
        row = {
            "key": event["key"],
            "date": event["date"],
            "label": event["label"],
            "n_matches": int(len(matches)),
            "n_channels": int(matches["channel_slug"].nunique()),
        }
        for slug in CHANNEL_ORDER:
            row[SHORT_NAMES[slug]] = int((matches["channel_slug"] == slug).sum())
        row["verified"] = bool(row["n_matches"] >= min_posts and row["n_channels"] >= min_channels)
        rows.append(row)
    return pd.DataFrame(rows)


def verified_events(posts: pd.DataFrame, **kwargs: Any) -> list[dict[str, Any]]:
    """The subset of ``EVENTS`` the data supports (see :func:`verify_events`)."""
    verdicts = verify_events(posts, **kwargs).set_index("key")["verified"]
    return [event for event in EVENTS if verdicts.get(event["key"], False)]


def event_examples(
    posts: pd.DataFrame,
    event: Mapping[str, Any],
    n: int = 3,
    *,
    window_days: int = 1,
    text_col: str = "clean_text",
) -> pd.DataFrame:
    """Up to ``n`` matching posts (one per channel first, earliest first) as evidence for an event."""
    day = pd.Timestamp(event["date"], tz="UTC")
    in_window = (posts["timestamp"] >= day - pd.Timedelta(days=window_days)) & (
        posts["timestamp"] < day + pd.Timedelta(days=window_days + 1)
    )
    matches = posts[in_window & posts[text_col].str.contains(event["evidence_query"], case=False, regex=True)]
    first_per_channel = matches.sort_values("timestamp").groupby("channel_slug", sort=False).head(1)
    return first_per_channel.sort_values("timestamp").head(n)[["timestamp", "short_name", text_col]]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if isinstance(value, pd.DataFrame):
        return json.loads(value.to_json(orient="records"))
    if isinstance(value, pd.Series):
        return json.loads(value.to_json())
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    raise TypeError(f"not JSON serialisable: {type(value)!r}")


def _sanitize(value: Any) -> Any:
    """Round-trip through JSON so NaN/inf become null and numpy types become plain Python."""
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.DataFrame, pd.Series, np.ndarray, set, frozenset)):
        return _sanitize(json.loads(json.dumps(value, default=_json_default)))
    return json.loads(json.dumps(value, default=_json_default))


def record_findings(key: str, payload: Mapping[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    """Merge ``payload`` into ``findings.json`` under ``key`` (other keys are preserved).

    The write is atomic. Values are made JSON-safe (numpy scalars, DataFrames -> records, NaN -> null).
    Returns the full document.
    """
    target = Path(path) if path is not None else FINDINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {}
    if target.exists() and target.stat().st_size > 0:
        document = json.loads(target.read_text(encoding="utf-8"))
    document[key] = _sanitize(dict(payload))
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return document


def load_findings(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FINDINGS_PATH
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cached model scoring
# ---------------------------------------------------------------------------


def score_tone_cached(posts: pd.DataFrame, cache_path: str | Path | None = None, *, text_col: str = "clean_text") -> pd.DataFrame:
    """Sentiment + emotion scores per post (``analysis.sentiment.score_frame``), cached by ``post_id``.

    Posts with no text after cleaning get NaN scores. The cache is a parquet file keyed by ``post_id``
    plus a hash of the scored text, so a change to the cleaning rules re-scores only the changed posts.
    """
    import hashlib

    from telegram_scraper.analysis.sentiment import score_frame

    path = Path(cache_path) if cache_path is not None else TONE_CACHE_PATH
    cached = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    hashes = posts[text_col].map(lambda text: hashlib.sha1(text.encode("utf-8")).hexdigest())
    known = set(zip(cached.index, cached["text_sha1"])) if len(cached) else set()
    fresh_mask = np.array([(pid, h) not in known for pid, h in zip(posts["post_id"], hashes)]) & (posts[text_col] != "").to_numpy()
    if fresh_mask.any():
        todo = posts[fresh_mask]
        scored = score_frame(todo.reset_index(drop=True), text_col=text_col)
        scored.index = todo["post_id"].to_numpy()
        scored.index.name = "post_id"
        scored["text_sha1"] = hashes[fresh_mask].to_numpy()
        cached = pd.concat([cached[~cached.index.isin(scored.index)], scored]) if len(cached) else scored
        path.parent.mkdir(parents=True, exist_ok=True)
        cached.to_parquet(path)
    tone = cached.drop(columns="text_sha1").reindex(posts["post_id"].to_numpy())
    tone.index = posts.index
    return tone


def bootstrap_median_ci(values: Any, *, n_boot: int = 2000, seed: int = SEED, alpha: float = 0.05) -> dict[str, float]:
    """Percentile-bootstrap CI for a median (``analysis.stats`` only ships the mean). Keys: ``n, median, ci_low, ci_high``."""
    array = np.asarray(pd.Series(values).dropna(), dtype=float)
    if array.size == 0:
        return {"n": 0, "median": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    rng = np.random.default_rng(seed)
    medians = np.median(array[rng.integers(0, array.size, size=(n_boot, array.size))], axis=1)
    low, high = np.percentile(medians, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"n": int(array.size), "median": float(np.median(array)), "ci_low": float(low), "ci_high": float(high)}
