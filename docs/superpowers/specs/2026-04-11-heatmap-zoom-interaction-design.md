# Heatmap Zoom & Interaction — viz-web

**Date:** 2026-04-11
**Status:** Design approved, ready for implementation plan
**Scope:** `viz-web/src/components/LandscapeMap.tsx` and related hooks/children. No changes to other views, API contracts, or backend.

## Goal

Make the Landscape view heatmap interactive and zoomable:

- Pan and zoom via d3-zoom (wheel, trackpad pinch, click-drag on background, zoom buttons, keyboard)
- Drag individual bubbles temporarily, with a snap-back animation to their force-simulated position on release
- Shift-click to pin an inline preview popover without navigating away
- Keyboard accessibility throughout (tab focus per bubble, arrow-key pan, +/- zoom, 0 reset, auto-pan to keep focused bubble on screen)
- Canvas-based rendering for higher performance ceiling, backed by a transparent HTML button overlay so screen-reader access and keyboard focus are preserved per bubble

The existing click-to-navigate, hover-to-tooltip, and table↔map hover sync behaviors are preserved unchanged.

## Decisions locked in brainstorming

| Decision | Choice |
|---|---|
| Primary problem | All of the above: crowding, in-place exploration, spatial interaction |
| Zoom mechanism | d3-zoom on the outer container |
| Drag behavior | Drag-to-peek with animated snap-back on release |
| Controls | Zoom +/- buttons + reset + scale indicator + keyboard shortcuts |
| Click behavior | Click navigates (unchanged); shift-click opens inline preview |
| Lasso / box-select | Deferred — future feature |
| Rendering strategy | Canvas visuals + transparent HTML button overlay (accessible canvas pattern) |
| Drag animation duration | 180ms (design-system motion standard) |
| Focus pan behavior | Auto-pan to center focused bubble when off-screen |
| Library additions | None — use existing `d3` package only (already installed) |

## Architecture

### Layered rendering

Both canvas and hit layer live inside a single CSS-transformed `<div class="zoom-layer">`. d3-zoom writes one CSS `transform` string per interaction — no React re-render on pan/zoom.

```
<div className="relative" ref={containerRef}>       ← d3-zoom binds here, overlays live here
  <canvas ref={canvasRef} />                         ← full-size, untransformed
  <div className="zoom-layer" ref={zoomLayerRef}>    ← CSS transform: translate(tx,ty) scale(k)
    <div className="hit-layer">
      {nodes.map(node =>
        <button
          data-node-id={node.node_id}
          aria-label={`${node.display_name}, ${node.kind}, score ${node.score.toFixed(2)}`}
          tabIndex={0}
          onClick={...}
          onPointerDown={...}  // drag start
          onMouseEnter={...}   // hover tooltip
          onFocus={...}        // auto-pan if off-screen
          style={{ left: node.x - node.r, top: node.y - node.r, width: node.r * 2, height: node.r * 2 }}
        />
      )}
    </div>
  </div>
  <LandscapeControls />                              ← zoom +/-, reset, scale indicator, keyboard hint
  <NodeTooltip />                                    ← follows pointer in client coords
  <LandscapePreviewPopover />                        ← pinned on shift-click
</div>
```

Canvas is NOT inside the zoom-layer. Instead, the canvas's `drawScene` function applies `ctx.setTransform(k, 0, 0, k, tx, ty)` internally and redraws on every zoom change. This gives crisp rendering at any zoom level (no blurry CSS scaling of a raster) while keeping the hit layer in sync via a parallel DOM transform.

**Correction to initial sketch:** earlier the architecture mockup put the canvas inside the shared transform-group. The final design puts the canvas OUTSIDE (applying its transform via 2D context) for crisp text/line rendering, while the hit layer stays inside the CSS-transformed zoom-layer. Both are driven by the same `{tx, ty, k}` state.

### Component structure

```
viz-web/src/components/LandscapeMap/
├── index.ts                             # re-exports LandscapeMap
├── LandscapeMap.tsx                     # orchestrator (~200 lines)
├── LandscapeMap.test.tsx                # integration tests for the composed map
├── useLandscapeLayout.ts                # force-simulation hook (extracted from current)
├── useLandscapeZoom.ts                  # d3-zoom hook
├── useLandscapeZoom.test.ts
├── useLandscapeDrag.ts                  # pointer-drag state machine with snap-back
├── useLandscapeDrag.test.ts
├── LandscapeCanvas.tsx                  # canvas renderer (no unit test — integration)
├── LandscapeHitLayer.tsx                # button overlay (no unit test — integration)
├── LandscapeControls.tsx                # +/-, reset, scale, keyboard hint
├── LandscapeControls.test.tsx
├── LandscapePreviewPopover.tsx          # shift-click preview card
└── LandscapePreviewPopover.test.tsx

viz-web/src/components/
└── NodeTooltip.tsx                      # unchanged
```

