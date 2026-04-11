# Frontend Redesign — viz-web

**Date:** 2026-04-10
**Status:** Design approved, updated 2026-04-10 to match new graph-node data model
**Scope:** `viz-web/` only. No changes to `src/telegram_scraper/`, the viz-api, or any API contract.

## Goal

Replace the current warm-cream glassmorphism look with a dense, editorial "newsroom analyst" interface. Full rework of the styling tech stack. Landscape and Node Detail views are rebuilt in code; Trends, Propagation, and Evolution stay as placeholder routes but get redesigned placeholder screens.

The redesign targets the current code shape: a graph-node snapshot API where nodes have a `kind` (`event`, `theme`, `person`, `nation`, `org`, `place`) and only `theme` nodes carry a phase. The design is not a topic-centric redesign — it is a node-centric redesign.

## Decisions locked in brainstorming

| Decision | Choice |
|---|---|
| Redesign scope | Full rework including tech stack |
| Audience / feel | Editorial newsroom tool (FT Alphaville / Rest of World) |
| Visual direction | A · Refined warm paper |
| Density | Dense analyst mode (metrics strip + filter rail + compact rows) |
| Styling system | Tailwind CSS v4 + hand-rolled primitives (no shadcn/Radix) |
| Dark mode | Light only |
| Deferred views | Redesign placeholders only; don't build Trends/Propagation/Evolution |
| Landscape layout | A · List-primary with companion node map |
| Top-level title | Keep "Telegram Knowledge Graph" (no rename) |
| Table virtualization | No virtualization; render all rows (≤200 nodes) |

## Design system

### Palette

All colors live in `src/styles/tokens.css` as CSS custom properties.

**Surface**
- Paper `#F7F1E3` — page background
- Card `#FDF9EC` — cards, chart backgrounds, inputs
- Surface-2 `#EFE6D0` — subtle separator panels
- Ink `#1A1715` — primary text, heavy rules

**Semantic phase (themes only)**
- Emerging `#C94F2B` (terracotta, also the single brand accent)
- Flash `#D97706`
- Sustained `#0D7C66`
- Fading `#2F6FB5`
- Steady `#5C4A39`

**Semantic kind (all node kinds)**
- Event `#B45309`
- Theme `#2F4858`
- Person `#115E59`
- Nation `#1D4ED8`
- Org `#7C2D12`
- Place `#4D7C0F`

Kind colors are used for ring strokes on the node map, kind chips/pills, and the kind filter. Phase colors are only used to fill theme nodes and to render theme-specific phase pills. The two scales are visually distinct because they're applied to different SVG attributes (stroke vs fill).

**Supporting**
- Muted `#8B5E3C` — eyebrow labels, secondary text, mono captions
- Neutral cream `#F0E6D2` — fill color for non-theme node bubbles (matches existing code behavior)

No other accents. Any time a component needs color, it uses Ink for text, Muted for secondary text, a phase color for theme-specific semantics, or a kind color for node-kind semantics. The current orange/teal/blue radial-gradient background is deleted.

### Typography

Fonts are self-hosted via `@fontsource/*` packages. The `@import url(fonts.googleapis.com…)` in the current `styles.css` is removed.

- **Fraunces** — display serif, weight 500, used for every `h1`/`h2`/`h3`
- **Inter** — UI sans, body text, controls, labels
- **JetBrains Mono** — all numeric data, timestamps, IDs, status strings

**Type scale**
- `display-xl` — `clamp(1.8rem, 4vw, 2.4rem)`, line-height 0.98, letter-spacing -0.03em (page titles)
- `display-lg` — 1.6rem, line-height 1.02, letter-spacing -0.02em (section titles)
- `display-md` — 1.2rem, line-height 1.05 (card titles)
- `body-md` — 0.88rem
- `body-sm` — 0.78rem
- `mono` — 0.82rem, JetBrains Mono
- `eyebrow` — 0.62rem, Inter 600, uppercase, letter-spacing 0.16em, color `muted`

### Shape & motion

- 4px Tailwind spacing scale (default).
- Max border-radius is 4px (`rounded`). **No pill buttons** anywhere. No `border-radius: 999px`.
- No glassmorphism. No `backdrop-filter: blur`.
- No drop shadows except on node-graph bubbles (keeps the subtle print-feel on the map).
- Two ink rule weights: `1px #1A1715` (section divider) and `1px rgba(26,23,21,0.16)` (row divider). Both exported as `--rule-ink` and `--rule-ink-thin`.
- Motion: opacity/transform transitions only, ≤180ms. Hover transforms are subtle (translateY(-1px) for buttons, background tint for table rows).

