# Node Heat Generalization

Generalize the theme-only heat computation (`theme_heat_view`) to cover all six node kinds, add event hierarchy aggregation, and fix the `get_graph_snapshot` ranking bug where events and themes compete on incompatible scales.

## Motivation

Today, heat is calculated exclusively for `kind='theme'` nodes via a Postgres materialized view (`theme_heat_view`). The `/api/graph/snapshot` endpoint mixes themes and events on the landscape map, scoring themes by fractional heat (`[0, 1]`) and events by raw `article_count` (integers). Because both go through a single descending sort, events always out-rank themes regardless of actual relevance. Generalizing heat to all kinds gives the ranking a single comparable metric.

## Decisions

| Question | Choice | Rationale |
|---|---|---|
| Phase classification scope | Themes and events only | These are the two kinds with natural temporal lifecycles. Other kinds get raw `heat_Nd` values but `phase: null`. |
| API surface | Parameterized `GET /api/nodes/heat?kind=<kind>` with `/api/themes/heat` as a permanent fixed-kind alias | Matches `GET /api/nodes/{kind}/{slug}` convention. One route, one schema, zero legacy breakage. |
| Frontend scope | Backend only | The ranking fix is observable the moment `get_graph_snapshot` returns heat-based scores for all kinds. Frontend polish (phase badges on non-themes, heat in hover cards) is a separate follow-up. |
| Event hierarchy | Include aggregation now | Parent event heat = union of own stories and all active descendants' stories. Depends on the event-hierarchy branch (currently in working tree) merging first. |
| Implementation strategy | Incremental, 5 sequenced PRs | Each PR is independently mergeable and verifiable. The event-hierarchy branch only blocks PR 3. |

## Data Model

### `node_heat_view` materialized view

Replaces `theme_heat_view`. Dropped via `DROP MATERIALIZED VIEW IF EXISTS theme_heat_view CASCADE` and recreated. Safe because the view is stateless (recomputed from `story_units` / `story_nodes` / `nodes` on every refresh).

```sql
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
```

Phase is absent from the view body. Computed in Python at query time (see Phase Classification below).

Indexes:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_node_heat_view_node ON node_heat_view (node_id);
CREATE INDEX IF NOT EXISTS idx_node_heat_view_kind ON node_heat_view (kind);
```

### Denominator

`window_totals` counts all story units in the window with no kind filter. Cross-kind heat values are directly comparable: a theme with `heat_7d = 0.12` and a nation with `heat_7d = 0.35` both represent "share of weekly story volume."

### Hierarchy aggregation

The `node_descendants` recursive CTE walks `parent_node_id` for all kinds. Non-events have `parent_node_id = NULL`, so the recursion returns only `(self, self)` for them. Events with hierarchy contribute rows for the full descendant subtree. `COUNT(DISTINCT su.story_id)` in `window_counts` de-duplicates stories assigned to both a parent event and a child.

Design details:

- **Single heat column per window** (rolled-up). No separate `direct_heat_Nd` column. Leaves get direct heat by construction. Parents get the union-aggregated heat. If the frontend ever needs to distinguish "this event's own news" from "news including sub-events," a two-column extension is the follow-up.
- **`article_count` is NOT rolled up.** The field comes from `n.article_count` on the `nodes` table (maintained by semantic extraction). Changing its semantics would affect every API that surfaces it. Minor inconsistency for parents: `article_count` will be smaller than implied by `heat_Nd * window_total`. Noted as acceptable.
- **Inactive descendants excluded.** Both the anchor and recursive step filter `status = 'active'`. A deactivated child's stories stop contributing to its parent's heat immediately.
- **Depth cap: 10.** Defensive cycle-breaker. Real hierarchies are 1-2 levels deep.

### Model

`ThemeHeatSnapshot` (`kg/models.py:173`) becomes `NodeHeatSnapshot`. Gains one field: `kind: NodeKind`. Otherwise keeps the same shape: `node_id`, `slug`, `display_name`, `article_count`, `heat_1d`..`heat_31d`, `phase`.

`ThemeHeatSnapshot` stays as a type alias (`ThemeHeatSnapshot = NodeHeatSnapshot`) during the transition. Cleaned up in PR 5.

`phase` is `str | None`. Non-phase kinds (person, nation, org, place) always get `None`.

### Refresh

`refresh_theme_heat_view()` renamed to `refresh_node_heat_view()`. Body becomes `REFRESH MATERIALIZED VIEW node_heat_view`. Called from `kg-segment-worker` after each processed batch, same cadence as today.

## Phase Classification

### Location: Python, not SQL

Phase moves out of the materialized view into a pure function in a new file `kg/heat_phase.py`:

```python
@dataclass(frozen=True)
class HeatPhaseThresholds:
    emerging_1d_min: float
    emerging_31d_max: float
    fading_31d_min: float
    fading_1d_max: float
    sustained_delta_max: float
    flash_3d_min: float
    flash_7d_max: float

