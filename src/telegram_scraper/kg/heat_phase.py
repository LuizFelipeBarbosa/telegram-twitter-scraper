# src/telegram_scraper/kg/heat_phase.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram_scraper.kg.models import NodeHeatSnapshot


class PhaseNotSupported(Exception):
    """Raised when phase filtering is requested for a non-phase-eligible kind."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"phase filter not supported for kind={kind}")
        self.kind = kind


@dataclass(frozen=True)
class HeatPhaseThresholds:
    emerging_1d_min: float
    emerging_31d_max: float
    fading_31d_min: float
    fading_1d_max: float
    sustained_delta_max: float
    flash_3d_min: float
    flash_7d_max: float


DEFAULT_THEME_HEAT_THRESHOLDS = HeatPhaseThresholds(
    emerging_1d_min=0.10,
    emerging_31d_max=0.02,
    fading_31d_min=0.05,
    fading_1d_max=0.01,
    sustained_delta_max=0.02,
    flash_3d_min=0.10,
    flash_7d_max=0.02,
)

DEFAULT_EVENT_HEAT_THRESHOLDS = HeatPhaseThresholds(
    emerging_1d_min=0.10,
    emerging_31d_max=0.02,
    fading_31d_min=0.05,
    fading_1d_max=0.01,
    sustained_delta_max=0.02,
    flash_3d_min=0.10,
    flash_7d_max=0.02,
)


def classify_phase(
    snapshot: NodeHeatSnapshot,
    thresholds: HeatPhaseThresholds | None,
) -> str | None:
    if thresholds is None:
        return None
    t = thresholds
    if snapshot.heat_1d > t.emerging_1d_min and snapshot.heat_31d < t.emerging_31d_max:
        return "emerging"
    if snapshot.heat_31d > t.fading_31d_min and snapshot.heat_1d < t.fading_1d_max:
        return "fading"
    if snapshot.heat_3d > t.flash_3d_min and snapshot.heat_7d < t.flash_7d_max:
        return "flash_event"
    if abs(snapshot.heat_1d - snapshot.heat_31d) < t.sustained_delta_max:
        return "sustained"
    return "steady"