### Primitives (`src/ui/`)

Every primitive is presentational, takes no domain state, and has a matching Vitest test.

- `Button` — variants: `ink` (primary, ink bg + paper text), `ghost` (transparent + ruled border), `ghost-active` (ink fill for selected state)
- `Pill` — generic squared pill with a semantic variant prop
- `PhaseBadge` — thin wrapper over `Pill` that maps `PhaseKey` to the right variant (themes only)
- `KindChip` — squared chip for node kind, uses the kind color palette for a colored dot + ink text; supports an `active` toggle state
- `Eyebrow` — renders uppercase Muted label
- `Rule` — `<hr>` replacement with `bold` / `thin` / `dashed` variants
- `Card` — cream card with optional ruled header slot
- `MetricCell` — label + mono value + optional sub-line (accepts `up` / `down` / `neutral`)
- `MetricsStrip` — lays out N `MetricCell`s between ink rules with vertical dividers
- `SortableTable` — headless-ish table with column configs, sort state, row click handler, hover callback
- `WindowSelector` — button group for `1d / 3d / 5d / 7d / 14d / 31d` (moved from `components/`, restyled to match the new `WindowKey` union)

All primitives are exported from `src/ui/index.ts`.

> **Note:** The new `WindowKey` union in `lib/types.ts` is `"1d" | "3d" | "5d" | "7d" | "14d" | "31d"`. `WindowSelector` must render these exact values, not the old `24H / 7D / 30D / 90D` set shown in early mockups.

## Layout shell (`src/layout/`)

### `AppShell`

Replaces the inline `<header>` in the current `App.tsx`. Owns:
- `TopNav` (always rendered)
- `Breadcrumbs` slot (rendered on Node Detail only)
- Main content slot for view routes

### `TopNav`

Slim horizontal bar, ruled bottom edge (`1px #1A1715`).

- **Left:** brand stack — `"Telegram Knowledge Graph"` in Fraunces + `"Signal mapping for channel narratives"` eyebrow
- **Center:** route links — Landscape · Node Detail · Trends · Propagation · Evolution
  - Active route: Inter weight 600 with a 2px terracotta underline anchored below the nav row
  - Disabled routes (Trends/Propagation/Evolution): muted color, `aria-disabled`, not clickable
  - Node Detail tab is active only when the current pathname starts with `/node/`
- **Right:** live status chip — `● LIVE · 14:32 UTC`, mono, muted color

Replaces the current pill-button tab group entirely. Preserves the current `App.tsx` behavior of pointing the Node Detail tab at the current pathname when already on a node detail route, or at `/` otherwise.

### `Breadcrumbs`

Renders on Node Detail only: `Landscape › <kind> › <display_name>`. The `Landscape` crumb navigates to `/`; the `<kind>` crumb is a mono token (non-clickable in v1).

## Landscape view

### Composition

`LandscapeView.tsx` becomes a thin orchestrator holding:
- `windowKey` state (`WindowKey`, default `"7d"`)
- `kindFilter` state (`Set<NodeKind>`, default `{"event","theme"}` — matches current code)
- `phaseFilter` state (`Set<string>`, default all phases — applies to themes only)
- `hoveredNodeId` state
- `sortBy` / `sortDir` state for the table
- async resource for the graph snapshot (`fetchSnapshot`)

It renders (in order, inside the main slot):

1. **Page header band** — eyebrow `LIVE NODE LANDSCAPE`, `display-xl` headline `Event and theme pressure map` (kept from current code), `WindowSelector` right-aligned
2. **`MetricsStrip`** with five cells (all computed client-side from `snapshotState.data?.nodes`):
   - Nodes (count of all nodes in the snapshot)
   - Themes (count of nodes with `kind === "theme"`)
   - Events (count of nodes with `kind === "event"`)
   - Emerging themes (count of theme nodes with `phase === "emerging"` or `"flash_event"`)
   - Relations (count of `snapshotState.data?.relations`)
   Sub-lines under each number are static descriptive captions like `in 7d window`, `themes only`, `all kinds`. **No deltas are computed in v1** — the current snapshot API does not expose historical comparisons. Do not fabricate deltas.