The current single-file `src/components/LandscapeMap.tsx` is split into a subdirectory. `LandscapeView.tsx` imports `LandscapeMap` from `../components/LandscapeMap` — the import path changes from `../components/LandscapeMap` (single file) to `../components/LandscapeMap` (directory with `index.ts`) — which is identical. No upstream changes to `LandscapeView.tsx`.

### Interfaces between units

**`useLandscapeLayout`** — extracted from the current inline memo:
```ts
function useLandscapeLayout(nodes: GraphNodeRow[], canvasWidth: number): PositionedNode[]
```
Runs synchronous 180-tick d3 force simulation. No behavior change from today.

**`useLandscapeZoom`**:
```ts
function useLandscapeZoom(options: {
  containerRef: RefObject<HTMLDivElement>;
  onTransformChange: (transform: ZoomTransform) => void;
}): {
  scale: number;
  zoomIn: () => void;
  zoomOut: () => void;
  reset: () => void;
  panBy: (dx: number, dy: number) => void;
  panTo: (x: number, y: number) => void;  // for auto-pan on focus
}
```
Wraps d3-zoom. Binds to `containerRef.current` on mount. Filter rejects pointer events whose target is inside `.hit-layer button` (lets the buttons handle click/drag) and accepts wheel + pointerdown-on-background. `scaleExtent([0.5, 8])`. Scale state throttled via rAF for the indicator.

**`useLandscapeDrag`**:
```ts
type DragState =
  | { phase: "idle" }
  | { phase: "dragging"; nodeId: string; originX: number; originY: number; dx: number; dy: number }
  | { phase: "snapping-back"; nodeId: string; progress: number; fromDx: number; fromDy: number };

function useLandscapeDrag(options: {
  onDragStart: (nodeId: string) => void;
  onDragMove: (nodeId: string, dx: number, dy: number) => void;
  onDragEnd: (nodeId: string) => void;
}): {
  state: DragState;
  pointerDown: (nodeId: string, event: PointerEvent) => void;
}
```

State machine:
- `idle` + `pointerDown(button 0, no shift)` → `dragging`. `setPointerCapture(pointerId)` on the target. Records origin.
- `dragging` + `pointermove` → update `{dx, dy}`. Canvas redraws with the node at drag position.
- `dragging` + `pointerup` → transition to `snapping-back`. Start a `requestAnimationFrame` loop that eases `progress` from 0 to 1 over 180ms using `easeOutCubic`. Canvas reads `(1 - eased) * (dx, dy)` for the node's offset each frame.
- `snapping-back` completion → `idle`. Release pointer capture.

Click vs. drag distinction: if pointerdown and pointerup happen within 4px movement and 300ms, it's a click and no drag state is entered. The `onClick` handler on the button fires normally.

**`LandscapeCanvas`**:
```tsx
interface LandscapeCanvasProps {
  nodes: PositionedNode[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  dragState: DragState;            // so drawScene can render the dragged node at the drag position
  transform: ZoomTransform;
  width: number;
  height: number;
}
```
Renders an absolutely-positioned `<canvas>` with the given width/height and `{ width: devicePixelRatio * width }` backing store. `drawScene(ctx, props)` is called from a `useEffect` whose dependencies include all the above. `drawScene` does:
1. `ctx.save()` and `ctx.setTransform(k, 0, 0, k, tx, ty)` using the incoming transform
2. Draw relations (hovered-neighbor edges only)
3. Draw bubble fills + strokes for each node — using the dragged-node offset if applicable
4. Draw labels for nodes with `r * k > 24` (semantic label culling based on effective screen-space size)
5. `ctx.restore()`

**`LandscapeHitLayer`**:
```tsx
interface LandscapeHitLayerProps {
  nodes: PositionedNode[];
  hoveredNodeId: string | null;
  dragState: DragState;
  onHover: (nodeId: string | null) => void;
  onNodeClick: (node: PositionedNode, event: ReactMouseEvent) => void;
  onPointerDown: (nodeId: string, event: ReactPointerEvent) => void;
  onFocus: (node: PositionedNode) => void;
}
```
Renders one `<button>` per node. Buttons are absolutely positioned at `(node.x - node.r, node.y - node.r)` with size `2r × 2r` (untransformed coordinates — the parent zoom-layer applies the CSS transform). Transparent background, no border by default, visible focus ring on `focus-visible`.

