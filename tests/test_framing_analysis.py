from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("plotly")
pytest.importorskip("seaborn")
import matplotlib.pyplot as plt

from telegram_scraper.analysis import framing
from telegram_scraper.analysis.framing import RhetoricFramingConfig, run_rhetoric_framing_analysis
from telegram_scraper.notebook_pipeline import RawMessage


CANDIDATE_SCORES = {
    "fear": {
        "fear and threat warning": 0.76,
        "authority appeal and official quote": 0.08,
        "victimhood and injustice": 0.07,
        "call to action": 0.04,
        "us versus them othering": 0.02,
        "factual neutral reporting": 0.01,
        "conspiracy and suspicion": 0.01,
        "triumphalism and strength": 0.01,
    },
    "authority": {
        "authority appeal and official quote": 0.72,
        "factual neutral reporting": 0.11,
        "fear and threat warning": 0.05,
        "victimhood and injustice": 0.04,
        "call to action": 0.03,
        "us versus them othering": 0.02,
        "conspiracy and suspicion": 0.02,
        "triumphalism and strength": 0.01,
    },
    "mixed": {
        "factual neutral reporting": 0.24,
        "authority appeal and official quote": 0.22,
        "victimhood and injustice": 0.15,
        "fear and threat warning": 0.12,
        "conspiracy and suspicion": 0.09,
        "us versus them othering": 0.08,
        "call to action": 0.06,
        "triumphalism and strength": 0.04,
    },
    "triumph": {
        "triumphalism and strength": 0.79,
        "fear and threat warning": 0.05,
        "call to action": 0.05,
        "authority appeal and official quote": 0.04,
        "factual neutral reporting": 0.03,
        "us versus them othering": 0.02,
        "victimhood and injustice": 0.01,
        "conspiracy and suspicion": 0.01,
    },
}


class FakeZeroShotClassifier:
    def __call__(
        self,
        texts,
        *,
        candidate_labels,
        multi_label,
        hypothesis_template,
        truncation,
        batch_size,
    ):
        assert multi_label is False
        assert hypothesis_template.startswith("This message primarily uses")
        batch = [texts] if isinstance(texts, str) else list(texts)
        outputs = []
        for text in batch:
            lowered = text.lower()
            if "threat" in lowered or "strike" in lowered:
                score_map = CANDIDATE_SCORES["fear"]
            elif "minister said" in lowered or "according to" in lowered:
                score_map = CANDIDATE_SCORES["authority"]
            elif "victory" in lowered or "powerful" in lowered:
                score_map = CANDIDATE_SCORES["triumph"]
            else:
                score_map = CANDIDATE_SCORES["mixed"]

            ordered_labels = sorted(candidate_labels, key=lambda label: score_map[label], reverse=True)
            outputs.append(
                {
                    "labels": ordered_labels,
                    "scores": [score_map[label] for label in ordered_labels],
                }
            )
        return outputs if len(outputs) > 1 else outputs[0]


def build_message(*, message_id: int, timestamp: datetime, text: str, english_text: str | None = None) -> RawMessage:
    return RawMessage(
        channel_id=321,
        message_id=message_id,
        timestamp=timestamp,
        sender_id=None,
        sender_name=None,
        text=text,
        raw_json={},
        english_text=english_text,
    )


def test_run_rhetoric_framing_analysis_classifies_messages_and_builds_outputs(monkeypatch) -> None:
    monkeypatch.setattr(framing, "_build_zero_shot_classifier", lambda config: FakeZeroShotClassifier())

    messages = [
        build_message(
            message_id=1,
            timestamp=datetime(2026, 4, 6, 0, 10, tzinfo=timezone.utc),
            text="Direct threat of a strike against key infrastructure.",
        ),
        build_message(
            message_id=2,
            timestamp=datetime(2026, 4, 6, 8, 30, tzinfo=timezone.utc),
            text="اصل خبر",
            english_text="According to the minister said in the briefing, talks continue.",
        ),
        build_message(
            message_id=3,
            timestamp=datetime(2026, 4, 6, 16, 45, tzinfo=timezone.utc),
            text="An unclear update with several competing cues and little certainty.",
        ),
        build_message(
            message_id=4,
            timestamp=datetime(2026, 4, 7, 4, 20, tzinfo=timezone.utc),
            text="The resistance celebrates a powerful victory and strong capabilities.",
        ),
    ]
    sentiment_emotion_df = pd.DataFrame(
        [
            {"channel_id": 321, "message_id": 1, "dominant_sentiment": "negative"},
            {"channel_id": 321, "message_id": 2, "dominant_sentiment": "neutral"},
            {"channel_id": 321, "message_id": 3, "dominant_sentiment": "neutral"},
            {"channel_id": 321, "message_id": 4, "dominant_sentiment": "positive"},
        ]
    )

    result = run_rhetoric_framing_analysis(
        messages,
        channel_label="Framing Test Channel",
        sentiment_emotion_df=sentiment_emotion_df,
        config=RhetoricFramingConfig(
            window_freq="12h",
            model_batch_size=2,
            gallery_examples_per_frame=1,
            validation_samples_per_frame=1,
            ambiguous_threshold=0.35,
        ),
    )

    dominant_frames = result.rhetoric_messages_df.set_index("message_id")["dominant_frame"].to_dict()
    assert dominant_frames[1] == "Fear / Threat"
    assert dominant_frames[2] == "Authority Appeal"
    assert dominant_frames[3] == "Mixed / Ambiguous"
    assert dominant_frames[4] == "Triumphalism / Strength"

    assert result.rhetoric_summary_df.iloc[0]["messages_scored"] == 4
    assert result.rhetoric_label_counts_df.set_index("dominant_frame").loc["Mixed / Ambiguous", "message_count"] == 1
    assert result.rhetoric_window_df["message_count"].sum() == 4
    assert set(result.rhetoric_window_long_df["frame_label"]) == set(result.rhetoric_taxonomy_df["frame_label"])
    assert set(result.rhetoric_half_summary_df["period_half"]) == {"First Half", "Second Half"}
    assert not result.rhetoric_half_flow_df.empty

    assert result.rhetoric_example_messages_df["example_rank"].max() == 1
    assert len(result.rhetoric_validation_sample_df) == 4

    crosstab = result.rhetoric_sentiment_crosstab_df
    assert crosstab.loc["Fear / Threat", "negative"] == 1
    assert crosstab.loc["Authority Appeal", "neutral"] == 1
    assert crosstab.loc["Triumphalism / Strength", "positive"] == 1
    assert result.rhetoric_sentiment_heatmap_fig is not None

    assert result.rhetoric_over_time_fig is not None
    assert result.rhetoric_transition_fig is not None
    assert result.rhetoric_examples_fig is not None

    plt.close("all")