3. **`FilterBar`** — two horizontal groups in one ruled strip:
   - `Kinds` (primary) — six `KindChip`s, one per node kind, with colored dots and active/ink-fill toggle state. Clicking a chip toggles it in `kindFilter`. If all chips get deselected, reset to the default `{"event","theme"}` (matches current code behavior).
   - `Phases` (secondary, themes only) — five phase pills acting as toggles. Visually dimmed to 40% opacity when `"theme"` is not in `kindFilter`, but still clickable. A small muted caption beside the label explains `themes only`.
4. **`LandscapeTable` + `LandscapeMap` split**, side by side in a grid-cols-[1fr_1.15fr] container with an internal ink rule:
   - **`LandscapeTable`** — sortable table columns:
     | Col | Content |
     |---|---|
     | dot | kind color dot (or phase color dot if theme) |
     | Node | `display_name` title + subline `<kind>` · `<phase if theme>` · `<summary truncated if present>` |
     | Score | `score`, mono, right-aligned, 2 decimal places |
     | Stories | `article_count`, mono, right-aligned |
     | Heat | `heat` if present, mono; `—` otherwise |
     Default sort: `score` desc. Clickable column headers toggle sort direction. Row hover tints the row and sets `hoveredNodeId`. Row click navigates to `/node/:kind/:slug`.
     Rows are filtered by the same rule the current code uses: keep the row if its kind is in `kindFilter`, and (if the row is a theme) if its phase is in `phaseFilter` or phase is null.
   - **`LandscapeMap`** — extracted d3 force-simulation:
     - Reuses the current `d3.forceSimulation` + `forceX`/`forceY`/`forceCollide` logic and the existing radius scale `d3.scaleSqrt().domain([0, max(score)]).range([16, 78])`
     - Re-skinned: ring stroke uses `kindStroke[node.kind]` (same mapping as current code, but the stroke palette becomes the kind palette from the design system tokens), fill uses `phaseColors[node.phase]` for themes or neutral cream `#F0E6D2` for other kinds (matches current behavior)
     - Labels: `display_name` on line 1 (truncated to 18 chars + ellipsis), `kind` on line 2 (not `channel_title` — that field no longer exists on nodes)
     - Caption row above the canvas: eyebrow `HEAT MAP` + mono legend `ring = kind · fill = phase (themes) · size = score`
     - Bubble hover sets `hoveredNodeId`; hover-linked relations are drawn as ink lines at reduced opacity (matches current behavior). Non-hovered + non-related bubbles dim to 0.16 opacity.
     - Bubble click navigates to `/node/:kind/:slug`
     - `TopicTooltip` (re-themed, rename to `NodeTooltip` in the refactor — see architecture section) renders on hover
5. **Footer status line** — mono, muted, under the split: `<N> nodes · <M> shown · sort by <col> desc` and `window: <windowKey>`

### Behavior

- `hoveredNodeId` is shared state; hovering a table row highlights the matching bubble (opacity boost + halo ring), and hovering a bubble highlights the matching table row (background tint).
- Filters compose: phase filter narrows theme rows only; kind filter narrows both tables and bubbles.
- Empty state: when `filteredNodes.length === 0`, render `EmptyState` with suggestions ("Widen the window", "Enable more kinds", "Enable all phases for themes") and a "Reset filters" ghost button.
- Loading state: skeleton version of the metrics strip + table rows; slide-bar animation on top.
- All SVG ids (`bubbleGlow` filter) are kept for d3 continuity.

### What changes relative to the current code

- Inline styled `<header>` in `App.tsx` → `AppShell` + `TopNav`
- `ChannelLegend` component → deleted; channels are no longer a filter dimension
- `TimeWindowSelector` → `WindowSelector` in `ui/`, restyled, supports the six window keys
- `LandscapeView` splits into orchestrator + `LandscapeTable` + `LandscapeMap`
- The whole `view-toolbar` + `filters-row` + `graph-card` structure is replaced
- The `kindFilter` moves from a plain text-button row to a proper `KindChip` group in `FilterBar`

## Node Detail view

### Composition

`NodeDetailView.tsx` (renamed from `TopicDetailView.tsx`) renders, top to bottom:

