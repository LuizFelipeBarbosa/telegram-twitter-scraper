# Node Heat Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the theme-only `theme_heat_view` to a unified `node_heat_view` covering all six node kinds, with event hierarchy aggregation, configurable phase thresholds, and a parameterized `/api/nodes/heat` endpoint that fixes the `get_graph_snapshot` ranking bug.

**Architecture:** Five incremental PRs. PR 1 generalizes the view and introduces Python-based phase classification. PR 2 makes thresholds configurable via `KGSettings`. PR 3 activates event heat with hierarchy aggregation (requires the event-hierarchy branch). PR 4 exposes heat for actor/place kinds. PR 5 adds the public API endpoint and rewires `get_graph_snapshot` to use heat for all kinds.

**Tech Stack:** Python 3.9+, Postgres 16 (materialized views, recursive CTEs), FastAPI, psycopg, Redis caching, unittest

**Spec:** `docs/superpowers/specs/2026-04-12-node-heat-generalization-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `src/telegram_scraper/kg/heat_phase.py` | `HeatPhaseThresholds` dataclass, `classify_phase` pure function, `PhaseNotSupported` exception, default threshold constants |
| `tests/kg/test_heat_phase.py` | Unit tests for phase classification |
| `tests/kg/test_node_heat_view_postgres.py` | Optional Postgres integration tests for hierarchy aggregation |
| `scripts/benchmark_node_heat_view.py` | One-shot refresh benchmark (not committed as test; run manually before merging PR 3, result recorded in PR description) |

### Modified Files

| File | What Changes |
|---|---|
| `src/telegram_scraper/kg/models.py` | `ThemeHeatSnapshot` renamed to `NodeHeatSnapshot` (adds `kind` field), old name kept as alias |
| `src/telegram_scraper/kg/repository.py` | `SCHEMA_STATEMENTS` (drop old view, create `node_heat_view`), new `list_node_heat_rows` + `refresh_node_heat_view`, `list_theme_heat` becomes wrapper |
| `src/telegram_scraper/kg/interfaces.py` | New protocol methods: `list_node_heat_rows`, `refresh_node_heat_view` |
| `src/telegram_scraper/kg/services.py` | Refresh call rename, `themes_now`/`themes_emerging`/`themes_fading` use new path |
| `src/telegram_scraper/kg/config.py` | `KGSettings` gains `theme_heat_thresholds`, `event_heat_thresholds` fields |
| `src/telegram_scraper/kg/__init__.py` | Exports `NodeHeatSnapshot`, `HeatPhaseThresholds` |
| `src/telegram_scraper/viz_api/queries.py` | `list_node_heat` replaces `list_theme_heat`, `get_graph_snapshot` rewired |
| `src/telegram_scraper/viz_api/app.py` | New `/api/nodes/heat` route, `/api/themes/heat` becomes alias |
| `src/telegram_scraper/viz_api/schemas.py` | `NodeHeatRow`, `NodesHeatResponse` added |
| `tests/kg/test_repository_schema.py` | Assertions updated for `node_heat_view` |
| `tests/kg/test_kg_config.py` | Threshold config tests |
| `tests/kg/test_services.py` | Fake repository gains `list_node_heat_rows`, existing theme tests preserved |
| `tests/viz_api/test_queries.py` | Tests for `list_node_heat`, phase filtering |
| `tests/viz_api/test_api.py` | `/api/nodes/heat` tests, legacy compat, ranking regression |

---

## PR 1: Generalize View, Theme-Only Behavior Preserved

### Task 1: Phase classification pure function

**Files:**
- Create: `src/telegram_scraper/kg/heat_phase.py`
- Create: `tests/kg/test_heat_phase.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/kg/test_heat_phase.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'telegram_scraper.kg.heat_phase'`

- [ ] **Step 3: Implement heat_phase.py**

```python
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
    if abs(snapshot.heat_1d - snapshot.heat_31d) < t.sustained_delta_max:
        return "sustained"
    if snapshot.heat_3d > t.flash_3d_min and snapshot.heat_7d < t.flash_7d_max:
        return "flash_event"
    return "steady"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/kg/test_heat_phase.py -v`
Expected: PASS (8 tests) — Note: the `NodeHeatSnapshot` import will fail because the model doesn't exist yet. If so, proceed to Task 2 and return.

- [ ] **Step 5: Commit**

```bash
git add src/telegram_scraper/kg/heat_phase.py tests/kg/test_heat_phase.py
git commit -m "feat(kg): add phase classification pure function with default thresholds"
```

---

### Task 2: NodeHeatSnapshot model

**Files:**
- Modify: `src/telegram_scraper/kg/models.py` (lines 8-9, 172-184)
- Modify: `src/telegram_scraper/kg/__init__.py` (lines 5-37)

- [ ] **Step 1: Write the model change**

In `src/telegram_scraper/kg/models.py`, rename `ThemeHeatSnapshot` to `NodeHeatSnapshot`, add `kind` field, and create alias.

Replace the current `ThemeHeatSnapshot` dataclass (lines 172-184) with:

```python
@dataclass(frozen=True)
class NodeHeatSnapshot:
    node_id: str
    kind: str
    slug: str
    display_name: str
    article_count: int
    heat_1d: float
    heat_3d: float
    heat_5d: float
    heat_7d: float
    heat_14d: float
    heat_31d: float
    phase: str | None = None


