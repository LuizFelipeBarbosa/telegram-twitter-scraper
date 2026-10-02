"""Human-validation toolkit for model labels (sentiment / emotion).

Workflow: ``make_coding_sheet`` -> humans fill ``human_*`` columns blind to channel ->
``score_agreement`` compares them against the model labels held in the private key ->
``usable_labels`` lists labels whose agreement clears ``KAPPA_THRESHOLD``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

KAPPA_THRESHOLD = 0.6
CSV_ENCODING = "utf-8-sig"

DEFAULT_HUMAN_COLS = ("human_sentiment", "human_emotion")
DEFAULT_PAIRS: dict[str, tuple[str, str]] = {
    "sentiment": ("human_sentiment", "model_sentiment"),
    "emotion": ("human_emotion", "model_emotion"),
}


def _model_column_name(name: str) -> str:
    return name if name.startswith("model_") else f"model_{name}"


def make_coding_sheet(
    df: pd.DataFrame,
    *,
    label_cols: Sequence[str] | Mapping[str, str],
    out_path: str | os.PathLike[str],
    n_per_group: int = 150,
    group_col: str = "channel_slug",
    text_col: str = "text",
    seed: int = 0,
    key_path: str | os.PathLike[str] | None = None,
    human_cols: Sequence[str] = DEFAULT_HUMAN_COLS,
    show_channel: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sample ``n_per_group`` rows per group and write a blind coding sheet plus a private key.

    ``label_cols`` lists the model-label columns of ``df`` to put in the key. Pass a mapping
    ``{"sentiment": "dominant_sentiment", "emotion": "dominant_emotion"}`` to get key columns
    ``model_sentiment`` / ``model_emotion`` (a plain list yields ``model_<column>``).

    The sheet (``out_path``) holds ``id, text`` and empty ``human_cols`` (plus the channel only if
    ``show_channel``). Rows are shuffled across groups and ids follow the shuffled order, so ids
    carry no channel information. The key (``key_path``, default ``<out_path stem>_key.csv``) maps
    ``id -> channel, source_index, model labels`` and must be kept from coders.
    Returns ``(sheet_df, key_df)``.
    """
    if isinstance(label_cols, Mapping):
        label_map = {_model_column_name(key): column for key, column in label_cols.items()}
    else:
        label_map = {_model_column_name(column): column for column in label_cols}

    parts = [
        group.sample(n=min(n_per_group, len(group)), random_state=seed)
        for _, group in df.groupby(group_col, sort=True)
    ]
    sampled = pd.concat(parts).sample(frac=1.0, random_state=seed)  # shuffle across groups
    ids = [f"S{position:04d}" for position in range(1, len(sampled) + 1)]

    sheet_df = pd.DataFrame({"id": ids, "text": sampled[text_col].fillna("").astype(str).to_numpy()})
    if show_channel:
        sheet_df.insert(1, "channel", sampled[group_col].to_numpy())
    for column in human_cols:
        sheet_df[column] = ""

    key_df = pd.DataFrame(
        {"id": ids, "channel": sampled[group_col].to_numpy(), "source_index": sampled.index.to_numpy()}
    )
    for key_column, source_column in label_map.items():
        key_df[key_column] = sampled[source_column].to_numpy()

    out = Path(out_path)
    key_out = Path(key_path) if key_path is not None else out.with_name(f"{out.stem}_key.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    key_out.parent.mkdir(parents=True, exist_ok=True)
    sheet_df.to_csv(out, index=False, encoding=CSV_ENCODING)
    key_df.to_csv(key_out, index=False, encoding=CSV_ENCODING)
    return sheet_df, key_df


def _normalise(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def _kappa(human: pd.Series, model: pd.Series) -> float:
    from sklearn.metrics import cohen_kappa_score

    if len(human) == 0 or len(set(human) | set(model)) < 2:
        return float("nan")
    return float(cohen_kappa_score(human, model))


def _read_csv(source: str | os.PathLike[str] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source
    return pd.read_csv(source, dtype=str, keep_default_na=False, encoding=CSV_ENCODING)


def score_agreement(
    coded_csv: str | os.PathLike[str] | pd.DataFrame,
    key_csv: str | os.PathLike[str] | pd.DataFrame,
    pairs: Mapping[str, tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Agreement between human codes and model labels, per label.

    ``pairs`` maps a label name to ``(human_column, model_column)``; the default scores
    sentiment and emotion. Rows the human left blank are skipped. Returns one row per label with
    ``label, n, agreement, kappa, confusion`` (a DataFrame, humans on rows / model on columns),
    ``n_<channel>`` and ``kappa_<channel>`` for every channel in the key.
    """
    pairs = dict(pairs or DEFAULT_PAIRS)
    coded = _read_csv(coded_csv).drop(columns=["channel"], errors="ignore")  # channel comes from the key
    key = _read_csv(key_csv)
    merged = coded.merge(key, on="id", how="left", validate="one_to_one", suffixes=("", "_key"))
    if merged["channel"].isna().any():
        raise ValueError("Some coded ids are missing from the key file.")
    channels = sorted(merged["channel"].unique(), key=str)

    rows = []
    for label, (human_col, model_col) in pairs.items():
        for column in (human_col, model_col):
            if column not in merged.columns:
                raise KeyError(f"Column {column!r} not found in coded sheet / key.")
        frame = merged[["channel", human_col, model_col]].copy()
        frame[human_col] = _normalise(frame[human_col].fillna(""))
        frame[model_col] = _normalise(frame[model_col].fillna(""))
        frame = frame[(frame[human_col] != "") & (frame[model_col] != "")]

        labels_seen = sorted(set(frame[human_col]) | set(frame[model_col]))
        confusion = (
            pd.crosstab(frame[human_col], frame[model_col])
            .reindex(index=labels_seen, columns=labels_seen, fill_value=0)
            .rename_axis(index="human", columns="model")
        )
        row: dict[str, object] = {
            "label": label,
            "n": int(len(frame)),
            "agreement": float((frame[human_col] == frame[model_col]).mean()) if len(frame) else float("nan"),
            "kappa": _kappa(frame[human_col], frame[model_col]),
            "confusion": confusion,
        }
        for channel in channels:
            subset = frame[frame["channel"] == channel]
            row[f"n_{channel}"] = int(len(subset))
            row[f"kappa_{channel}"] = _kappa(subset[human_col], subset[model_col])
        rows.append(row)
    return pd.DataFrame(rows)


def usable_labels(
    agreement_df: pd.DataFrame,
    threshold: float = KAPPA_THRESHOLD,
    *,
    per_channel: bool = False,
) -> list[str]:
    """Labels whose Cohen's kappa is >= ``threshold`` (default ``KAPPA_THRESHOLD`` = 0.6).

    With ``per_channel=True`` every ``kappa_<channel>`` column must also clear the threshold, which
    is the stricter condition for cross-channel comparisons. NaN kappas never qualify.
    """
    kappa_columns = ["kappa"]
    if per_channel:
        kappa_columns += [column for column in agreement_df.columns if column.startswith("kappa_")]
    mask = np.ones(len(agreement_df), dtype=bool)
    for column in kappa_columns:
        mask &= (agreement_df[column] >= threshold).to_numpy()
    return agreement_df.loc[mask, "label"].tolist()