1. **`Breadcrumbs`** — `Landscape › <kind> › <display_name>`
2. **`NodeHeaderBand`** — two-column grid:
   - **Left:** eyebrow `NODE DETAIL · <KIND uppercase>`, `display-xl` `display_name`, one-line mono sub-row with `slug`, `article_count` stories, and (for themes) a `PhaseBadge`
   - **Right:** optional Theme `PhaseBadge` stacked in the corner for theme nodes only
   - A `summary` paragraph sits below the display name using `body-md` at `max-w-prose`, or nothing if `summary` is null. Keywords are not rendered — the new data model has no keywords field.
3. **`MetricsStrip`** with four to five cells depending on kind:
   - Always: **Kind** (`kind`, sub-line: `node slug`), **Stories** (`article_count`)
   - Always: sum of related node counts across `events + people + nations + orgs + places + themes`, labeled **Connected**
   - Themes only: **Phase** (phase label, sub-line empty or showing phase color dot)
   - Themes only: **Drift** (latest centroid drift from `historyState.data.history[last].centroid_drift` if present, else `—`)
4. **Body grid** — `grid-cols-[2fr_1fr]` with an ink rule between columns:
   - **Left column** (stacked):
     - **`ThemeHistory`** — rendered only when `kind === "theme"` and `chartData.length > 0`. Re-themed recharts `ComposedChart` from the current `TopicDetailView`:
       - `Bar` `article_count` in Sustained green with 2px radius
       - `Line` `centroid_drift` in Emerging terracotta, stroke-width 2, no dots
       - Axes: tick line off, axis line thin `rgba(26,23,21,0.16)`, ticks in mono muted
       - Tooltip: cream background, ink text, ink border
       - No gridlines except a few 5% horizontal references
       - **No `ReferenceLine` for events** — the new data model does not expose lifecycle events, so merge/split/relabel reference lines are not rendered. If the API later adds events, they plug back in here.
       When `kind !== "theme"` the component is not rendered at all. No "no history" placeholder is shown for non-themes — the chart simply doesn't exist for those kinds.
     - **`NodeStoriesList`** — dense three-column grid rows:
       | Col | Content |
       |---|---|
       | Timestamp | mono, two lines (date / time) of `story.timestamp_start` |
       | Title | `preview_text` or `"(media-only story)"` fallback, `body-md` weight 500, click to expand |
       | Meta | mono, right-aligned: `<channel_title>` · `<confidence rounded to 2 decimals>` |
       Replaces the current story-card-with-summary-button pattern.
       **No pagination.** The component renders every story in `detail.stories`. If the list exceeds a visual budget, overflow is handled by natural scroll (the list lives in the normal page flow).
       Expanded row shows `combined_text` + `media_list` beneath the row, within the same ruled container. Expansion state is an `Set<string>` of story IDs held by `NodeDetailView`, same as today.
   - **Right column** (stacked rails):
     - **`ConnectedNodesRail`** — replaces the old `related-sidebar`. Renders six sections, one per entity kind, in this order: `Events`, `People`, `Nations`, `Organizations`, `Places`, `Themes`. Each section:
       - Has an eyebrow header with count: `EVENTS · 3`
       - Shows up to 6 rows (same as current code)
       - If the section's array is empty, renders a compact muted `No related <label>.` line under the header
       - Each row: two-column grid — left: `display_name` + mono sub-line `<kind> · <shared_story_count> shared stories`; right: mono `score.toFixed(2)` and a thin `score-bar` (Sustained green fill at `(score / maxScoreInSection) * 100%` width)
       - Clickable, navigates to `/node/:kind/:slug`

### Behavior

- Story expand/collapse is same as current code (Set<string> of expanded IDs).
- `detailState` (from `fetchNodeDetail`) and `historyState` (from `fetchThemeHistory`, theme-only) are unchanged from current code.
- If `kind` or `slug` params are missing, render `EmptyState` with "Node not found".
- If `detailState.error || !detailState.data`, render `EmptyState` with "Node detail unavailable".
- `historyState` is fetched unconditionally by the hook but only used when `kind === "theme"` (matches current code where the promise resolves to `null` for non-themes).

### What changes relative to the current code