The dragged node's button gets an additional `transform: translate(dx, dy)` so it follows the cursor during drag.

**`LandscapeControls`**:
```tsx
interface LandscapeControlsProps {
  scale: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}
```
Renders three stacked buttons (+ / − / ⌂) in the top-right corner (absolutely positioned over the canvas), a scale indicator (`× {scale.toFixed(2)}`) in the bottom-left, and a tiny mono legend (`+ − 0 ← → ↑ ↓`) in the bottom-right.

**`LandscapePreviewPopover`**:
```tsx
interface LandscapePreviewPopoverProps {
  node: GraphNodeRow;
  x: number;  // anchor point in client coords
  y: number;
  onClose: () => void;
  onNavigate: (node: GraphNodeRow) => void;
}
```
Ink card with rounded-sm corners, pointer-events auto, fixed position. Contents:
- Eyebrow `PINNED · {KIND uppercase}`
- Display name (Fraunces display-md)
- Subline: `{kind} · score {score.toFixed(2)} · {article_count} stories`
- Summary paragraph if present
- Footer row: `Open detail →` link + small `Dismiss (Esc)` ghost button

Closes on: Escape key, click outside, or when a different bubble is shift-clicked (controller state sets a new node).

### State ownership in `LandscapeMap.tsx`

```tsx
const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
const [previewNode, setPreviewNode] = useState<GraphNodeRow | null>(null);
const [previewAnchor, setPreviewAnchor] = useState<{ x: number; y: number } | null>(null);
const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; node: GraphNodeRow } | null>(null);
const containerRef = useRef<HTMLDivElement>(null);
const zoomLayerRef = useRef<HTMLDivElement>(null);
const canvasRef = useRef<HTMLCanvasElement>(null);

const layout = useLandscapeLayout(nodes, width);
const zoom = useLandscapeZoom({
  containerRef,
  onTransformChange: (t) => {
    // Update zoom-layer CSS transform
    if (zoomLayerRef.current) {
      zoomLayerRef.current.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.k})`;
    }
    // Trigger canvas redraw via ref (canvas reads the same transform on next rAF)
    requestCanvasRedraw();
  },
});
const drag = useLandscapeDrag({
  onDragStart: setDraggingNodeId,
  onDragMove: (nodeId, dx, dy) => { ... requestCanvasRedraw(); ... },
  onDragEnd: () => setDraggingNodeId(null),
});
```

The parent controls hover, preview, and tooltip state. Zoom and drag are encapsulated in their hooks.

## Interaction mechanics

### d3-zoom filter

```ts
zoom.filter((event) => {
  // Let button clicks / drags / hovers through
  const target = event.target as Element | null;
  if (target?.closest("[data-node-id]")) return false;
  // Let d3-zoom handle wheel + pointerdown on background
  if (event.type === "wheel") return true;
  if (event.type === "pointerdown" && event.button === 0) return true;
  return false;
});
```

### Scale + pan keyboard handlers

Attached to `containerRef` via `onKeyDown`:

```ts
switch (event.key) {
  case "+": case "=": event.preventDefault(); zoom.zoomIn(); break;
  case "-": case "_": event.preventDefault(); zoom.zoomOut(); break;
  case "0":           event.preventDefault(); zoom.reset(); break;
  case "ArrowLeft":   event.preventDefault(); zoom.panBy( 48,  0); break;
  case "ArrowRight":  event.preventDefault(); zoom.panBy(-48,  0); break;
  case "ArrowUp":     event.preventDefault(); zoom.panBy(  0, 48); break;
  case "ArrowDown":   event.preventDefault(); zoom.panBy(  0,-48); break;
  case "Escape":      setPreviewNode(null); break;
}
```

Tab navigation through buttons is native browser behavior — no custom handler needed. Enter/Space on a focused button is also native button semantics (fires the button's `onClick`). Shift+Enter on a focused button: caught by the button's own `onKeyDown` and treated the same as shift-click.

### Click / shift-click

```ts
function handleClick(node: PositionedNode, event: ReactMouseEvent) {
  if (event.shiftKey) {
    setPreviewNode(node);
    setPreviewAnchor({ x: event.clientX, y: event.clientY });
  } else {
    onNodeClick(node);  // parent's navigate callback
  }
}
```

### Auto-pan on focus

`LandscapeHitLayer` forwards `onFocus` to the parent. The parent checks whether the focused node's client-rect bounding box is fully inside the container's bounding box. If not, it calls `zoom.panTo(node.x, node.y)` which smoothly transitions the transform so the node is centered.

The focus handler uses the button's bounding client rect (post-transform) via `event.currentTarget.getBoundingClientRect()` and compares it to `containerRef.current.getBoundingClientRect()`. If out of bounds in any axis, pan.

## Canvas drawing function

Pseudocode for `drawScene(ctx, { nodes, relations, hoveredNodeId, dragState, transform, width, height })`:

```ts
const dpr = window.devicePixelRatio || 1;
ctx.save();
ctx.clearRect(0, 0, width * dpr, height * dpr);
ctx.scale(dpr, dpr);
ctx.translate(transform.x, transform.y);
ctx.scale(transform.k, transform.k);