def classify_phase(
    snapshot: NodeHeatSnapshot,
    thresholds: HeatPhaseThresholds | None,
) -> str | None:
    if thresholds is None:
        return None
    # same CASE semantics as today's SQL, top-to-bottom:
    # emerging → fading → sustained → flash_event → steady
```

`thresholds=None` is the signal for phase-ineligible kinds: the function returns `None` without branching.

### Thresholds in `KGSettings`

Two new fields on `KGSettings`:

```python
theme_heat_thresholds: HeatPhaseThresholds | None
event_heat_thresholds: HeatPhaseThresholds | None
```

`None` means phase disabled for that kind. Controlled by `KG_THEME_HEAT_PHASE_ENABLED=0` / `KG_EVENT_HEAT_PHASE_ENABLED=0` env vars. Threshold values are overridable via optional JSON env vars (`KG_THEME_HEAT_THRESHOLDS_JSON`, `KG_EVENT_HEAT_THRESHOLDS_JSON`); defaults are hardcoded in Python.

### Default values

Theme defaults reproduce today's SQL exactly:

```
emerging_1d_min=0.10, emerging_31d_max=0.02
fading_31d_min=0.05,  fading_1d_max=0.01
sustained_delta_max=0.02
flash_3d_min=0.10,    flash_7d_max=0.02
```

Event defaults start identical to theme defaults. Flagged for calibration once event heat data is observed in production.

### Query-time classification

Repository method `list_node_heat_rows(kind)` returns raw rows (no phase). `VisualizationQueries.list_node_heat()` classifies each row, filters by phase if requested, sorts by `heat_1d DESC, heat_3d DESC, display_name ASC`, and paginates. Volumes (~hundreds to low thousands of active nodes) make this cheap; results are Redis-cached.

### Known issue carried forward

The sort key is always `heat_1d` regardless of the `?window=` query parameter. Fixing this is a separate change.

## API Surface

### New endpoint: `GET /api/nodes/heat`

```
GET /api/nodes/heat?kind=<kind>&window=<Nd>&phase=<phase>&limit=<n>&offset=<n>
```

- `kind` (required): `event`, `person`, `nation`, `org`, `place`, `theme`.
- `window`: default `7d`.
- `phase` (optional): `emerging`, `fading`, `sustained`, `flash_event`, `steady`. Returns HTTP 400 if provided for a non-phase-eligible kind.
- `limit`: default 50, max 300.
- `offset`: default 0.

Response schema:

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

### Legacy alias: `GET /api/themes/heat`

Stays forever. The handler calls `list_node_heat(kind='theme', ...)` and reshapes the response into the legacy `ThemesHeatResponse` format (with `themes` and `topics` fields). `ThemeHeatRow.phase: str` remains required — themes always have phase per the defaults.

`GET /api/topics/heat` remains an alias of `/api/themes/heat`, unchanged.

### `get_graph_snapshot` rewiring

The current branching (themes through `list_theme_heat`, other kinds through `list_nodes` with `score=article_count`) collapses to a single loop where every kind goes through `list_node_heat` and gets `score=heat`.

Two intentional behavior changes:

1. **`score` is now `heat` for every kind.** Events switch from `score=float(article_count)` to `score=heat`. This is the fix.
2. **`?phase=<phase>` drops non-phase kinds.** Today, phase filters only affect themes while non-themes pass through unchanged. After the change, `?phase=emerging` returns only emerging themes and emerging events. Non-phase kinds are excluded because they can never satisfy a phase filter. If a caller wants emerging themes plus all persons, they should make separate requests.

### Cache keys

`RedisResponseCache` hashes the `params` dict for cache keys. The new endpoint passes `kind` in params, so each kind gets its own cache entry. Existing `/api/themes/heat` cache keys are unchanged.

### CLI: no new commands

The existing `kg-themes-now` / `-emerging` / `-fading` / `-history` commands stay unchanged. No `kg-events-now` or `kg-nodes-heat` commands are added. Rationale: the bug-fix scope doesn't need them, and CLI surface decisions for event heat deserve their own discussion once event heat data exists.

## Implementation Sequence

### PR 1: Generalize view, theme-only behavior preserved

- Drop `theme_heat_view`, create `node_heat_view` with the recursive CTE (benign no-op for non-events since their `parent_node_id` is NULL).
- Rename `refresh_theme_heat_view()` to `refresh_node_heat_view()`.
- Rename `ThemeHeatSnapshot` to `NodeHeatSnapshot`, add `kind` field, keep `ThemeHeatSnapshot` as alias.
- `list_theme_heat` stays on the repository as a backward-compat wrapper. Internally it calls the new `list_node_heat_rows(kind='theme')`, classifies each row with `classify_phase` using hardcoded defaults (matching today's SQL exactly), and filters/sorts as before. Callers are unchanged.
- Introduce `kg/heat_phase.py` with `classify_phase`, `HeatPhaseThresholds`, `DEFAULT_THEME_HEAT_THRESHOLDS`, and a `PhaseNotSupported` exception (raised when a caller requests phase filtering on a non-phase-eligible kind).
- Zero behavior change for any caller. Verified by existing tests.

### PR 2: Move phase thresholds into `KGSettings`

- Add `theme_heat_thresholds` and `event_heat_thresholds` fields to `KGSettings`.
- Add `HeatPhaseThresholds` parsing from `KG_*_HEAT_THRESHOLDS_JSON` env vars and `KG_*_HEAT_PHASE_ENABLED` kill switches.
- Wire `VisualizationQueries` to read thresholds from settings and pass them through to classification.
- Add threshold round-trip unit tests.

### PR 3: Event heat with hierarchy aggregation

- Depends on the event-hierarchy branch (currently uncommitted working-tree changes) being committed and merged first.
- Start querying event rows from the service and API layers (the rows were already present in the view since PR 1 but no caller read them).
- Add event-specific threshold defaults (initially matching theme defaults, flagged for calibration).
- Postgres integration tests for hierarchy correctness (`test_node_heat_view_postgres.py`).
- Refresh benchmark to verify the recursive CTE runs within 500ms on realistic data.

### PR 4: Heat for person / nation / org / place

- Expose these kinds through `list_node_heat_rows(kind=...)` (they're already in the view since PR 1).
- `classify_phase` returns `None` for these kinds (no thresholds configured).
- Parameterized unit tests for each kind.

### PR 5: Expose `/api/nodes/heat` + rewire `get_graph_snapshot`

- Add the `GET /api/nodes/heat` route with `NodesHeatResponse`.
- Convert `/api/themes/heat` to a thin alias that reshapes the response into `ThemesHeatResponse`.
- Rewire `get_graph_snapshot` so all kinds use `list_node_heat` and `score=heat`.
- Add the `test_graph_snapshot_mixed_kinds_ranking` regression test: the canonical proof that the ranking bug is fixed (themes and events interleave by heat, not grouped by kind).
- Clean up the `ThemeHeatSnapshot` alias.

## Testing Strategy

### Unit tests (run in `uv run pytest`, no infrastructure)

- **`tests/kg/test_heat_phase.py`** (new): `classify_phase` assertions for all 5 phases, edge cases (all-zero → `sustained`, `thresholds=None` → `None`), threshold tuning round-trip.
- **`tests/kg/test_kg_config.py`** (extends): `KGSettings.from_mapping` populates thresholds, JSON override parsing, phase-enabled kill switch.
- **`tests/kg/test_repository_schema.py`** (updates): Asserts `node_heat_view` exists, `WITH RECURSIVE` present, phase `CASE` gone, `kind` index exists.
- **`tests/kg/test_services.py`** (updates): Fake repository gains `list_node_heat_rows(kind=)`. Existing `themes_now`/`themes_emerging`/`themes_fading` tests pass unchanged.
- **`tests/viz_api/test_queries.py`** (extends): `list_node_heat` for each kind, phase filtering, `PhaseNotSupported` on non-phase kind + phase param.
- **`tests/viz_api/test_api.py`** (extends): `/api/nodes/heat` route shape, HTTP 400 on invalid kind+phase, legacy `/api/themes/heat` and `/api/topics/heat` shape preserved, `get_graph_snapshot` mixed-kinds ranking regression.

### Postgres integration tests (optional, behind `KG_PG_INTEGRATION=1`)

- **`tests/kg/test_node_heat_view_postgres.py`** (new): Requires a real Postgres instance. Fixture populates parent events, child events, themes, persons with known story assignments. Test cases:
  - Leaf event heat equals direct assignment.
  - Parent event heat rolls up descendants.
  - No double-count when a story is on parent and child.
  - Inactive descendants excluded from aggregation.
  - Non-event kinds have no rollup even if `parent_node_id` is set.
  - Cycles bounded by depth cap.

### Performance benchmark

`scripts/benchmark_node_heat_view.py` (not checked into tests). Seeds ~2000 nodes, ~10000 story units, 500 story-node assignments. Times 10 refreshes. Acceptance: median < 500ms on local dev. Run before merging PR 3; result recorded in PR description.

## Known Issues and Non-Goals

- **Sort key is always `heat_1d` regardless of `?window=`.** Carried forward from today. Separate fix.
- **No CLI commands for non-theme heat.** Follow-up when event heat data is stable.
- **No frontend changes.** Follow-up after the backend deploys and data is observable.
- **No rolled-up `article_count`.** Accepted inconsistency; `heat_Nd` carries the aggregated signal.
- **Event threshold calibration is deferred.** Defaults match theme thresholds. Calibrate from observed event heat distribution after PR 3 deploys.