- `detail-header-card` → `NodeHeaderBand` + `MetricsStrip`
- Rendered `summary` gets its own line instead of being in `<p className="muted">` below meta row
- Chart card becomes `ThemeHistory`, re-themed
- Current `stories-card` with "Related Sections" header (rendering six `NodeSection`s inline) → `ConnectedNodesRail` in the right rail
- Stories card → `NodeStoriesList` (ruled rows instead of article elements)
- Current two stacked cards layout → single two-column body grid
- Keyword row: deleted (no keywords in data)
- Event log: not implemented (no event data in current model)
- Pagination: deleted (no pagination in current model)

## Placeholder, loading, empty states

### `ComingSoonPanel` (rewritten)

Used for `/trends`, `/propagation`, `/evolution`. Props: `eyebrow`, `title`, `description`, `phase` (`"Phase 2"` / `"Phase 3"`).

Renders:
- Eyebrow + `display-lg` title
- Ink rule
- Short description paragraph (keeps the existing copy from current `App.tsx` for each view)
- A dashed-border `pg-preview` box gesturing at the future visualization with muted rows (not animated, just static hinting)
- Ink `phase` badge at bottom-left

No external link unless a spec file exists for that view.

### `LoadingState` (rewritten)

Replaces current spinner shimmer. Props: `view` (`"landscape"` | `"node-detail"`).

Renders:
- Eyebrow `LOADING`
- `display-lg` headline matching the destination view: `"Fetching landscape"` for `view="landscape"`, `"Fetching node"` for `view="node-detail"`
- Animated slide bar (terracotta on a muted background, ~1.2s loop)
- Deterministic skeleton rows matching the shape of the destination view (table rows for landscape, header + chart + stories placeholders for node detail)

Skeletons reuse the same layout primitives as the real views so loading feels like a shape-first preview rather than a spinner.

### `EmptyState` (rewritten)

Props: `title`, `message`, `suggestions?` (array of `{label, onClick}`), `onReset?`.

Renders:
- Eyebrow `NOTHING FOUND`
- `display-lg` title
- Ink rule
- Message paragraph
- A cream card containing a `/ suggestions` header + bullet list of suggestions + a ghost "Reset filters" button when `onReset` is provided

Used by Landscape (empty filter result) and Node Detail (error / not found).

## Architecture

### File structure

```
viz-web/
├── index.html
├── package.json                 # adds tailwindcss v4, @fontsource/*, clsx
├── postcss.config.js            # new
├── tailwind.config.ts           # new: content globs only
├── src/
│   ├── main.tsx                 # imports fonts + globals.css
│   ├── App.tsx                  # renders <AppShell> + routes only
│   ├── styles/
│   │   ├── globals.css
│   │   └── tokens.css
│   ├── ui/
│   │   ├── Button.tsx
│   │   ├── Pill.tsx
│   │   ├── PhaseBadge.tsx       # moved from components/
│   │   ├── KindChip.tsx         # new
│   │   ├── Eyebrow.tsx
│   │   ├── Rule.tsx
│   │   ├── Card.tsx
│   │   ├── MetricCell.tsx
│   │   ├── MetricsStrip.tsx
│   │   ├── SortableTable.tsx
│   │   ├── WindowSelector.tsx   # moved from components/
│   │   └── index.ts
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── TopNav.tsx
│   │   └── Breadcrumbs.tsx
│   ├── components/
│   │   ├── LandscapeMap.tsx     # extracted from LandscapeView
│   │   ├── LandscapeTable.tsx   # new
│   │   ├── FilterBar.tsx        # new (kind + phase filters)
│   │   ├── NodeHeaderBand.tsx   # new
│   │   ├── ThemeHistory.tsx     # new (themes only, re-themed chart)
│   │   ├── NodeStoriesList.tsx  # new
│   │   ├── ConnectedNodesRail.tsx # new (replaces old related-topics sidebar)
│   │   ├── ComingSoonPanel.tsx  # rewritten
│   │   ├── EmptyState.tsx       # rewritten
│   │   ├── LoadingState.tsx     # rewritten
│   │   └── NodeTooltip.tsx      # renamed from TopicTooltip.tsx, re-themed
│   ├── views/
│   │   ├── LandscapeView.tsx    # thin orchestrator
│   │   └── NodeDetailView.tsx   # renamed from TopicDetailView.tsx, thin orchestrator
│   ├── hooks/                   # unchanged
│   ├── lib/
│   │   ├── api.ts               # unchanged
│   │   ├── types.ts             # unchanged
│   │   └── channelColors.ts     # unchanged, retained (may be used by future views)
│   └── test/                    # unchanged
└── ...
```

