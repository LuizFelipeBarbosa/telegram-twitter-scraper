# tests/kg/test_heat_phase.py
from __future__ import annotations

import unittest

from telegram_scraper.kg.heat_phase import (
    DEFAULT_THEME_HEAT_THRESHOLDS,
    HeatPhaseThresholds,
    PhaseNotSupported,
    classify_phase,
)
from telegram_scraper.kg.models import NodeHeatSnapshot


def _snap(
    *,
    heat_1d: float = 0.0,
    heat_3d: float = 0.0,
    heat_5d: float = 0.0,
    heat_7d: float = 0.0,
    heat_14d: float = 0.0,
    heat_31d: float = 0.0,
) -> NodeHeatSnapshot:
    return NodeHeatSnapshot(
        node_id="00000000-0000-0000-0000-000000000001",
        kind="theme",
        slug="test",
        display_name="Test",
        article_count=10,
        heat_1d=heat_1d,
        heat_3d=heat_3d,
        heat_5d=heat_5d,
        heat_7d=heat_7d,
        heat_14d=heat_14d,
        heat_31d=heat_31d,
        phase=None,
    )


class ClassifyPhaseTests(unittest.TestCase):
    def test_emerging(self):
        snap = _snap(heat_1d=0.15, heat_31d=0.01)
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "emerging")

    def test_fading(self):
        snap = _snap(heat_1d=0.005, heat_31d=0.06)
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "fading")

    def test_sustained(self):
        snap = _snap(heat_1d=0.05, heat_31d=0.04)
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "sustained")

    def test_flash_event(self):
        snap = _snap(heat_3d=0.15, heat_7d=0.01)
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "flash_event")

    def test_steady_default(self):
        snap = _snap(heat_1d=0.05, heat_3d=0.04, heat_7d=0.03, heat_31d=0.08)
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "steady")

    def test_all_zeros_is_sustained(self):
        snap = _snap()
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "sustained")

    def test_none_thresholds_returns_none(self):
        snap = _snap(heat_1d=0.15, heat_31d=0.01)
        self.assertIsNone(classify_phase(snap, None))

    def test_cascade_order_emerging_before_sustained(self):
        snap = _snap(heat_1d=0.15, heat_31d=0.015)
        self.assertEqual(classify_phase(snap, DEFAULT_THEME_HEAT_THRESHOLDS), "emerging")


if __name__ == "__main__":
    unittest.main()
