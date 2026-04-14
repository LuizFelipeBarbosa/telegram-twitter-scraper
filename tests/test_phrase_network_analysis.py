from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("networkx")
pytest.importorskip("nltk")
pytest.importorskip("plotly")
import matplotlib.pyplot as plt

from telegram_scraper.analysis.phrases import PhraseNetworkConfig, run_phrase_network_analysis
from telegram_scraper.notebook_pipeline import RawMessage


def build_message(*, message_id: int, timestamp: datetime, text: str) -> RawMessage:
    return RawMessage(
        channel_id=777,
        message_id=message_id,
        timestamp=timestamp,
        sender_id=None,
        sender_name=None,
        text=text,
        raw_json={},
    )


def test_run_phrase_network_analysis_scores_phrases_and_temporal_shifts() -> None:
    messages = [
        build_message(
            message_id=1,
            timestamp=datetime(2026, 4, 6, 0, 0, tzinfo=timezone.utc),
            text="Zionist regime expands aggression. Operation True Promise continues.",
        ),
        build_message(
            message_id=2,
            timestamp=datetime(2026, 4, 6, 2, 0, tzinfo=timezone.utc),
            text="The Zionist regime fears retaliation as Operation True Promise advances.",
        ),
        build_message(
            message_id=3,
            timestamp=datetime(2026, 4, 6, 4, 0, tzinfo=timezone.utc),
            text="Resistance axis condemns the Zionist regime and praises Operation True Promise.",
        ),
        build_message(
            message_id=4,
            timestamp=datetime(2026, 4, 6, 6, 0, tzinfo=timezone.utc),
            text="Resistance axis says the Zionist regime failed.",
        ),
        build_message(
            message_id=5,
            timestamp=datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
            text="Nuclear deal talks resume as Resistance axis observers watch.",
        ),
        build_message(
            message_id=6,
            timestamp=datetime(2026, 4, 8, 2, 0, tzinfo=timezone.utc),
            text="The nuclear deal dominates diplomacy and Resistance axis statements.",
        ),
        build_message(
            message_id=7,
            timestamp=datetime(2026, 4, 8, 4, 0, tzinfo=timezone.utc),
            text="Analysts say nuclear deal momentum grows after Operation True Promise.",
        ),
        build_message(
            message_id=8,
            timestamp=datetime(2026, 4, 8, 6, 0, tzinfo=timezone.utc),
            text="Officials say nuclear deal terms are clear.",
        ),
    ]

    result = run_phrase_network_analysis(
        messages,
        channel_label="Phrase Test Channel",
        entity_terms={"zionist", "nuclear"},
        config=PhraseNetworkConfig(
            min_bigram_freq=2,
            min_trigram_freq=2,
            min_bigram_pmi=0.0,
            min_trigram_pmi=0.0,
            top_bigrams=10,
            top_trigrams=10,
            network_edge_limit=10,
            temporal_top_k=10,
            temporal_network_edge_limit=10,
            temporal_min_freq=2,
        ),
    )

    bigram_lookup = result.phrase_bigram_df.set_index("bigram")
    trigram_lookup = result.phrase_trigram_df.set_index("trigram")
    temporal_lookup = result.phrase_temporal_change_df.set_index("bigram")

    assert len(result.phrase_messages_df) == 8
    assert bigram_lookup.loc["zionist regime", "frequency"] == 4
    assert bigram_lookup.loc["nuclear deal", "frequency"] == 4
    assert bigram_lookup.loc["resistance axis", "frequency"] == 4
    assert bool(bigram_lookup.loc["zionist regime", "contains_entity_term"])
    assert bool(bigram_lookup.loc["nuclear deal", "contains_entity_term"])

    assert trigram_lookup.loc["operation true promise", "frequency"] == 4

    assert temporal_lookup.loc["zionist regime", "status"] == "dropped"
    assert temporal_lookup.loc["nuclear deal", "status"] == "new"
    assert temporal_lookup.loc["resistance axis", "status"] == "retained"

    assert result.phrase_bigram_graph.has_edge("zionist", "regime")
    assert result.phrase_bigram_graph.has_edge("nuclear", "deal")
    assert result.phrase_network_summary_df.iloc[0]["network_edges"] >= 3

    assert result.phrase_network_fig is not None
    assert result.phrase_bigram_bar_fig is not None
    assert result.phrase_temporal_fig is not None

    assert set(result.phrase_temporal_bigram_df["period_half"]) == {"First Half", "Second Half"}
    assert isinstance(result.phrase_network_nodes_df, pd.DataFrame)
    assert isinstance(result.phrase_network_edges_df, pd.DataFrame)

    plt.close("all")