### Files deleted

- `src/styles.css` (replaced by `src/styles/globals.css` + `src/styles/tokens.css`)
- `src/components/ChannelLegend.tsx` (channels no longer a filter dimension, already unused by current `LandscapeView`)

### Files renamed

- `src/components/TopicTooltip.tsx` → `src/components/NodeTooltip.tsx`
- `src/views/TopicDetailView.tsx` → `src/views/NodeDetailView.tsx`
- `src/views/TopicDetailView.test.tsx` → `src/views/NodeDetailView.test.tsx`

### Files moved

- `src/components/PhaseBadge.tsx` → `src/ui/PhaseBadge.tsx`
- `src/components/TimeWindowSelector.tsx` → `src/ui/WindowSelector.tsx`

### Import updates

- `App.tsx` — imports `NodeDetailView` instead of `TopicDetailView`; route path stays `/node/:kind/:slug` (already correct in current code)
- `LandscapeView.tsx` — imports `NodeTooltip` instead of `TopicTooltip`
- Any test referencing `TopicDetailView` must be updated to `NodeDetailView`

### Tokens

All colors, type sizes, spacing, and radii live in `src/styles/tokens.css` as CSS custom properties. Tailwind v4's `@theme` block consumes them. A future dark variant would be a `[data-theme="dark"]` block overriding the same custom properties; no component code changes needed.

### Tailwind configuration

- Tailwind CSS v4 via `@tailwindcss/postcss`
- No `theme.extend` — all tokens come from CSS custom properties via `@theme`
- Content globs: `src/**/*.{ts,tsx,html}`

### Font strategy

Self-hosted via `@fontsource/fraunces`, `@fontsource/inter`, `@fontsource/jetbrains-mono`. Import in `main.tsx`:

```ts
import "@fontsource/fraunces/500.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
```

Remove the `@import url("https://fonts.googleapis.com/...")` line from the current `styles.css`.

### `channelColors.ts`

Kept as-is. It is no longer used by `LandscapeView` (channels have been removed from the snapshot render), but the file may be useful for a future channel-filter view. Do not delete and do not rewrite — it's out of scope for this redesign.

### Kind color mapping

The kind color mapping lives in `src/styles/tokens.css` as CSS custom properties and is also exported as a typed object for use inside d3:

```ts
// src/ui/kindColors.ts
import type { NodeKind } from "../lib/types";

export const KIND_STROKE: Record<NodeKind, string> = {
  event: "#B45309",
  theme: "#2F4858",
  person: "#115E59",
  nation: "#1D4ED8",
  org: "#7C2D12",
  place: "#4D7C0F",
};
```

This matches the `kindStroke` object currently hard-coded inside `LandscapeView.tsx`, with the same hex values. The refactor extracts this map so both `LandscapeMap` and `KindChip` can import it.

## Testing strategy

Vitest + React Testing Library + jsdom (unchanged from today).

### Tests that stay (with updates)

- `routes/App.test.tsx` — smoke test, keep "Trends/Propagation/Evolution are disabled" assertions; update selectors for the new `TopNav` markup (the `getByRole("button", ...)` assertions for disabled tabs will need to adapt if `TopNav` renders disabled tabs as `aria-disabled` anchors rather than buttons; keep the assertion intent, change the query)
- `views/NodeDetailView.test.tsx` (renamed) — keep the behavioral assertion that clicking a story row expands it; update selectors for the new ruled-row markup

### New tests

- `ui/SortableTable.test.tsx` — renders rows, sort toggle changes order, row click fires callback
- `ui/PhaseBadge.test.tsx` — renders each phase variant with correct text and class
- `ui/KindChip.test.tsx` — renders each kind with its dot color, toggle calls `onClick`
- `components/LandscapeTable.test.tsx` — renders filtered rows, sort works, hover callback fires
- `components/FilterBar.test.tsx` — kind chip click fires `onKindToggle`; phase pill click fires `onPhaseToggle`; phase pills are visually dimmed when `theme` is not in the kind set
- `components/LandscapeMap.test.tsx` — smoke test: renders svg with N bubbles, mouseenter fires onHover
- `components/ConnectedNodesRail.test.tsx` — renders six sections, empty sections show muted copy, row click navigates
- `layout/TopNav.test.tsx` — active route gets terracotta underline, disabled routes are not interactive

