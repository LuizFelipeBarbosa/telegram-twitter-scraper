import numpy as np
import pandas as pd
import pytest

from telegram_scraper.analysis.validation import (
    KAPPA_THRESHOLD,
    make_coding_sheet,
    score_agreement,
    usable_labels,
)


def _frame():
    rows = []
    for channel in ("alpha", "beta"):
        for index in range(30):
            rows.append(
                {
                    "channel_slug": channel,
                    "text": f"{channel} post {index}",
                    "dominant_sentiment": ["negative", "neutral", "positive"][index % 3],
                    "dominant_emotion": ["fear", "joy", "neutral"][index % 3],
                }
            )
    return pd.DataFrame(rows)


def test_make_coding_sheet_is_blind_seeded_and_writes_key(tmp_path):
    df = _frame()
    kwargs = dict(
        label_cols={"sentiment": "dominant_sentiment", "emotion": "dominant_emotion"},
        n_per_group=10,
        seed=7,
    )
    sheet, key = make_coding_sheet(df, out_path=tmp_path / "sheet.csv", **kwargs)
    sheet2, key2 = make_coding_sheet(df, out_path=tmp_path / "sheet2.csv", **kwargs)

    assert list(sheet.columns) == ["id", "text", "human_sentiment", "human_emotion"]
    assert (sheet["human_sentiment"] == "").all()
    assert len(sheet) == 20
    assert key["channel"].value_counts().to_dict() == {"alpha": 10, "beta": 10}
    assert list(key.columns) == ["id", "channel", "source_index", "model_sentiment", "model_emotion"]
    # shuffled: ids do not sort by channel
    assert key["channel"].tolist() != sorted(key["channel"].tolist())
    pd.testing.assert_frame_equal(sheet, sheet2)
    pd.testing.assert_frame_equal(key, key2)
    assert (tmp_path / "sheet.csv").exists() and (tmp_path / "sheet_key.csv").exists()
    assert "alpha" not in (tmp_path / "sheet.csv").read_text(encoding="utf-8-sig").replace("alpha post", "")


def test_make_coding_sheet_small_group_and_list_label_cols(tmp_path):
    df = _frame().iloc[:35]  # beta has only 5 rows
    sheet, key = make_coding_sheet(
        df, label_cols=["dominant_sentiment"], n_per_group=10, out_path=tmp_path / "s.csv", show_channel=True
    )
    assert "channel" in sheet.columns
    assert key["channel"].value_counts().to_dict() == {"alpha": 10, "beta": 5}
    assert "model_dominant_sentiment" in key.columns


def test_score_agreement_toy_sheet(tmp_path):
    key = pd.DataFrame(
        {
            "id": [f"S{i}" for i in range(8)],
            "channel": ["a"] * 4 + ["b"] * 4,
            "model_sentiment": ["pos", "pos", "neg", "neg", "pos", "neg", "pos", "neg"],
            "model_emotion": ["joy", "joy", "fear", "fear", "joy", "fear", "joy", "fear"],
        }
    )
    coded = pd.DataFrame(
        {
            "id": [f"S{i}" for i in range(8)],
            "text": ["t"] * 8,
            # a: perfect; b: fully inverted
            "human_sentiment": ["pos", "pos", "neg", "neg", "neg", "pos", "neg", "pos"],
            # last row left blank -> skipped; first channel perfect
            "human_emotion": ["joy", "joy", "fear", "fear", "joy", "fear", "joy", ""],
        }
    )
    coded.to_csv(tmp_path / "coded.csv", index=False)
    key.to_csv(tmp_path / "key.csv", index=False)

    result = score_agreement(tmp_path / "coded.csv", tmp_path / "key.csv").set_index("label")
    assert result.loc["sentiment", "n"] == 8
    assert result.loc["sentiment", "agreement"] == pytest.approx(0.5)
    assert result.loc["sentiment", "kappa"] == pytest.approx(0.0)
    assert result.loc["sentiment", "kappa_a"] == pytest.approx(1.0)
    assert result.loc["sentiment", "kappa_b"] == pytest.approx(-1.0)
    confusion = result.loc["sentiment", "confusion"]
    assert confusion.loc["pos", "pos"] == 2 and confusion.loc["neg", "pos"] == 2
    assert result.loc["emotion", "n"] == 7
    assert result.loc["emotion", "kappa"] == pytest.approx(1.0)
    assert result.loc["emotion", "n_b"] == 3


def test_usable_labels_threshold():
    agreement = pd.DataFrame(
        {
            "label": ["sentiment", "emotion", "stance"],
            "kappa": [0.72, 0.41, float("nan")],
            "kappa_a": [0.9, 0.5, 0.8],
            "kappa_b": [0.5, 0.3, 0.8],
        }
    )
    assert KAPPA_THRESHOLD == 0.6
    assert usable_labels(agreement) == ["sentiment"]
    assert usable_labels(agreement, per_channel=True) == []
    assert usable_labels(agreement, threshold=0.4) == ["sentiment", "emotion"]


def test_score_agreement_round_trip_with_generated_sheet(tmp_path):
    df = _frame()
    sheet, key = make_coding_sheet(
        df,
        label_cols={"sentiment": "dominant_sentiment", "emotion": "dominant_emotion"},
        n_per_group=12,
        out_path=tmp_path / "s.csv",
    )
    coded = pd.read_csv(tmp_path / "s.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    coded["human_sentiment"] = key["model_sentiment"].to_numpy()  # coder agrees with model
    coded["human_emotion"] = key["model_emotion"].to_numpy()
    coded.to_csv(tmp_path / "coded.csv", index=False)
    result = score_agreement(tmp_path / "coded.csv", tmp_path / "s_key.csv")
    assert np.allclose(result["kappa"], 1.0)
    assert usable_labels(result, per_channel=True) == ["sentiment", "emotion"]