ThemeHeatSnapshot = NodeHeatSnapshot
```

- [ ] **Step 2: Update `__init__.py` exports**

In `src/telegram_scraper/kg/__init__.py`, add `NodeHeatSnapshot` to the import list and `__all__`:

Add to the imports from `models`:
```python
NodeHeatSnapshot,
```

Add to `__all__`:
```python
"HeatPhaseThresholds",
"NodeHeatSnapshot",
```

Also add `HeatPhaseThresholds` to the imports at the top of the file:
```python
from telegram_scraper.kg.heat_phase import HeatPhaseThresholds
```

- [ ] **Step 3: Run all existing tests to verify nothing broke**

Run: `uv run pytest -q`
Expected: All 45+ tests pass. The `ThemeHeatSnapshot` alias preserves backward compat everywhere it's imported.

- [ ] **Step 4: Run the heat_phase tests that depend on NodeHeatSnapshot**

Run: `uv run pytest tests/kg/test_heat_phase.py -v`
Expected: All 8 tests pass now that `NodeHeatSnapshot` exists.

- [ ] **Step 5: Commit**

```bash
git add src/telegram_scraper/kg/models.py src/telegram_scraper/kg/__init__.py
git commit -m "refactor(kg): rename ThemeHeatSnapshot to NodeHeatSnapshot with kind field"
```

---

### Task 3: Replace theme_heat_view with node_heat_view in schema

**Files:**
- Modify: `src/telegram_scraper/kg/repository.py` (lines 184-234)
- Modify: `tests/kg/test_repository_schema.py`

- [ ] **Step 1: Update test assertions for the new view**

In `tests/kg/test_repository_schema.py`, replace the assertions about `theme_heat_view` and phase SQL with assertions about `node_heat_view`:

```python
# Replace existing theme_heat_view assertions with:
self.assertIn("DROP MATERIALIZED VIEW IF EXISTS theme_heat_view CASCADE", schema)
self.assertIn("CREATE MATERIALIZED VIEW IF NOT EXISTS node_heat_view", schema)
self.assertIn("WITH RECURSIVE", schema)
self.assertIn("node_descendants", schema)
self.assertIn("idx_node_heat_view_node", schema)
self.assertIn("idx_node_heat_view_kind", schema)
# Phase CASE should be gone from SQL
self.assertNotIn("THEN 'emerging'", schema)
self.assertNotIn("THEN 'fading'", schema)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/kg/test_repository_schema.py -v`
Expected: FAIL — old view still exists, new assertions don't match.

- [ ] **Step 3: Update SCHEMA_STATEMENTS in repository.py**

In `src/telegram_scraper/kg/repository.py`, replace lines 184-234 (the `theme_heat_view` definition and its index) with:

```python
    "DROP MATERIALIZED VIEW IF EXISTS theme_heat_view CASCADE",
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS node_heat_view AS
    WITH RECURSIVE
    windows AS (
        SELECT unnest(ARRAY[1, 3, 5, 7, 14, 31]) AS days
    ),
    window_totals AS (
        SELECT w.days, COUNT(*) AS total
        FROM windows w
        JOIN story_units su ON su.timestamp_start >= NOW() - (w.days || ' days')::INTERVAL
        GROUP BY w.days
    ),
    node_descendants AS (
        SELECT node_id AS root_id, node_id AS descendant_id, 0 AS depth
        FROM nodes
        WHERE status = 'active'

        UNION ALL

        SELECT nd.root_id, n.node_id, nd.depth + 1
        FROM node_descendants nd
        JOIN nodes n ON n.parent_node_id = nd.descendant_id
        WHERE n.status = 'active' AND nd.depth < 10
    ),
    window_counts AS (
        SELECT
            nd.root_id AS node_id,
            w.days,
            COUNT(DISTINCT su.story_id) AS cnt
        FROM node_descendants nd
        JOIN story_nodes sn ON sn.node_id = nd.descendant_id
        JOIN story_units su ON su.story_id = sn.story_id
        CROSS JOIN windows w
        WHERE su.timestamp_start >= NOW() - (w.days || ' days')::INTERVAL
        GROUP BY nd.root_id, w.days
    ),
    base AS (
        SELECT
            n.node_id,
            n.kind,
            n.slug,
            n.display_name,
            n.article_count,
            COALESCE(MAX(CASE WHEN wc.days = 1  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_1d,
            COALESCE(MAX(CASE WHEN wc.days = 3  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_3d,
            COALESCE(MAX(CASE WHEN wc.days = 5  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_5d,
            COALESCE(MAX(CASE WHEN wc.days = 7  THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_7d,
            COALESCE(MAX(CASE WHEN wc.days = 14 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_14d,
            COALESCE(MAX(CASE WHEN wc.days = 31 THEN wc.cnt::DOUBLE PRECISION / NULLIF(wt.total, 0) END), 0) AS heat_31d
        FROM nodes n
        LEFT JOIN window_counts wc ON wc.node_id = n.node_id
        LEFT JOIN window_totals wt ON wt.days = wc.days
        WHERE n.status = 'active'
        GROUP BY n.node_id, n.kind, n.slug, n.display_name, n.article_count
    )
    SELECT * FROM base
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_node_heat_view_node ON node_heat_view (node_id)",
    "CREATE INDEX IF NOT EXISTS idx_node_heat_view_kind ON node_heat_view (kind)",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/kg/test_repository_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/telegram_scraper/kg/repository.py tests/kg/test_repository_schema.py
git commit -m "refactor(kg): replace theme_heat_view with node_heat_view"
```

---

### Task 4: Repository methods — list_node_heat_rows + refresh_node_heat_view

**Files:**
- Modify: `src/telegram_scraper/kg/repository.py` (refresh at ~1293, list_theme_heat at ~1427, _theme_heat_from_row at ~1760)
- Modify: `src/telegram_scraper/kg/interfaces.py` (lines 137, 151)

- [ ] **Step 1: Add `list_node_heat_rows` and `refresh_node_heat_view` to the protocol**

In `src/telegram_scraper/kg/interfaces.py`, add after the existing `refresh_theme_heat_view` and `list_theme_heat` protocol methods:

```python
    def refresh_node_heat_view(self) -> None: ...

    def list_node_heat_rows(self, *, kind: str) -> list[NodeHeatSnapshot]: ...
```

Add `NodeHeatSnapshot` to the imports from `telegram_scraper.kg.models` at the top of the file.

- [ ] **Step 2: Implement `refresh_node_heat_view` in the repository**

In `src/telegram_scraper/kg/repository.py`, rename the `refresh_theme_heat_view` method body (around line 1293):

```python
    def refresh_node_heat_view(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("REFRESH MATERIALIZED VIEW node_heat_view")
            connection.commit()

    def refresh_theme_heat_view(self) -> None:
        self.refresh_node_heat_view()
```

The old method calls the new one for backward compat.

- [ ] **Step 3: Implement `list_node_heat_rows` in the repository**

Add a new method to `PostgresStoryRepository` and update `_theme_heat_from_row` to `_node_heat_from_row`:

```python
    def list_node_heat_rows(self, *, kind: str) -> list[NodeHeatSnapshot]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT node_id, kind, slug, display_name, article_count,
                           heat_1d, heat_3d, heat_5d, heat_7d, heat_14d, heat_31d
                    FROM node_heat_view
                    WHERE kind = %s
                    ORDER BY heat_1d DESC, heat_3d DESC, display_name ASC
                    """,
                    (kind,),
                )
                rows = cursor.fetchall()
        return [_node_heat_from_row(row) for row in rows]
```

Replace `_theme_heat_from_row` (around line 1760) with:

```python
def _node_heat_from_row(row: Sequence[Any]) -> NodeHeatSnapshot:
    return NodeHeatSnapshot(
        node_id=str(row[0]),
        kind=str(row[1]),
        slug=str(row[2]),
        display_name=str(row[3]),
        article_count=int(row[4]),
        heat_1d=float(row[5]),
        heat_3d=float(row[6]),
        heat_5d=float(row[7]),
        heat_7d=float(row[8]),
        heat_14d=float(row[9]),
        heat_31d=float(row[10]),
        phase=None,
    )
```

- [ ] **Step 4: Rewrite `list_theme_heat` as a wrapper**

Replace the existing `list_theme_heat` method (around line 1427) with a wrapper that uses the new method plus `classify_phase`:

```python
    def list_theme_heat(self, *, phase: str | None = None, limit: int | None = None) -> list[NodeHeatSnapshot]:
        from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS, classify_phase

        rows = self.list_node_heat_rows(kind="theme")
        classified = [
            replace(row, phase=classify_phase(row, DEFAULT_THEME_HEAT_THRESHOLDS))
            for row in rows
        ]
        if phase is not None:
            classified = [r for r in classified if r.phase == phase]
        if limit is not None:
            classified = classified[:limit]
        return classified
```

Add `from dataclasses import replace` to the file's imports if not already present.

- [ ] **Step 5: Update the import of NodeHeatSnapshot in repository.py**

In the imports at the top of `repository.py`, add `NodeHeatSnapshot` to the import from `telegram_scraper.kg.models`. Replace the `ThemeHeatSnapshot` import with `NodeHeatSnapshot` (or add alongside — the alias means both names work).

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -q`
Expected: All tests pass. The `list_theme_heat` wrapper preserves the same public behavior. The `refresh_theme_heat_view` backward-compat wrapper keeps service-layer callers working.

- [ ] **Step 7: Commit**

```bash
git add src/telegram_scraper/kg/repository.py src/telegram_scraper/kg/interfaces.py
git commit -m "feat(kg): add list_node_heat_rows and refresh_node_heat_view with theme wrappers"
```

---

### Task 5: Wire services layer to new refresh method

**Files:**
- Modify: `src/telegram_scraper/kg/services.py` (line ~567 at HEAD for refresh call)
- Modify: `tests/kg/test_services.py` (fake repository)

- [ ] **Step 1: Update the fake repository in test_services.py**

In `tests/kg/test_services.py`, add `list_node_heat_rows` and `refresh_node_heat_view` to the fake repository class. Keep the existing `refresh_theme_heat_view` and `list_theme_heat` — they should continue to work via the same data.

Add a `list_node_heat_rows` method to the fake that reuses `theme_heat_rows`:

```python
    def refresh_node_heat_view(self):
        self.refresh_theme_heat_view()

    def list_node_heat_rows(self, *, kind):
        if kind != "theme":
            return []
        return [replace(row, phase=None) for row in self.theme_heat_rows]
```

Add `from dataclasses import replace` to the file's imports if not already present.

- [ ] **Step 2: Update services.py refresh call**

In `src/telegram_scraper/kg/services.py`, find the call to `self.repository.refresh_theme_heat_view()` and change it to:

```python
self.repository.refresh_node_heat_view()
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -q`
Expected: All tests pass. `themes_now`, `themes_emerging`, `themes_fading` still work because they call `self.repository.list_theme_heat(...)` which still exists.

- [ ] **Step 4: Commit**

```bash
git add src/telegram_scraper/kg/services.py tests/kg/test_services.py
git commit -m "refactor(kg): wire segment worker to refresh_node_heat_view"
```

---

### Task 6: Verify PR 1 is behavior-preserving

**Files:** No new changes — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass with zero failures.

- [ ] **Step 2: Run the viz-web tests**

Run: `cd viz-web && npm run test -- --run`
Expected: All 75+ tests pass (no backend changes affect frontend tests, but verify anyway).

- [ ] **Step 3: Verify the CLI still loads**

Run: `uv run telegram-scraper --help`
Expected: All commands listed, no import errors.

- [ ] **Step 4: Tag PR 1 completion**

```bash
git log --oneline -5
```

Review the last commits and confirm they form a clean, reviewable PR 1.

---

## PR 2: Move Phase Thresholds into KGSettings

### Task 7: Add threshold fields to KGSettings

**Files:**
- Modify: `src/telegram_scraper/kg/config.py` (lines 12-68)
- Modify: `tests/kg/test_kg_config.py`

- [ ] **Step 1: Write failing tests for threshold config**

Add to `tests/kg/test_kg_config.py`:

```python
from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS, DEFAULT_EVENT_HEAT_THRESHOLDS, HeatPhaseThresholds


class KGSettingsHeatThresholdTests(unittest.TestCase):
    def test_defaults_populated(self):
        settings = build_settings()
        self.assertEqual(settings.theme_heat_thresholds, DEFAULT_THEME_HEAT_THRESHOLDS)
        self.assertEqual(settings.event_heat_thresholds, DEFAULT_EVENT_HEAT_THRESHOLDS)

    def test_theme_phase_disabled(self):
        settings = build_settings(KG_THEME_HEAT_PHASE_ENABLED="0")
        self.assertIsNone(settings.theme_heat_thresholds)
        self.assertEqual(settings.event_heat_thresholds, DEFAULT_EVENT_HEAT_THRESHOLDS)

    def test_event_phase_disabled(self):
        settings = build_settings(KG_EVENT_HEAT_PHASE_ENABLED="0")
        self.assertEqual(settings.theme_heat_thresholds, DEFAULT_THEME_HEAT_THRESHOLDS)
        self.assertIsNone(settings.event_heat_thresholds)

    def test_theme_thresholds_json_override(self):
        import json
        custom = {
            "emerging_1d_min": 0.20,
            "emerging_31d_max": 0.03,
            "fading_31d_min": 0.08,
            "fading_1d_max": 0.02,
            "sustained_delta_max": 0.03,
            "flash_3d_min": 0.20,
            "flash_7d_max": 0.03,
        }
        settings = build_settings(KG_THEME_HEAT_THRESHOLDS_JSON=json.dumps(custom))
        self.assertEqual(settings.theme_heat_thresholds.emerging_1d_min, 0.20)
        self.assertEqual(settings.theme_heat_thresholds.flash_3d_min, 0.20)
```

Reuse the existing `build_settings` helper in the test file (it calls `KGSettings.from_mapping`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/kg/test_kg_config.py::KGSettingsHeatThresholdTests -v`
Expected: FAIL — `KGSettings` doesn't have `theme_heat_thresholds` yet.

- [ ] **Step 3: Add threshold fields to KGSettings**

In `src/telegram_scraper/kg/config.py`, add the new fields to the `KGSettings` dataclass (after `event_match_window_days`):

```python
    theme_heat_thresholds: HeatPhaseThresholds | None
    event_heat_thresholds: HeatPhaseThresholds | None
```

Add the import at the top:
```python
from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS, DEFAULT_EVENT_HEAT_THRESHOLDS, HeatPhaseThresholds
```

In `from_mapping`, add parsing logic at the end of the return statement:

```python
            theme_heat_thresholds=_parse_heat_thresholds(
                values, "THEME", DEFAULT_THEME_HEAT_THRESHOLDS,
            ),
            event_heat_thresholds=_parse_heat_thresholds(
                values, "EVENT", DEFAULT_EVENT_HEAT_THRESHOLDS,
            ),
```

Add the helper function before the class:

```python
import json as _json


def _parse_heat_thresholds(
    values: Mapping[str, str],
    kind_prefix: str,
    defaults: HeatPhaseThresholds,
) -> HeatPhaseThresholds | None:
    enabled_key = f"KG_{kind_prefix}_HEAT_PHASE_ENABLED"
    if values.get(enabled_key, "1").strip() == "0":
        return None
    json_key = f"KG_{kind_prefix}_HEAT_THRESHOLDS_JSON"
    raw_json = values.get(json_key, "").strip()
    if not raw_json:
        return defaults
    parsed = _json.loads(raw_json)
    return HeatPhaseThresholds(**parsed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/kg/test_kg_config.py -v`
Expected: All tests pass (both old and new).

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -q`
Expected: All tests pass. The new fields have defaults so existing `build_settings()` calls in other test files don't break.

- [ ] **Step 6: Commit**

```bash
git add src/telegram_scraper/kg/config.py tests/kg/test_kg_config.py
git commit -m "feat(kg): add heat phase threshold fields to KGSettings"
```

---

### Task 8: Wire VisualizationQueries to use configurable thresholds

**Files:**
- Modify: `src/telegram_scraper/viz_api/queries.py`
- Modify: `src/telegram_scraper/viz_api/app.py` (line 24 — queries init)
- Modify: `tests/viz_api/test_queries.py`

- [ ] **Step 1: Update VisualizationQueries constructor**

In `src/telegram_scraper/viz_api/queries.py`, update the constructor to accept thresholds:

```python
from telegram_scraper.kg.heat_phase import HeatPhaseThresholds


class VisualizationQueries:
    def __init__(
        self,
        database_url: str,
        *,
        theme_heat_thresholds: HeatPhaseThresholds | None = None,
        event_heat_thresholds: HeatPhaseThresholds | None = None,
    ):
        self.repository = PostgresStoryRepository(database_url)
        self.service = KGQueryService(self.repository)
        self.theme_heat_thresholds = theme_heat_thresholds
        self.event_heat_thresholds = event_heat_thresholds

    def thresholds_for(self, kind: str) -> HeatPhaseThresholds | None:
        if kind == "theme":
            return self.theme_heat_thresholds
        if kind == "event":
            return self.event_heat_thresholds
        return None
```

- [ ] **Step 2: Update create_app to pass thresholds from settings**

In `src/telegram_scraper/viz_api/app.py`, update the `queries` initialization (line 24):

```python
    queries = VisualizationQueries(
        settings.database_url,
        theme_heat_thresholds=settings.theme_heat_thresholds,
        event_heat_thresholds=settings.event_heat_thresholds,
    )
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -q`
Expected: All tests pass. Existing test code that constructs `VisualizationQueries("...")` still works because the new params are keyword-only with defaults.

- [ ] **Step 4: Commit**

```bash
git add src/telegram_scraper/viz_api/queries.py src/telegram_scraper/viz_api/app.py
git commit -m "feat(viz-api): wire configurable heat thresholds into VisualizationQueries"
```

---

## PR 3: Event Heat with Hierarchy Aggregation

> **Prerequisite:** The event-hierarchy branch (currently uncommitted working-tree changes adding `parent_node_id` to nodes, `kg/event_hierarchy.py`, and related services.py updates) must be committed and merged before starting this PR.

### Task 9: Activate event heat + Postgres integration tests

**Files:**
- Create: `tests/kg/test_node_heat_view_postgres.py`
- Modify: `tests/kg/test_heat_phase.py` (add event threshold test)

- [ ] **Step 1: Add event phase test to test_heat_phase.py**

Append to `tests/kg/test_heat_phase.py`:

```python
from telegram_scraper.kg.heat_phase import DEFAULT_EVENT_HEAT_THRESHOLDS


class EventPhaseTests(unittest.TestCase):
    def test_event_emerging(self):
        snap = _snap(heat_1d=0.15, heat_31d=0.01)
        snap = replace(snap, kind="event")
        self.assertEqual(classify_phase(snap, DEFAULT_EVENT_HEAT_THRESHOLDS), "emerging")

    def test_event_flash(self):
        snap = _snap(heat_3d=0.15, heat_7d=0.01)
        snap = replace(snap, kind="event")
        self.assertEqual(classify_phase(snap, DEFAULT_EVENT_HEAT_THRESHOLDS), "flash_event")
```

Add `from dataclasses import replace` to the file's imports.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/kg/test_heat_phase.py -v`
Expected: All 10 tests pass.

- [ ] **Step 3: Create Postgres integration test file**

```python
# tests/kg/test_node_heat_view_postgres.py
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import pytest

if not os.environ.get("KG_PG_INTEGRATION"):
    pytest.skip(
        "set KG_PG_INTEGRATION=1 and point DATABASE_URL at a disposable db",
        allow_module_level=True,
    )

from telegram_scraper.kg.repository import PostgresStoryRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class NodeHeatViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/telegram_kg")
        cls.repo = PostgresStoryRepository(url)
        cls.repo.ensure_schema()

    def setUp(self):
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM story_nodes")
                cur.execute("DELETE FROM story_semantics")
                cur.execute("DELETE FROM story_units")
                cur.execute("DELETE FROM nodes")
            conn.commit()

    def _insert_node(self, *, node_id, kind, slug, status="active", parent_node_id=None):
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO nodes (node_id, kind, slug, display_name, canonical_name,
                       normalized_name, summary, aliases, status, label_source, article_count,
                       parent_node_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (node_id, kind, slug, slug, slug, slug, None, [], status, "test", 0, parent_node_id),
                )
            conn.commit()

    def _insert_story(self, *, story_id, channel_id=1, minutes_ago=0):
        ts = _now() - timedelta(minutes=minutes_ago)
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO story_units (story_id, channel_id, timestamp_start, timestamp_end,
                       message_ids, combined_text, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (story_id, channel_id, ts, ts, [1], "text", _now()),
                )
            conn.commit()

    def _assign(self, story_id, node_id):
        with self.repo._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO story_nodes (story_id, node_id, confidence, is_primary_event)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (story_id, node_id, 1.0, False),
                )
            conn.commit()

    def _refresh(self):
        self.repo.refresh_node_heat_view()

    def test_leaf_event_heat_equals_direct_assignment(self):
        event_id = _uuid()
        story_id = _uuid()
        self._insert_node(node_id=event_id, kind="event", slug="leaf")
        self._insert_story(story_id=story_id, minutes_ago=10)
        self._assign(story_id, event_id)
        self._refresh()
        rows = self.repo.list_node_heat_rows(kind="event")
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0].heat_1d, 0)

    def test_parent_event_rolls_up_child(self):
        parent_id = _uuid()
        child_id = _uuid()
        story_id = _uuid()
        self._insert_node(node_id=parent_id, kind="event", slug="parent")
        self._insert_node(node_id=child_id, kind="event", slug="child", parent_node_id=parent_id)
        self._insert_story(story_id=story_id, minutes_ago=10)
        self._assign(story_id, child_id)
        self._refresh()
        rows = {r.slug: r for r in self.repo.list_node_heat_rows(kind="event")}
        self.assertGreater(rows["parent"].heat_1d, 0, "parent should have heat from child's story")
        self.assertEqual(rows["parent"].heat_1d, rows["child"].heat_1d)

    def test_no_double_count(self):
        parent_id = _uuid()
        child_id = _uuid()
        story_id = _uuid()
        self._insert_node(node_id=parent_id, kind="event", slug="parent")
        self._insert_node(node_id=child_id, kind="event", slug="child", parent_node_id=parent_id)
        self._insert_story(story_id=story_id, minutes_ago=10)
        self._assign(story_id, parent_id)
        self._assign(story_id, child_id)
        self._refresh()
        rows = {r.slug: r for r in self.repo.list_node_heat_rows(kind="event")}
        self.assertEqual(rows["parent"].heat_1d, rows["child"].heat_1d,
                         "same story on parent+child should not double-count")

    def test_inactive_descendant_excluded(self):
        parent_id = _uuid()
        child_id = _uuid()
        story_id = _uuid()
        self._insert_node(node_id=parent_id, kind="event", slug="parent")
        self._insert_node(node_id=child_id, kind="event", slug="child",
                          parent_node_id=parent_id, status="inactive")
        self._insert_story(story_id=story_id, minutes_ago=10)
        self._assign(story_id, child_id)
        self._refresh()
        rows = self.repo.list_node_heat_rows(kind="event")
        parent_rows = [r for r in rows if r.slug == "parent"]
        self.assertEqual(len(parent_rows), 1)
        self.assertEqual(parent_rows[0].heat_1d, 0.0,
                         "inactive child's stories should not roll up")

    def test_theme_has_no_rollup(self):
        theme_id = _uuid()
        story_id = _uuid()
        self._insert_node(node_id=theme_id, kind="theme", slug="test-theme")
        self._insert_story(story_id=story_id, minutes_ago=10)
        self._assign(story_id, theme_id)
        self._refresh()
        rows = self.repo.list_node_heat_rows(kind="theme")
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0].heat_1d, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run integration tests (requires Postgres)**

Run: `KG_PG_INTEGRATION=1 uv run pytest tests/kg/test_node_heat_view_postgres.py -v`
Expected: All 5 tests pass (assuming Postgres is running via `docker compose up -d postgres`).

- [ ] **Step 5: Verify integration tests are skipped by default**

Run: `uv run pytest tests/kg/test_node_heat_view_postgres.py -v`
Expected: `SKIPPED (set KG_PG_INTEGRATION=1...)`

- [ ] **Step 6: Commit**

```bash
git add tests/kg/test_heat_phase.py tests/kg/test_node_heat_view_postgres.py
git commit -m "test(kg): add event phase tests and Postgres integration tests for hierarchy rollup"
```

---

## PR 4: Heat for Person / Nation / Org / Place

### Task 10: Expose non-phase kinds and add tests

**Files:**
- Modify: `tests/kg/test_heat_phase.py`

- [ ] **Step 1: Add tests for non-phase kinds**

Append to `tests/kg/test_heat_phase.py`:

```python
class NonPhaseKindTests(unittest.TestCase):
    def test_person_returns_none_phase(self):
        snap = replace(_snap(heat_1d=0.15, heat_31d=0.01), kind="person")
        self.assertIsNone(classify_phase(snap, None))

    def test_nation_returns_none_phase(self):
        snap = replace(_snap(heat_1d=0.15, heat_31d=0.01), kind="nation")
        self.assertIsNone(classify_phase(snap, None))

    def test_org_returns_none_phase(self):
        snap = replace(_snap(heat_1d=0.15, heat_31d=0.01), kind="org")
        self.assertIsNone(classify_phase(snap, None))

    def test_place_returns_none_phase(self):
        snap = replace(_snap(heat_1d=0.15, heat_31d=0.01), kind="place")
        self.assertIsNone(classify_phase(snap, None))
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/kg/test_heat_phase.py -v`
Expected: All tests pass — these kinds pass `thresholds=None`, which already returns `None` per Task 1.

- [ ] **Step 3: Commit**

```bash
git add tests/kg/test_heat_phase.py
git commit -m "test(kg): add non-phase kind classification tests"
```

---

## PR 5: Expose /api/nodes/heat + Rewire get_graph_snapshot

### Task 11: Add NodeHeatRow and NodesHeatResponse schemas

**Files:**
- Modify: `src/telegram_scraper/viz_api/schemas.py`

- [ ] **Step 1: Add new schemas**

In `src/telegram_scraper/viz_api/schemas.py`, add after `ThemesHeatResponse`:

```python
class NodeHeatRow(BaseModel):
    node_id: str
    kind: NodeKind
    slug: str
    display_name: str
    article_count: int
    heat: float
    phase: Optional[str] = None


class NodesHeatResponse(BaseModel):
    window: Window
    kind: NodeKind
    total: int
    nodes: List[NodeHeatRow]
```

- [ ] **Step 2: Commit**

```bash
git add src/telegram_scraper/viz_api/schemas.py
git commit -m "feat(viz-api): add NodeHeatRow and NodesHeatResponse schemas"
```

---

### Task 12: Add list_node_heat to VisualizationQueries

**Files:**
- Modify: `src/telegram_scraper/viz_api/queries.py`

- [ ] **Step 1: Add the list_node_heat method**

In `src/telegram_scraper/viz_api/queries.py`, add after the existing `list_theme_heat` method:

```python
    def list_node_heat(
        self,
        *,
        kind: str,
        window: Window,
        phase: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        from dataclasses import replace
        from telegram_scraper.kg.heat_phase import PhaseNotSupported, classify_phase

        field_name = WINDOW_FIELD_MAP[window]
        rows = self.repository.list_node_heat_rows(kind=kind)
        thresholds = self.thresholds_for(kind)
        classified = [
            replace(row, phase=classify_phase(row, thresholds))
            for row in rows
        ]
        if phase is not None:
            if thresholds is None:
                raise PhaseNotSupported(kind)
            classified = [r for r in classified if r.phase == phase]
        classified.sort(key=lambda r: (-r.heat_1d, -r.heat_3d, r.display_name))
        total = len(classified)
        paged = classified[offset : offset + limit]
        nodes = [
            {
                "node_id": row.node_id,
                "kind": row.kind,
                "slug": row.slug,
                "display_name": row.display_name,
                "article_count": row.article_count,
                "heat": getattr(row, field_name),
                "phase": row.phase,
            }
            for row in paged
        ]
        return {
            "window": window,
            "kind": kind,
            "total": total,
            "nodes": nodes,
        }
```

- [ ] **Step 2: Commit**

```bash
git add src/telegram_scraper/viz_api/queries.py
git commit -m "feat(viz-api): add list_node_heat query method"
```

---

### Task 13: Add /api/nodes/heat endpoint

**Files:**
- Modify: `src/telegram_scraper/viz_api/app.py`
- Modify: `tests/viz_api/test_api.py`

- [ ] **Step 1: Write failing test for the new endpoint**

Add to `tests/viz_api/test_api.py`:

```python
    def test_nodes_heat_route_returns_schema(self):
        response = client.get("/api/nodes/heat?kind=theme&window=7d")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kind"], "theme")
        self.assertIn("nodes", body)
        self.assertIn("total", body)
        self.assertIn("window", body)

    def test_nodes_heat_rejects_phase_on_non_phase_kind(self):
        response = client.get("/api/nodes/heat?kind=person&phase=emerging")
        self.assertEqual(response.status_code, 400)
```

Update the `FakeVisualizationQueries` class with a `list_node_heat` method and `thresholds_for`:

```python
    def thresholds_for(self, kind):
        from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS
        if kind == "theme":
            return DEFAULT_THEME_HEAT_THRESHOLDS
        return None

    def list_node_heat(self, *, kind, window, phase=None, limit=50, offset=0):
        from telegram_scraper.kg.heat_phase import PhaseNotSupported
        if phase is not None and self.thresholds_for(kind) is None:
            raise PhaseNotSupported(kind)
        return {
            "window": window,
            "kind": kind,
            "total": 1,
            "nodes": [
                {
                    "node_id": "00000000-0000-0000-0000-000000000001",
                    "kind": kind,
                    "slug": "test-node",
                    "display_name": "Test Node",
                    "article_count": 10,
                    "heat": 0.15,
                    "phase": "emerging" if kind in ("theme", "event") else None,
                }
            ],
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/viz_api/test_api.py -v -k "nodes_heat"`
Expected: FAIL — route doesn't exist yet.

- [ ] **Step 3: Add the /api/nodes/heat route to app.py**

In `src/telegram_scraper/viz_api/app.py`, add the new imports and route. Add `NodesHeatResponse` to the schema imports. Then add the handler after the `graph_snapshot` handler:

```python
    @app.get("/api/nodes/heat", response_model=NodesHeatResponse)
    def nodes_heat(
        kind: str = Query(...),
        window: Window = Query(default="7d"),
        phase: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=300),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        from telegram_scraper.kg.heat_phase import PhaseNotSupported
        params = {"kind": kind, "window": window, "phase": phase, "limit": limit, "offset": offset}
        try:
            return cache.get_or_set(
                "nodes_heat",
                params,
                ttl_seconds=15 * 60,
                loader=lambda: queries.list_node_heat(
                    kind=kind, window=window, phase=phase, limit=limit, offset=offset,
                ),
            )
        except PhaseNotSupported as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Add `HTTPException` to the FastAPI imports if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/viz_api/test_api.py -v -k "nodes_heat"`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/telegram_scraper/viz_api/app.py tests/viz_api/test_api.py
git commit -m "feat(viz-api): add GET /api/nodes/heat endpoint"
```

---

### Task 14: Convert /api/themes/heat to thin alias

**Files:**
- Modify: `src/telegram_scraper/viz_api/app.py`
- Modify: `tests/viz_api/test_api.py`

- [ ] **Step 1: Verify existing legacy tests still exist**

Check that `tests/viz_api/test_api.py` has the existing `/api/themes/heat` test. It should assert the response has `themes` and `topics` fields. This test must keep passing.

- [ ] **Step 2: Rewrite the themes_heat handler as an alias**

In `src/telegram_scraper/viz_api/app.py`, replace the `themes_heat` handler:

```python
    @app.get("/api/themes/heat", response_model=ThemesHeatResponse)
    def themes_heat(
        window: Window = Query(default="7d"),
        phase: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=300),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        params = {"window": window, "phase": phase, "limit": limit, "offset": offset}
        return cache.get_or_set(
            "themes_heat",
            params,
            ttl_seconds=15 * 60,
            loader=lambda: _themes_heat_legacy(window, phase, limit, offset),
        )

    def _themes_heat_legacy(window: Window, phase, limit: int, offset: int) -> dict:
        raw = queries.list_node_heat(
            kind="theme", window=window, phase=phase, limit=limit, offset=offset,
        )
        return {
            "window": raw["window"],
            "total": raw["total"],
            "themes": raw["nodes"],
            "topics": raw["nodes"],
        }
```

- [ ] **Step 3: Run legacy tests**

Run: `uv run pytest tests/viz_api/test_api.py -v -k "theme"`
Expected: All existing theme heat tests pass — the response shape is unchanged.

- [ ] **Step 4: Commit**

```bash
git add src/telegram_scraper/viz_api/app.py
git commit -m "refactor(viz-api): convert /api/themes/heat to thin alias over list_node_heat"
```

---

### Task 15: Rewire get_graph_snapshot + ranking regression test

**Files:**
- Modify: `src/telegram_scraper/viz_api/queries.py` (get_graph_snapshot method)
- Modify: `tests/viz_api/test_api.py`

- [ ] **Step 1: Write the ranking regression test**

Add to `tests/viz_api/test_api.py`:

```python
    def test_graph_snapshot_mixed_kinds_ranking(self):
        response = client.get("/api/graph/snapshot?window=7d")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()["nodes"]
        scores = [n["score"] for n in nodes]
        self.assertEqual(scores, sorted(scores, reverse=True),
                         "nodes should be sorted by score descending")
        kinds = [n["kind"] for n in nodes]
        self.assertIn("theme", kinds)
        # Under the old bug, all events would cluster first because score=article_count.
        # Under the fix, events and themes interleave by heat.

    def test_graph_snapshot_phase_filter_drops_non_phase_kinds(self):
        response = client.get("/api/graph/snapshot?phase=emerging&kind=event&kind=person")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()["nodes"]
        kinds_present = {n["kind"] for n in nodes}
        self.assertNotIn("person", kinds_present,
                         "non-phase kinds should be dropped when phase filter is applied")
```

Update `FakeVisualizationQueries.get_graph_snapshot` (or the backing `list_node_heat` mock) to support the new code path. You'll need the fake to return interleaved heat-based scores.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/viz_api/test_api.py -v -k "graph_snapshot"`
Expected: FAIL — `get_graph_snapshot` still uses the old code path.

- [ ] **Step 3: Rewrite get_graph_snapshot in queries.py**

Replace the `get_graph_snapshot` method in `src/telegram_scraper/viz_api/queries.py`:

```python
    def get_graph_snapshot(
        self,
        *,
        window: Window,
        kinds: Sequence[str] | None = None,
        phase: str | None = None,
        limit: int = 300,
        include_children: bool = False,
    ) -> dict[str, object]:
        from dataclasses import asdict, replace
        from telegram_scraper.kg.heat_phase import PhaseNotSupported, classify_phase

        selected_kinds = tuple(kinds or ("event", "theme"))
        ranked_nodes: list[dict[str, object]] = []
        selected_entries: list[NodeListEntry] = []

        for kind in selected_kinds:
            thresholds = self.thresholds_for(kind)
            if phase is not None and thresholds is None:
                continue

            rows = self.repository.list_node_heat_rows(kind=kind)
            field_name = WINDOW_FIELD_MAP[window]

            for row in rows:
                classified_phase = classify_phase(row, thresholds)
                if phase is not None and classified_phase != phase:
                    continue
                heat_value = getattr(row, field_name)
                selected_entries.append(
                    NodeListEntry(
                        node_id=row.node_id,
                        kind=row.kind,
                        slug=row.slug,
                        display_name=row.display_name,
                        summary=None,
                        article_count=row.article_count,
                        last_updated=None,
                    )
                )
                ranked_nodes.append(
                    {
                        "node_id": row.node_id,
                        "kind": row.kind,
                        "slug": row.slug,
                        "display_name": row.display_name,
                        "summary": None,
                        "article_count": row.article_count,
                        "score": heat_value,
                        "heat": heat_value,
                        "phase": classified_phase,
                    }
                )

        ranked_nodes.sort(key=lambda item: (-float(item["score"]), str(item["display_name"]).lower()))
        ranked_nodes = ranked_nodes[:limit]
        selected_entry_lookup = {row.node_id: row for row in selected_entries}
        visible_entries = [
            selected_entry_lookup[str(node["node_id"])]
            for node in ranked_nodes
            if str(node["node_id"]) in selected_entry_lookup
        ]

        relations = self._build_relations(visible_entries)
        return {"window": window, "nodes": ranked_nodes, "relations": relations}
```

Note: the `_build_relations` helper should already exist in the class (it was part of the original `get_graph_snapshot`). If it doesn't exist as a separate method, extract the relations-building block from the original method.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/viz_api/test_api.py -v`
Expected: All tests pass — both the new ranking regression tests and all existing tests.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/telegram_scraper/viz_api/queries.py tests/viz_api/test_api.py
git commit -m "fix(viz-api): rewire get_graph_snapshot to use heat for all kinds

Fixes the ranking bug where events (scored by article_count) always
out-ranked themes (scored by fractional heat) in the mixed landscape
sort. All kinds now use heat as their score, producing a coherent
interleaved ranking.

Intentional behavior change: ?phase= on /api/graph/snapshot now drops
non-phase-eligible kinds entirely instead of passing them through."
```

---

### Task 16: Clean up ThemeHeatSnapshot alias

**Files:**
- Modify: `src/telegram_scraper/kg/models.py`
- Modify: `src/telegram_scraper/kg/__init__.py`

- [ ] **Step 1: Verify ThemeHeatSnapshot is only used as an import alias**

Run: `uv run grep -rn "ThemeHeatSnapshot" src/ tests/`

Review the output. If all usages are either (a) the alias definition itself, (b) imports that can switch to `NodeHeatSnapshot`, or (c) test fixtures that use the alias — proceed with cleanup.

- [ ] **Step 2: Replace remaining ThemeHeatSnapshot usages with NodeHeatSnapshot**

In each file that imports `ThemeHeatSnapshot`, replace with `NodeHeatSnapshot`. Keep the alias in `models.py` for any external consumers, but update all internal references.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor(kg): replace ThemeHeatSnapshot usages with NodeHeatSnapshot"
```

---

### Task 17: Final verification

**Files:** No changes — verification only.

- [ ] **Step 1: Run the full backend test suite**

Run: `uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Run the frontend tests**

Run: `cd viz-web && npm run test -- --run`
Expected: All 75+ tests pass.

- [ ] **Step 3: Build the frontend**

Run: `cd viz-web && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Verify the CLI loads**

Run: `uv run telegram-scraper --help`
Expected: All commands listed.

- [ ] **Step 5: Review the commit log**

Run: `git log --oneline -15`

Verify the commits form clean, reviewable PRs matching the 5-PR structure from the spec.