// Relations (only when a node is hovered)
if (hoveredNodeId) {
  ctx.strokeStyle = "#1A1715";
  for (const rel of relations) {
    if (rel.source !== hoveredNodeId && rel.target !== hoveredNodeId) continue;
    const src = nodes.find(n => n.node_id === rel.source);
    const tgt = nodes.find(n => n.node_id === rel.target);
    if (!src || !tgt) continue;
    ctx.globalAlpha = Math.min(0.7, rel.score / 4);
    ctx.lineWidth = Math.max(1, rel.score);
    ctx.beginPath();
    ctx.moveTo(src.x, src.y);
    ctx.lineTo(tgt.x, tgt.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

// Bubbles
for (const node of nodes) {
  let { x, y, r } = node;
  // Dragged node offset
  if (dragState.phase === "dragging" && dragState.nodeId === node.node_id) {
    x += dragState.dx;
    y += dragState.dy;
  } else if (dragState.phase === "snapping-back" && dragState.nodeId === node.node_id) {
    const eased = easeOutCubic(dragState.progress);
    x += (1 - eased) * dragState.fromDx;
    y += (1 - eased) * dragState.fromDy;
  }
  const dimmed = hoveredNodeId !== null && hoveredNodeId !== node.node_id && !isRelated(node, hoveredNodeId, relations);
  ctx.globalAlpha = dimmed ? 0.16 : 0.9;
  ctx.fillStyle = fillFor(node);
  ctx.strokeStyle = KIND_STROKE[node.kind];
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  // Label — semantic culling based on effective screen size
  if (r * transform.k > 24) {
    ctx.globalAlpha = dimmed ? 0.18 : 1;
    ctx.fillStyle = "#1A1715";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "600 0.82rem Inter, sans-serif";
    const label = node.display_name.length > 18 ? node.display_name.slice(0, 18) + "…" : node.display_name;
    ctx.fillText(label, x, y - 4);
    ctx.font = "500 0.68rem Inter, sans-serif";
    ctx.globalAlpha = dimmed ? 0.14 : 0.75;
    ctx.fillText(node.kind, x, y + 10);
  }
}

ctx.restore();
```

Redraw is rAF-throttled: every call to `requestCanvasRedraw()` schedules a single animation frame; multiple calls in the same frame collapse to one redraw.

## Testing strategy

### Total test count: 75 (58 current + 20 new – 3 deleted)

Test layout:

| File | Tests | Purpose |
|---|---|---|
| `LandscapeMap.test.tsx` (rewrite) | 5 | Integration: full composed map rendering, click, shift-click, hover, legend |
| `useLandscapeZoom.test.ts` | 4 | Hook unit: initial scale, zoomIn, zoomOut, reset |
| `useLandscapeDrag.test.ts` | 4 | Hook unit: idle, pointerDown, pointerMove, snap-back timing |
| `LandscapeControls.test.tsx` | 4 | Controls: renders buttons, scale indicator, click handlers |
| `LandscapePreviewPopover.test.tsx` | 3 | Popover: renders content, navigate click, Escape key |

Net: 20 new tests − 3 deleted = +17 tests. Final: 75 total.

The hit layer and canvas components are not unit-tested directly. The hit layer's button-rendering behavior is exercised via `LandscapeMap.test.tsx` integration tests. The canvas is not unit-testable in jsdom (no real canvas rendering) and is visually verified by the manual smoke test in step 10 of the migration plan.

### Hook tests

`useLandscapeZoom.test.ts` — 4 tests using `renderHook`:
1. Initial scale is 1
2. `zoomIn()` scales by 1.4
3. `zoomOut()` scales by 1/1.4
4. `reset()` restores identity

`useLandscapeDrag.test.ts` — 4 tests using `renderHook` + fake timers:
1. Initial state is idle
2. `pointerDown` with button 0 transitions to dragging
3. `pointermove` updates dx/dy
4. `pointerup` transitions to snapping-back then idle after 180ms

### Overlay tests

`LandscapeControls.test.tsx` — 4 tests:
1. Renders +/-/reset buttons
2. Renders scale indicator with initial value
3. Clicking + calls `onZoomIn`
4. Clicking reset calls `onReset`

`LandscapePreviewPopover.test.tsx` — 3 tests:
1. Renders display name + kind + score
2. Clicking "Open detail →" calls navigate
3. Pressing Escape calls onClose

### Integration tests

`LandscapeMap.test.tsx` — rewritten, 5 tests replacing the current 3:
1. Renders one button per node
2. Each button has correct aria-label
3. Click without shift calls parent `onNodeClick`
4. Shift-click opens preview popover (assert by finding popover text in DOM)
5. Caption legend text still renders

### Deleted tests

The 3 tests in the current `LandscapeMap.test.tsx` that assert `querySelectorAll("circle")` and `dispatchEvent(new MouseEvent("mouseenter"))` are deleted. Canvas has no DOM circles.

### Not tested

- Canvas pixel output (jsdom doesn't support real canvas rendering; trust the draw function with integration tests of the surrounding DOM behavior)
- d3-zoom wheel handling (library's responsibility)
- Smooth pan transition curves (tested behaviorally: `focus → panTo called with correct node coords`)
- Performance at scale (manual smoke test only)

## Migration plan (ordered commits)

Each step is its own commit so regressions are bisectable.

1. **Move to subdirectory:** create `viz-web/src/components/LandscapeMap/`, move `LandscapeMap.tsx` → `LandscapeMap/LandscapeMap.tsx`, add `LandscapeMap/index.ts` re-export, move `LandscapeMap.test.tsx` → `LandscapeMap/LandscapeMap.test.tsx` and adjust its imports. Run tests to confirm nothing broke. Commit.
2. **Extract `useLandscapeLayout`:** pull the current `positioned` memo + force simulation into a hook. No behavior change. Commit.
3. **Build `useLandscapeZoom` hook + test.** Not yet used by the component. Commit.
4. **Build `useLandscapeDrag` hook + test.** Not yet used. Commit.
5. **Build `LandscapeCanvas` component.** Draws bubbles/relations/labels. Not yet integrated. No unit test (integration-tested via the parent). Commit.
6. **Build `LandscapeHitLayer` component.** No unit test — integration-tested via `LandscapeMap.test.tsx` at step 9. Commit.
7. **Build `LandscapeControls` component + test.** Commit.
8. **Build `LandscapePreviewPopover` component + test.** Commit.
9. **Rewrite `LandscapeMap.tsx` to use the new pieces.** Replace the SVG rendering with canvas + hit layer, wire the hooks, replace the test file with the new 5 integration tests. Delete the old test cases. Commit.
10. **Verification pass:** `npm run test` (expect 75 pass), `npx tsc -b`, `npm run build`. Manual: load dev API, verify zoom/pan/drag/shift-click/keyboard all work against a real snapshot. Commit only if any fix is needed, otherwise report clean.

## Out of scope

- Lasso or box-select
- Minimap / navigator
- Save view state to URL (bookmarkable zoom/pan)
- Continuous live force simulation (stays synchronous 180 ticks as today)
- Multi-touch gestures beyond what d3-zoom provides (pinch is in; rotation is out)
- Performance profiling / benchmarking
- Accessible table-view fallback (the LandscapeTable already fills this role)
- Changes to `LandscapeView`, `LandscapeTable`, `FilterBar`, `NodeTooltip`, or any view outside `LandscapeMap/`
- Changes to API contract or backend

## Success criteria

- All 75 tests pass (58 existing + 20 new – 3 removed)
- `npx tsc -b` clean
- `npm run build` green with no new warnings
- No regression in existing behavior: click still navigates, hover still tooltips, dim-on-hover still works, table ↔ map hover sync still works
- Manual smoke test on dev API confirms: smooth zoom/pan with wheel + trackpad pinch, click-drag pan on background, bubble drag + snap-back, shift-click preview popover, +/-/0 keyboard zoom, arrow-key pan, Tab navigates through bubbles with visible focus ring, focused off-screen bubble auto-pans into view
- `role="img"` + `aria-label="Heat map of nodes"` still present on the outermost map container
- No regression on forbidden patterns from the previous redesign (no `backdrop-filter`, no unexpected `rounded-full` on non-circular elements, no Google Fonts runtime imports)
- `src/components/LandscapeMap/` subdirectory exists with the 9 files listed above
- No changes outside `viz-web/src/components/LandscapeMap/` except the single import path in `viz-web/src/views/LandscapeView.tsx` (which may not even need to change if the re-export is wired correctly)