No snapshot tests. No pixel matching. No Playwright. Verification is behavioral + accessibility (roles, aria on toggle buttons, disabled states).

## Migration plan (ordered steps)

1. **Install dependencies**: `tailwindcss@next`, `@tailwindcss/postcss`, `postcss`, `@fontsource/fraunces`, `@fontsource/inter`, `@fontsource/jetbrains-mono`, `clsx`.
2. **Bootstrap Tailwind + tokens**: create `postcss.config.js`, `tailwind.config.ts`, `src/styles/tokens.css`, `src/styles/globals.css`. Import fonts + `globals.css` in `main.tsx`. Do not delete `styles.css` yet.
3. **Build `src/ui/` primitives** with tests for each. Components in this layer must not import from `lib/api.ts` or `lib/types.ts` (except `PhaseBadge` / `KindChip` which take enum values from `types.ts`).
4. **Build `src/layout/`** — `AppShell`, `TopNav`, `Breadcrumbs`. Swap `App.tsx` to use them. Keep the existing route table (`/`, `/node/:kind/:slug`, `/trends`, `/propagation`, `/evolution`).
5. **Build Landscape children**: `LandscapeTable`, `LandscapeMap`, `FilterBar`, `MetricsStrip`. Rebuild `LandscapeView` as orchestrator. Verify against the dev API.
6. **Rename + build Node Detail children**: rename `TopicDetailView` → `NodeDetailView`, rename `TopicTooltip` → `NodeTooltip`. Build `NodeHeaderBand`, `ThemeHistory`, `NodeStoriesList`, `ConnectedNodesRail`. Rebuild `NodeDetailView` as orchestrator. Verify against the dev API with both a theme node and a non-theme node.
7. **Rewrite `ComingSoonPanel`, `EmptyState`, `LoadingState`**. Update all call sites.
8. **Delete `src/styles.css`. Delete `src/components/ChannelLegend.tsx`.** Update imports.
9. **Run verification**: `npm run build`, `npm run test`, `npx tsc -b`. Manually load both views against the running viz-api and confirm: metrics strip populates for landscape, kind + phase filters both work, table ↔ map hover sync works bidirectionally, node click navigates to `/node/:kind/:slug`, node detail renders `NodeHeaderBand` + `MetricsStrip` + story list + `ConnectedNodesRail`, theme history chart renders for theme nodes only.
10. **Update `README.md`** Visualization Layer section only if behavior or routes changed (they shouldn't — this is a pure UI rework; route structure is preserved).

## Explicitly out of scope

- Building Trends, Propagation, or Evolution views
- Dark mode or theme toggle
- shadcn/ui, Radix, or any other component library
- Playwright, Storybook, or visual regression testing
- Backend / API changes (`src/telegram_scraper/`, `viz_api/`)
- Brand rename (keeping "Telegram Knowledge Graph")
- Virtualization for the node table
- Replacing recharts or d3
- Removing or rewriting the existing `useAsyncResource` / `useElementSize` hooks
- Re-introducing channel filters (channels are no longer part of the snapshot render)
- Re-introducing keywords, pagination, lifecycle event logs, or first-seen/last-updated timestamps (none of these exist in the current data model)
- Rewriting or touching `channelColors.ts`

## Success criteria

- Both Landscape and Node Detail render correctly against the live viz-api with no runtime errors.
- `npm run test`, `npm run build`, and `npx tsc -b` all pass clean.
- No import references to the deleted `styles.css` or `ChannelLegend` remain.
- Table ↔ map hover sync works bidirectionally on Landscape.
- Filtering by kind and phase composes correctly and empties to the EmptyState when nothing matches.
- Kind filter defaults to `{event, theme}` and the phase filter is visually dimmed (but clickable) when `theme` is not selected.
- Node Detail story expand/collapse behaves as it does today.
- Theme history chart only renders for `kind === "theme"` nodes.
- No pill-rounded (`border-radius: 999px`) buttons exist anywhere in the new code.
- No `backdrop-filter: blur` anywhere in the new code.
- Fonts load from `@fontsource/*`, not Google Fonts over the network.
- No references to "topic" as a domain term in new code — all user-facing strings, component names, and test names use "node" (except incidental references where the legacy name is still on disk awaiting rename).
