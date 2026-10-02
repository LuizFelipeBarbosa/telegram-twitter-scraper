import numpy as np
import pandas as pd
import pytest

from telegram_scraper.analysis import sentiment
from telegram_scraper.analysis.sentiment import EMOTION_LABEL_ORDER, SENTIMENT_LABEL_ORDER, score_frame


class FakePipe:
    def __init__(self, labels, pick):
        self.labels = labels
        self.pick = pick
        self.calls = []
        self.tokenizer = type("Tok", (), {"model_max_length": 10**30})()

    def __call__(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        outputs = []
        for text in texts:
            winner = self.pick(text)
            outputs.append(
                [{"label": label.upper(), "score": 0.8 if label == winner else 0.2 / (len(self.labels) - 1)} for label in self.labels]
            )
        return outputs


@pytest.fixture
def pipes(monkeypatch):
    sentiment_pipe = FakePipe(SENTIMENT_LABEL_ORDER, lambda text: "negative" if "attack" in text else "positive")
    emotion_pipe = FakePipe(EMOTION_LABEL_ORDER, lambda text: "fear" if "attack" in text else "joy")
    monkeypatch.setattr(sentiment, "_load_pipelines", lambda *args: (sentiment_pipe, emotion_pipe))
    return sentiment_pipe, emotion_pipe


def test_score_frame_aligned_with_index_and_explicit_truncation(pipes):
    df = pd.DataFrame(
        {"text": ["Rocket attack https://x.co/1", "", "Peace rally today", None]},
        index=[5, 5, 9, 12],  # deliberately non-unique / non-range index
    )
    scored = score_frame(df)
    assert scored.index.equals(df.index)
    assert scored.iloc[0]["dominant_sentiment"] == "negative"
    assert scored.iloc[0]["dominant_emotion"] == "fear"
    assert scored.iloc[2]["dominant_sentiment"] == "positive"
    assert scored.iloc[2]["sentiment_score"] == pytest.approx(0.8 - 0.1)
    assert scored.iloc[[1, 3]].isna().all().all()  # no text -> NaN scores
    for column in ("sentiment_negative", "sentiment_neutral", "sentiment_positive", "emotion_fear", "emotion_neutral"):
        assert column in scored.columns

    for pipe in pipes:
        texts, kwargs = pipe.calls[0]
        assert texts == ["Rocket attack", "Peace rally today"]  # URL stripped, empties skipped
        assert kwargs["truncation"] is True and kwargs["max_length"] == 512


def test_score_frame_respects_config_char_limit(pipes):
    config = sentiment.SentimentEmotionConfig(text_max_chars=4)
    score_frame(pd.DataFrame({"text": ["abcdefgh"]}), config=config)
    assert pipes[0].calls[0][0] == ["abcd"]


def test_score_frame_custom_text_col_and_all_empty(pipes):
    scored = score_frame(pd.DataFrame({"body": ["", "  "]}), text_col="body")
    assert len(scored) == 2 and scored["sentiment_score"].isna().all()
    assert not pipes[0].calls


def test_run_sentiment_emotion_analysis_still_uses_refactored_scoring(pipes):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    from datetime import datetime, timedelta, timezone

    import matplotlib

    matplotlib.use("Agg")
    from telegram_scraper.notebook_pipeline import RawMessage

    start = datetime(2026, 4, 6, tzinfo=timezone.utc)
    messages = [
        RawMessage(
            channel_id=1,
            message_id=index,
            timestamp=start + timedelta(hours=index),
            sender_id=None,
            sender_name=None,
            text="Rocket attack" if index % 2 else "Peace rally",
        )
        for index in range(8)
    ]
    result = sentiment.run_sentiment_emotion_analysis(messages, channel_label="Test")
    assert set(result.sentiment_emotion_df["dominant_sentiment"]) == {"negative", "positive"}
    assert len(result.sentiment_emotion_df) == 8
    assert pipes[0].calls[0][1]["max_length"] == 512
