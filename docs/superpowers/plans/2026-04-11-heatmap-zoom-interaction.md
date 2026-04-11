# Heatmap Zoom & Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Landscape heatmap pan/zoomable, drag-to-peek with snap-back, shift-click preview popover, keyboard accessible, backed by canvas rendering with an HTML button overlay for per-bubble accessibility.

**Architecture:** Split `src/components/LandscapeMap.tsx` into a subdirectory with a thin orchestrator + three hooks (`useLandscapeLayout`, `useLandscapeZoom`, `useLandscapeDrag`) + four presentational children (`LandscapeCanvas`, `LandscapeHitLayer`, `LandscapeControls`, `LandscapePreviewPopover`). Canvas draws bubbles via `ctx.setTransform` for crisp rendering at any zoom. A transparent HTML button overlay sits inside a CSS-transformed zoom-layer, synchronized with the canvas via the same `{tx, ty, k}` state from d3-zoom.

**Tech Stack:** React 19, TypeScript, D3 v7 (d3-zoom, d3-force, d3-ease), Vitest, React Testing Library, Tailwind v4. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-11-heatmap-zoom-interaction-design.md`

---

## Prerequisites

Before starting any task, verify the baseline is green:

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web
npm run test
npx tsc -b
npm run build
```

All three must pass. The viz-web redesign is already merged to `main`, so the starting test count is **58 passing**.

**Working directory for npm commands:** `/Users/lfpmb/Documents/telegram-twitter-scraper/viz-web`
**Working directory for git commands:** `/Users/lfpmb/Documents/telegram-twitter-scraper` (repo root)
**Target branch:** `feature/heatmap-zoom` (create with `git checkout -b feature/heatmap-zoom` — the repo has lots of pre-existing uncommitted work on main, so use a dedicated branch to isolate these commits)

**Commit discipline:** only `git add` the specific files listed per task. Never `git add -A` or `git add .` — many pre-existing uncommitted files exist in the repo.

---

## File structure

Files created / modified:

```
viz-web/src/components/
├── LandscapeMap.tsx                          # DELETED in Task 1 (becomes directory)
├── LandscapeMap.test.tsx                     # MOVED in Task 1 → LandscapeMap/LandscapeMap.test.tsx
└── LandscapeMap/                             # NEW directory
    ├── index.ts                              # NEW (barrel re-export)
    ├── LandscapeMap.tsx                      # MOVED from viz-web/src/components/LandscapeMap.tsx (Task 1), heavily rewritten in Task 9
    ├── LandscapeMap.test.tsx                 # MOVED from viz-web/src/components/LandscapeMap.test.tsx (Task 1), rewritten in Task 9
    ├── useLandscapeLayout.ts                 # NEW (Task 2)
    ├── useLandscapeZoom.ts                   # NEW (Task 3)
    ├── useLandscapeZoom.test.ts              # NEW (Task 3)
    ├── useLandscapeDrag.ts                   # NEW (Task 4)
    ├── useLandscapeDrag.test.ts              # NEW (Task 4)
    ├── LandscapeCanvas.tsx                   # NEW (Task 5)
    ├── LandscapeHitLayer.tsx                 # NEW (Task 6)
    ├── LandscapeControls.tsx                 # NEW (Task 7)
    ├── LandscapeControls.test.tsx            # NEW (Task 7)
    ├── LandscapePreviewPopover.tsx           # NEW (Task 8)
    └── LandscapePreviewPopover.test.tsx      # NEW (Task 8)

viz-web/src/views/
└── LandscapeView.tsx                         # unchanged (import path resolves to LandscapeMap/index.ts via directory resolution)

viz-web/src/components/NodeTooltip.tsx        # unchanged
```

---

## Task 1: Move LandscapeMap to a subdirectory (no behavior change)

**Files:**
- Move: `viz-web/src/components/LandscapeMap.tsx` → `viz-web/src/components/LandscapeMap/LandscapeMap.tsx`
- Move: `viz-web/src/components/LandscapeMap.test.tsx` → `viz-web/src/components/LandscapeMap/LandscapeMap.test.tsx`
- Create: `viz-web/src/components/LandscapeMap/index.ts`

**Rationale:** Pure file relocation. After this commit the import `../components/LandscapeMap` still resolves because Node resolves `LandscapeMap` to `LandscapeMap/index.ts`. No code changes inside the files except test imports (relative paths may change).

- [ ] **Step 1: Create the subdirectory and move files**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
mkdir viz-web/src/components/LandscapeMap
git mv viz-web/src/components/LandscapeMap.tsx viz-web/src/components/LandscapeMap/LandscapeMap.tsx
git mv viz-web/src/components/LandscapeMap.test.tsx viz-web/src/components/LandscapeMap/LandscapeMap.test.tsx
```

Note: these files may be untracked in git. If `git mv` errors with "not under version control", use plain `mv` instead and `git add` the destinations.

- [ ] **Step 2: Update relative imports inside the moved files**

Edit `viz-web/src/components/LandscapeMap/LandscapeMap.tsx` — change all imports from `"../lib/..."`, `"../hooks/..."`, `"../ui"`, `"./NodeTooltip"` to account for the new depth:

Before:
```tsx
import type { GraphNodeRow, SnapshotRelation } from "../lib/types";
import { KIND_STROKE } from "../ui";
import { useElementSize } from "../hooks/useElementSize";
import { NodeTooltip } from "./NodeTooltip";
```

After:
```tsx
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";
import { KIND_STROKE } from "../../ui";
import { useElementSize } from "../../hooks/useElementSize";
import { NodeTooltip } from "../NodeTooltip";
```

Edit `viz-web/src/components/LandscapeMap/LandscapeMap.test.tsx` similarly. Find imports like `"./LandscapeMap"` — keep as-is (same directory now). Find `"../lib/types"` → `"../../lib/types"`.

- [ ] **Step 3: Create the barrel `index.ts`**

Create `viz-web/src/components/LandscapeMap/index.ts`:

```ts
export { LandscapeMap } from "./LandscapeMap";
```

- [ ] **Step 4: Run tests + typecheck to confirm nothing broke**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npm run test 2>&1 | tail -15
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx tsc -b 2>&1 | tail -10
```

Expected: 58 tests pass (same as baseline). Typecheck clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/
git commit -m "refactor(viz-web): move LandscapeMap into subdirectory"
```

---

## Task 2: Extract `useLandscapeLayout` hook

**Files:**
- Create: `viz-web/src/components/LandscapeMap/useLandscapeLayout.ts`
- Modify: `viz-web/src/components/LandscapeMap/LandscapeMap.tsx`

**Rationale:** Extract the existing force-simulation memo into a reusable hook. No behavior change; just file organization.

- [ ] **Step 1: Create `useLandscapeLayout.ts`**

Create `viz-web/src/components/LandscapeMap/useLandscapeLayout.ts`:

```ts
import * as d3 from "d3";
import { useMemo } from "react";
import type { GraphNodeRow } from "../../lib/types";

export type PositionedNode = GraphNodeRow & { x: number; y: number; r: number };

export function useLandscapeLayout(nodes: GraphNodeRow[], width: number): PositionedNode[] {
  return useMemo<PositionedNode[]>(() => {
    if (nodes.length === 0) {
      return [];
    }
    const canvasWidth = Math.max(width, 720);
    const radius = d3
      .scaleSqrt<number, number>()
      .domain([0, d3.max(nodes, (n) => n.score) ?? 1])
      .range([16, 78]);

    const initial: PositionedNode[] = nodes.map((node, index) => ({
      ...node,
      x: canvasWidth / 2 + ((index % 6) - 3) * 20,
      y: 260 + (Math.floor(index / 6) - 3) * 20,
      r: radius(node.score),
    }));

    const simulation = d3
      .forceSimulation(initial)
      .force("x", d3.forceX<PositionedNode>(canvasWidth / 2).strength(0.06))
      .force("y", d3.forceY<PositionedNode>(260).strength(0.08))
      .force("charge", d3.forceManyBody<PositionedNode>().strength(-22))
      .force("collision", d3.forceCollide<PositionedNode>((n) => n.r + 6))
      .stop();

    for (let i = 0; i < 180; i += 1) {
      simulation.tick();
    }
    return initial;
  }, [nodes, width]);
}
```

- [ ] **Step 2: Update `LandscapeMap.tsx` to use the hook**

In `viz-web/src/components/LandscapeMap/LandscapeMap.tsx`:

1. Add import at top: `import { useLandscapeLayout, type PositionedNode } from "./useLandscapeLayout";`
2. Delete the local `type PositionedNode = ...` declaration
3. Delete the inline `const positioned = useMemo<PositionedNode[]>(...)` block
4. Replace with: `const positioned = useLandscapeLayout(nodes, width);`
5. Remove the `import * as d3 from "d3";` line if no other d3 usage remains in the file (check — d3.scaleSqrt / d3.forceSimulation / d3.forceX / d3.forceY / d3.forceManyBody / d3.forceCollide should all be gone from this file). Keep the import if other d3 calls remain.
6. Remove `import { useMemo, useRef, useState } from "react";` → change to `import { useEffect, useRef, useState } from "react";` (useMemo is still used by `visibleRelations`, so keep it if needed — recheck and retain only the hooks you still use).

- [ ] **Step 3: Run tests + typecheck**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npm run test 2>&1 | tail -15
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx tsc -b 2>&1 | tail -10
```

Expected: 58 tests pass. Typecheck clean.

- [ ] **Step 4: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/useLandscapeLayout.ts viz-web/src/components/LandscapeMap/LandscapeMap.tsx
git commit -m "refactor(viz-web): extract useLandscapeLayout hook"
```

---

## Task 3: `useLandscapeZoom` hook + tests

**Files:**
- Create: `viz-web/src/components/LandscapeMap/useLandscapeZoom.ts`
- Create: `viz-web/src/components/LandscapeMap/useLandscapeZoom.test.ts`

**Rationale:** Encapsulate d3-zoom lifecycle. Not yet used by the component — we'll wire it up in Task 9.

- [ ] **Step 1: Write the failing test**

Create `viz-web/src/components/LandscapeMap/useLandscapeZoom.test.ts`:

```ts
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLandscapeZoom } from "./useLandscapeZoom";
import { useRef } from "react";

function setup() {
  const container = document.createElement("div");
  Object.defineProperty(container, "clientWidth", { value: 800, configurable: true });
  Object.defineProperty(container, "clientHeight", { value: 600, configurable: true });
  document.body.appendChild(container);
  const onTransformChange = vi.fn();
  const hookResult = renderHook(() => {
    const ref = useRef<HTMLDivElement | null>(container);
    return useLandscapeZoom({ containerRef: ref, onTransformChange });
  });
  return { container, onTransformChange, ...hookResult };
}

describe("useLandscapeZoom", () => {
  it("starts at scale 1", () => {
    const { result } = setup();
    expect(result.current.scale).toBe(1);
  });

  it("zoomIn multiplies scale by 1.4", () => {
    const { result } = setup();
    act(() => {
      result.current.zoomIn();
    });
    expect(result.current.scale).toBeCloseTo(1.4, 5);
  });

  it("zoomOut divides scale by 1.4", () => {
    const { result } = setup();
    act(() => {
      result.current.zoomIn();
      result.current.zoomOut();
    });
    expect(result.current.scale).toBeCloseTo(1, 5);
  });

  it("reset returns scale to 1", () => {
    const { result } = setup();
    act(() => {
      result.current.zoomIn();
      result.current.zoomIn();
      result.current.reset();
    });
    expect(result.current.scale).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/useLandscapeZoom.test.ts
```

Expected: FAIL with "Cannot find module './useLandscapeZoom'".

- [ ] **Step 3: Implement the hook**

Create `viz-web/src/components/LandscapeMap/useLandscapeZoom.ts`:

```ts
import * as d3 from "d3";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export interface LandscapeZoomTransform {
  x: number;
  y: number;
  k: number;
}

interface UseLandscapeZoomOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  onTransformChange?: (transform: LandscapeZoomTransform) => void;
}

const ZOOM_STEP = 1.4;
const SCALE_MIN = 0.5;
const SCALE_MAX = 8;

export function useLandscapeZoom({ containerRef, onTransformChange }: UseLandscapeZoomOptions) {
  const [scale, setScale] = useState(1);
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<HTMLDivElement, unknown> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      return;
    }
    const selection = d3.select(el as HTMLDivElement);
    const behavior = d3
      .zoom<HTMLDivElement, unknown>()
      .scaleExtent([SCALE_MIN, SCALE_MAX])
      .filter((event: Event) => {
        const target = event.target as Element | null;
        if (target && target.closest("[data-node-id]")) {
          return false;
        }
        if (event.type === "wheel") return true;
        if (event.type === "pointerdown" && (event as PointerEvent).button === 0) return true;
        if (event.type === "mousedown" && (event as MouseEvent).button === 0) return true;
        return false;
      })
      .on("zoom", (event) => {
        const { x, y, k } = event.transform;
        setScale(k);
        onTransformChange?.({ x, y, k });
      });
    selection.call(behavior);
    zoomBehaviorRef.current = behavior;
    return () => {
      selection.on(".zoom", null);
      zoomBehaviorRef.current = null;
    };
  }, [containerRef, onTransformChange]);

  const zoomIn = useCallback(() => {
    const el = containerRef.current;
    const behavior = zoomBehaviorRef.current;
    if (!el || !behavior) {
      setScale((s) => Math.min(SCALE_MAX, s * ZOOM_STEP));
      return;
    }
    d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.scaleBy, ZOOM_STEP);
  }, [containerRef]);

  const zoomOut = useCallback(() => {
    const el = containerRef.current;
    const behavior = zoomBehaviorRef.current;
    if (!el || !behavior) {
      setScale((s) => Math.max(SCALE_MIN, s / ZOOM_STEP));
      return;
    }
    d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.scaleBy, 1 / ZOOM_STEP);
  }, [containerRef]);

  const reset = useCallback(() => {
    const el = containerRef.current;
    const behavior = zoomBehaviorRef.current;
    if (!el || !behavior) {
      setScale(1);
      return;
    }
    d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.transform, d3.zoomIdentity);
  }, [containerRef]);

  const panBy = useCallback(
    (dx: number, dy: number) => {
      const el = containerRef.current;
      const behavior = zoomBehaviorRef.current;
      if (!el || !behavior) return;
      d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.translateBy, dx, dy);
    },
    [containerRef],
  );

  const panTo = useCallback(
    (x: number, y: number) => {
      const el = containerRef.current;
      const behavior = zoomBehaviorRef.current;
      if (!el || !behavior) return;
      const rect = el.getBoundingClientRect();
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      d3.select(el as HTMLDivElement)
        .transition()
        .duration(180)
        .call(behavior.translateTo, x, y, [centerX, centerY]);
    },
    [containerRef],
  );

  return { scale, zoomIn, zoomOut, reset, panBy, panTo };
}
```

Note: In jsdom the d3-zoom behavior will not fire synthetic events, so `scale` updates from `zoomIn`/`zoomOut` rely on the fallback path (when `behavior` exists but the d3 transition doesn't execute in jsdom). To make the test assertions deterministic, the hook falls back to directly updating `scale` when the zoom behavior's transition system isn't active. Verify with the test.

**Alternative:** If the test above still fails after implementing (because the d3 transition pathway updates scale asynchronously in jsdom in a way that `act()` can't catch), change the implementation so `zoomIn`/`zoomOut`/`reset` always synchronously update scale via `setScale` first, THEN call d3.zoom for the real DOM behavior. Example:

```ts
const zoomIn = useCallback(() => {
  setScale((s) => Math.min(SCALE_MAX, s * ZOOM_STEP));
  const el = containerRef.current;
  const behavior = zoomBehaviorRef.current;
  if (el && behavior) {
    d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.scaleBy, ZOOM_STEP);
  }
}, [containerRef]);
```

Use this dual-update pattern for `zoomIn`, `zoomOut`, and `reset` to keep the test deterministic while preserving real-DOM behavior.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/useLandscapeZoom.test.ts
```

Expected: 4/4 PASS.

If any test fails because scale didn't update, switch to the dual-update pattern shown in Step 3's "Alternative" block.

- [ ] **Step 5: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/useLandscapeZoom.ts viz-web/src/components/LandscapeMap/useLandscapeZoom.test.ts
git commit -m "feat(viz-web): add useLandscapeZoom hook"
```

---

## Task 4: `useLandscapeDrag` hook + tests

**Files:**
- Create: `viz-web/src/components/LandscapeMap/useLandscapeDrag.ts`
- Create: `viz-web/src/components/LandscapeMap/useLandscapeDrag.test.ts`

- [ ] **Step 1: Write the failing test**

Create `viz-web/src/components/LandscapeMap/useLandscapeDrag.test.ts`:

```ts
import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLandscapeDrag } from "./useLandscapeDrag";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useLandscapeDrag", () => {
  it("initial state is idle", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    expect(result.current.state.phase).toBe("idle");
  });

  it("beginDrag with button 0 transitions to dragging", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    act(() => {
      result.current.beginDrag("node-1", { clientX: 100, clientY: 200, button: 0, shiftKey: false });
    });
    expect(result.current.state.phase).toBe("dragging");
    if (result.current.state.phase === "dragging") {
      expect(result.current.state.nodeId).toBe("node-1");
      expect(result.current.state.dx).toBe(0);
      expect(result.current.state.dy).toBe(0);
    }
  });

  it("updateDrag updates dx/dy", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    act(() => {
      result.current.beginDrag("node-1", { clientX: 100, clientY: 200, button: 0, shiftKey: false });
      result.current.updateDrag({ clientX: 130, clientY: 240 });
    });
    expect(result.current.state.phase).toBe("dragging");
    if (result.current.state.phase === "dragging") {
      expect(result.current.state.dx).toBe(30);
      expect(result.current.state.dy).toBe(40);
    }
  });

  it("endDrag transitions to snapping-back then back to idle after 180ms", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    act(() => {
      result.current.beginDrag("node-1", { clientX: 100, clientY: 200, button: 0, shiftKey: false });
      result.current.updateDrag({ clientX: 150, clientY: 260 });
      result.current.endDrag();
    });
    expect(result.current.state.phase).toBe("snapping-back");
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.state.phase).toBe("idle");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/useLandscapeDrag.test.ts
```

Expected: FAIL with "Cannot find module './useLandscapeDrag'".

- [ ] **Step 3: Implement the hook**

Create `viz-web/src/components/LandscapeMap/useLandscapeDrag.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";

export type DragState =
  | { phase: "idle" }
  | { phase: "dragging"; nodeId: string; dx: number; dy: number }
  | { phase: "snapping-back"; nodeId: string; fromDx: number; fromDy: number; progress: number };

interface BeginDragEvent {
  clientX: number;
  clientY: number;
  button: number;
  shiftKey: boolean;
}

interface UpdateDragEvent {
  clientX: number;
  clientY: number;
}

const SNAP_BACK_MS = 180;

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export function useLandscapeDrag() {
  const [state, setState] = useState<DragState>({ phase: "idle" });
  const originRef = useRef<{ x: number; y: number } | null>(null);
  const snapTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const snapStartRef = useRef<number | null>(null);

  const beginDrag = useCallback((nodeId: string, event: BeginDragEvent) => {
    if (event.button !== 0 || event.shiftKey) {
      return;
    }
    originRef.current = { x: event.clientX, y: event.clientY };
    setState({ phase: "dragging", nodeId, dx: 0, dy: 0 });
  }, []);

  const updateDrag = useCallback((event: UpdateDragEvent) => {
    const origin = originRef.current;
    if (!origin) return;
    setState((prev) => {
      if (prev.phase !== "dragging") return prev;
      return {
        phase: "dragging",
        nodeId: prev.nodeId,
        dx: event.clientX - origin.x,
        dy: event.clientY - origin.y,
      };
    });
  }, []);

  const endDrag = useCallback(() => {
    setState((prev) => {
      if (prev.phase !== "dragging") return prev;
      snapStartRef.current = Date.now();
      const snap: DragState = {
        phase: "snapping-back",
        nodeId: prev.nodeId,
        fromDx: prev.dx,
        fromDy: prev.dy,
        progress: 0,
      };
      if (snapTimeoutRef.current) {
        clearTimeout(snapTimeoutRef.current);
      }
      snapTimeoutRef.current = setTimeout(() => {
        setState({ phase: "idle" });
        originRef.current = null;
        snapStartRef.current = null;
      }, SNAP_BACK_MS);
      return snap;
    });
  }, []);

  // rAF loop for snap-back progress updates during the 180ms window
  useEffect(() => {
    if (state.phase !== "snapping-back") return;
    let raf = 0;
    const tick = () => {
      const start = snapStartRef.current;
      if (!start) return;
      const elapsed = Date.now() - start;
      const progress = Math.min(1, elapsed / SNAP_BACK_MS);
      const eased = easeOutCubic(progress);
      setState((prev) => {
        if (prev.phase !== "snapping-back") return prev;
        return { ...prev, progress: eased };
      });
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [state.phase]);

  useEffect(() => {
    return () => {
      if (snapTimeoutRef.current) {
        clearTimeout(snapTimeoutRef.current);
      }
    };
  }, []);

  return { state, beginDrag, updateDrag, endDrag };
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/useLandscapeDrag.test.ts
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/useLandscapeDrag.ts viz-web/src/components/LandscapeMap/useLandscapeDrag.test.ts
git commit -m "feat(viz-web): add useLandscapeDrag hook with snap-back"
```

---

## Task 5: `LandscapeCanvas` component (no test)

**Files:**
- Create: `viz-web/src/components/LandscapeMap/LandscapeCanvas.tsx`

**Rationale:** Canvas rendering can't be meaningfully unit-tested in jsdom. The behavior will be integration-tested via `LandscapeMap.test.tsx` at Task 9 (which asserts DOM side effects, not canvas pixels).

- [ ] **Step 1: Create `LandscapeCanvas.tsx`**

Create `viz-web/src/components/LandscapeMap/LandscapeCanvas.tsx`:

```tsx
import { useEffect, useRef } from "react";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";
import { KIND_STROKE } from "../../ui";
import type { PositionedNode } from "./useLandscapeLayout";
import type { DragState } from "./useLandscapeDrag";
import type { LandscapeZoomTransform } from "./useLandscapeZoom";

const PHASE_FILL: Record<string, string> = {
  emerging: "#C94F2B",
  flash_event: "#D97706",
  sustained: "#0D7C66",
  fading: "#2F6FB5",
  steady: "#5C4A39",
};

const NEUTRAL_FILL = "#F0E6D2";

interface LandscapeCanvasProps {
  nodes: PositionedNode[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  dragState: DragState;
  transform: LandscapeZoomTransform;
  width: number;
  height: number;
}

function fillFor(node: GraphNodeRow): string {
  if (node.kind === "theme" && node.phase) {
    return PHASE_FILL[String(node.phase)] ?? NEUTRAL_FILL;
  }
  return NEUTRAL_FILL;
}

function isRelated(nodeId: string, hoveredId: string, relations: SnapshotRelation[]): boolean {
  return relations.some(
    (rel) =>
      (rel.source === hoveredId && rel.target === nodeId) ||
      (rel.target === hoveredId && rel.source === nodeId),
  );
}

function nodeOffset(node: PositionedNode, dragState: DragState): { x: number; y: number } {
  if (dragState.phase === "dragging" && dragState.nodeId === node.node_id) {
    return { x: node.x + dragState.dx, y: node.y + dragState.dy };
  }
  if (dragState.phase === "snapping-back" && dragState.nodeId === node.node_id) {
    const remaining = 1 - dragState.progress;
    return { x: node.x + remaining * dragState.fromDx, y: node.y + remaining * dragState.fromDy };
  }
  return { x: node.x, y: node.y };
}

export function LandscapeCanvas({
  nodes,
  relations,
  hoveredNodeId,
  dragState,
  transform,
  width,
  height,
}: LandscapeCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.scale(dpr, dpr);
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // Relations (only when a node is hovered)
    if (hoveredNodeId) {
      ctx.strokeStyle = "#1A1715";
      for (const rel of relations) {
        if (rel.source !== hoveredNodeId && rel.target !== hoveredNodeId) continue;
        const src = nodes.find((n) => n.node_id === rel.source);
        const tgt = nodes.find((n) => n.node_id === rel.target);
        if (!src || !tgt) continue;
        const srcPos = nodeOffset(src, dragState);
        const tgtPos = nodeOffset(tgt, dragState);
        ctx.globalAlpha = Math.min(0.7, rel.score / 4);
        ctx.lineWidth = Math.max(1, rel.score);
        ctx.beginPath();
        ctx.moveTo(srcPos.x, srcPos.y);
        ctx.lineTo(tgtPos.x, tgtPos.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // Bubbles
    for (const node of nodes) {
      const { x, y } = nodeOffset(node, dragState);
      const dimmed =
        hoveredNodeId !== null &&
        hoveredNodeId !== node.node_id &&
        !isRelated(node.node_id, hoveredNodeId, relations);

      ctx.globalAlpha = dimmed ? 0.16 : 0.9;
      ctx.fillStyle = fillFor(node);
      ctx.strokeStyle = KIND_STROKE[node.kind];
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, node.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Semantic label culling — only draw labels when effectively large enough on screen
      if (node.r * transform.k > 24) {
        ctx.globalAlpha = dimmed ? 0.18 : 1;
        ctx.fillStyle = "#1A1715";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = "600 13px Inter, system-ui, sans-serif";
        const label = node.display_name.length > 18 ? `${node.display_name.slice(0, 18)}…` : node.display_name;
        ctx.fillText(label, x, y - 4);
        ctx.font = "500 11px Inter, system-ui, sans-serif";
        ctx.globalAlpha = dimmed ? 0.14 : 0.75;
        ctx.fillText(node.kind, x, y + 10);
      }
    }

    ctx.restore();
  }, [nodes, relations, hoveredNodeId, dragState, transform, width, height]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none"
      aria-hidden="true"
    />
  );
}
```

- [ ] **Step 2: Run typecheck + tests to confirm no regressions**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx tsc -b 2>&1 | tail -10
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npm run test 2>&1 | tail -15
```

Expected: typecheck clean, 58+4+4 = 66 tests pass (58 baseline + 4 zoom + 4 drag). The new `LandscapeCanvas` is not yet imported by anything, so tests are unchanged by this commit.

- [ ] **Step 3: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/LandscapeCanvas.tsx
git commit -m "feat(viz-web): add LandscapeCanvas component"
```

---

## Task 6: `LandscapeHitLayer` component (no test)

**Files:**
- Create: `viz-web/src/components/LandscapeMap/LandscapeHitLayer.tsx`

**Rationale:** HitLayer rendering and event handling are integration-tested via `LandscapeMap.test.tsx` at Task 9.

- [ ] **Step 1: Create `LandscapeHitLayer.tsx`**

Create `viz-web/src/components/LandscapeMap/LandscapeHitLayer.tsx`:

```tsx
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent, FocusEvent as ReactFocusEvent } from "react";
import type { PositionedNode } from "./useLandscapeLayout";
import type { DragState } from "./useLandscapeDrag";

interface LandscapeHitLayerProps {
  nodes: PositionedNode[];
  hoveredNodeId: string | null;
  dragState: DragState;
  onHover: (nodeId: string | null, clientX: number, clientY: number) => void;
  onHoverEnd: () => void;
  onNodeClick: (node: PositionedNode, event: ReactMouseEvent<HTMLButtonElement>) => void;
  onPointerDown: (node: PositionedNode, event: ReactPointerEvent<HTMLButtonElement>) => void;
  onKeyDown: (node: PositionedNode, event: ReactKeyboardEvent<HTMLButtonElement>) => void;
  onFocus: (node: PositionedNode, event: ReactFocusEvent<HTMLButtonElement>) => void;
}

function ariaLabelFor(node: PositionedNode): string {
  const kindLabel = node.kind;
  return `${node.display_name}, ${kindLabel}, score ${node.score.toFixed(2)}`;
}

export function LandscapeHitLayer({
  nodes,
  dragState,
  onHover,
  onHoverEnd,
  onNodeClick,
  onPointerDown,
  onKeyDown,
  onFocus,
}: LandscapeHitLayerProps) {
  return (
    <div className="hit-layer absolute inset-0" data-testid="landscape-hit-layer">
      {nodes.map((node) => {
        const isDragging = dragState.phase === "dragging" && dragState.nodeId === node.node_id;
        const dragOffsetX = isDragging ? dragState.dx : 0;
        const dragOffsetY = isDragging ? dragState.dy : 0;
        return (
          <button
            key={node.node_id}
            type="button"
            data-node-id={node.node_id}
            aria-label={ariaLabelFor(node)}
            tabIndex={0}
            onMouseEnter={(event) => onHover(node.node_id, event.clientX, event.clientY)}
            onMouseMove={(event) => onHover(node.node_id, event.clientX, event.clientY)}
            onMouseLeave={onHoverEnd}
            onFocus={(event) => onFocus(node, event)}
            onClick={(event) => onNodeClick(node, event)}
            onPointerDown={(event) => onPointerDown(node, event)}
            onKeyDown={(event) => onKeyDown(node, event)}
            className="absolute rounded-full bg-transparent border-0 p-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-phase-emerging focus-visible:outline-offset-2"
            style={{
              left: `${node.x - node.r + dragOffsetX}px`,
              top: `${node.y - node.r + dragOffsetY}px`,
              width: `${node.r * 2}px`,
              height: `${node.r * 2}px`,
            }}
          />
        );
      })}
    </div>
  );
}
```

Note: `rounded-full` is intentional here — the buttons are visually invisible but must match the bubble's circular shape for accurate hit testing and focus-ring display. This matches the existing exemption for circular indicator dots in `KindChip`, `LandscapeTable`, and `LoadingState`.

- [ ] **Step 2: Run typecheck**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx tsc -b 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/LandscapeHitLayer.tsx
git commit -m "feat(viz-web): add LandscapeHitLayer component"
```

---

## Task 7: `LandscapeControls` component + tests

**Files:**
- Create: `viz-web/src/components/LandscapeMap/LandscapeControls.tsx`
- Create: `viz-web/src/components/LandscapeMap/LandscapeControls.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `viz-web/src/components/LandscapeMap/LandscapeControls.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapeControls } from "./LandscapeControls";

describe("LandscapeControls", () => {
  it("renders zoom in, zoom out, and reset buttons", () => {
    render(
      <LandscapeControls scale={1} onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();
  });

  it("renders scale indicator with formatted value", () => {
    render(
      <LandscapeControls scale={1.42} onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={() => undefined} />,
    );
    expect(screen.getByText(/×\s*1\.42/)).toBeInTheDocument();
  });

  it("clicking zoom in button calls onZoomIn", async () => {
    const handler = vi.fn();
    render(
      <LandscapeControls scale={1} onZoomIn={handler} onZoomOut={() => undefined} onReset={() => undefined} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("clicking reset button calls onReset", async () => {
    const handler = vi.fn();
    render(
      <LandscapeControls scale={2} onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={handler} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/LandscapeControls.test.tsx
```

Expected: FAIL with "Cannot find module './LandscapeControls'".

- [ ] **Step 3: Implement the component**

Create `viz-web/src/components/LandscapeMap/LandscapeControls.tsx`:

```tsx
interface LandscapeControlsProps {
  scale: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

export function LandscapeControls({ scale, onZoomIn, onZoomOut, onReset }: LandscapeControlsProps) {
  return (
    <>
      <div className="absolute top-2 right-2 z-10 flex flex-col bg-card border border-ink rounded-sm overflow-hidden">
        <button
          type="button"
          aria-label="Zoom in"
          onClick={onZoomIn}
          className="w-6 h-6 p-0 bg-transparent text-ink font-mono text-[0.78rem] cursor-pointer hover:bg-ink hover:text-paper border-0 border-b border-ink"
        >
          +
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          onClick={onZoomOut}
          className="w-6 h-6 p-0 bg-transparent text-ink font-mono text-[0.78rem] cursor-pointer hover:bg-ink hover:text-paper border-0 border-b border-ink"
        >
          −
        </button>
        <button
          type="button"
          aria-label="Reset view"
          onClick={onReset}
          className="w-6 h-6 p-0 bg-transparent text-ink font-mono text-[0.72rem] cursor-pointer hover:bg-ink hover:text-paper border-0"
        >
          ⌂
        </button>
      </div>
      <div className="absolute bottom-2 left-2 z-10 font-mono text-[0.6rem] text-muted bg-card border border-ink/20 rounded-sm px-1.5 py-0.5">
        × {scale.toFixed(2)}
      </div>
      <div className="absolute bottom-2 right-2 z-10 font-mono text-[0.56rem] text-muted bg-card border border-ink/20 rounded-sm px-1.5 py-0.5">
        + − 0 ← → ↑ ↓
      </div>
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/LandscapeControls.test.tsx
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/LandscapeControls.tsx viz-web/src/components/LandscapeMap/LandscapeControls.test.tsx
git commit -m "feat(viz-web): add LandscapeControls component"
```

---

## Task 8: `LandscapePreviewPopover` component + tests

**Files:**
- Create: `viz-web/src/components/LandscapeMap/LandscapePreviewPopover.tsx`
- Create: `viz-web/src/components/LandscapeMap/LandscapePreviewPopover.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `viz-web/src/components/LandscapeMap/LandscapePreviewPopover.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapePreviewPopover } from "./LandscapePreviewPopover";
import type { GraphNodeRow } from "../../lib/types";

const node: GraphNodeRow = {
  node_id: "1",
  kind: "theme",
  slug: "election",
  display_name: "US election narratives",
  summary: "Election coverage across the RT feed",
  article_count: 142,
  score: 84,
  phase: "emerging",
};

describe("LandscapePreviewPopover", () => {
  it("renders display name, kind, and score", () => {
    render(
      <LandscapePreviewPopover node={node} x={100} y={200} onClose={() => undefined} onNavigate={() => undefined} />,
    );
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText(/theme/i)).toBeInTheDocument();
    expect(screen.getByText(/84\.00/)).toBeInTheDocument();
  });

  it("clicking 'Open detail' calls onNavigate with the node", async () => {
    const handler = vi.fn();
    render(
      <LandscapePreviewPopover node={node} x={100} y={200} onClose={() => undefined} onNavigate={handler} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /open detail/i }));
    expect(handler).toHaveBeenCalledWith(node);
  });

  it("pressing Escape calls onClose", () => {
    const handler = vi.fn();
    render(
      <LandscapePreviewPopover node={node} x={100} y={200} onClose={handler} onNavigate={() => undefined} />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/LandscapePreviewPopover.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement the component**

Create `viz-web/src/components/LandscapeMap/LandscapePreviewPopover.tsx`:

```tsx
import { useEffect } from "react";
import type { GraphNodeRow } from "../../lib/types";
import { Eyebrow, KIND_LABEL } from "../../ui";

interface LandscapePreviewPopoverProps {
  node: GraphNodeRow;
  x: number;
  y: number;
  onClose: () => void;
  onNavigate: (node: GraphNodeRow) => void;
}

export function LandscapePreviewPopover({ node, x, y, onClose, onNavigate }: LandscapePreviewPopoverProps) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed z-30 bg-card border border-ink rounded-sm shadow-lg p-3 w-[18rem] max-w-[calc(100vw-2rem)]"
      style={{ left: `${x + 12}px`, top: `${y + 12}px` }}
      role="dialog"
      aria-label="Node preview"
    >
      <Eyebrow>{`Pinned · ${node.kind.toUpperCase()}`}</Eyebrow>
      <h3 className="text-[1.05rem] leading-tight mt-1">{node.display_name}</h3>
      <div className="font-mono text-[0.64rem] text-muted mt-1">
        {KIND_LABEL[node.kind]} · score {node.score.toFixed(2)} · {node.article_count} stories
      </div>
      {node.summary ? (
        <p className="mt-2 text-[0.76rem] text-ink/85 leading-snug">{node.summary}</p>
      ) : null}
      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onNavigate(node)}
          className="font-mono text-[0.68rem] text-ink underline underline-offset-2 decoration-ink/25 hover:decoration-ink/60 bg-transparent border-0 cursor-pointer p-0"
        >
          Open detail →
        </button>
        <button
          type="button"
          onClick={onClose}
          className="font-mono text-[0.62rem] text-muted bg-transparent border border-ink/25 rounded-sm px-1.5 py-0.5 cursor-pointer hover:border-ink/60"
        >
          Dismiss (Esc)
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx vitest run src/components/LandscapeMap/LandscapePreviewPopover.test.tsx
```

Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/LandscapePreviewPopover.tsx viz-web/src/components/LandscapeMap/LandscapePreviewPopover.test.tsx
git commit -m "feat(viz-web): add LandscapePreviewPopover component"
```

---

## Task 9: Rewrite `LandscapeMap.tsx` + integration tests

**Files:**
- Modify: `viz-web/src/components/LandscapeMap/LandscapeMap.tsx`
- Modify: `viz-web/src/components/LandscapeMap/LandscapeMap.test.tsx`

**Rationale:** This is the assembly step. Wire all the new pieces together, replace the SVG rendering with canvas + hit layer, replace the old DOM-based tests with behavioral tests against the button overlay.

- [ ] **Step 1: Replace `LandscapeMap.tsx` contents**

Replace the entire contents of `viz-web/src/components/LandscapeMap/LandscapeMap.tsx` with:

```tsx
import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type FocusEvent as ReactFocusEvent } from "react";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";
import { useElementSize } from "../../hooks/useElementSize";
import { NodeTooltip } from "../NodeTooltip";
import { LandscapeCanvas } from "./LandscapeCanvas";
import { LandscapeControls } from "./LandscapeControls";
import { LandscapeHitLayer } from "./LandscapeHitLayer";
import { LandscapePreviewPopover } from "./LandscapePreviewPopover";
import { useLandscapeDrag } from "./useLandscapeDrag";
import { useLandscapeLayout, type PositionedNode } from "./useLandscapeLayout";
import { useLandscapeZoom, type LandscapeZoomTransform } from "./useLandscapeZoom";

const INITIAL_TRANSFORM: LandscapeZoomTransform = { x: 0, y: 0, k: 1 };
const CANVAS_HEIGHT = 520;

interface LandscapeMapProps {
  nodes: GraphNodeRow[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  onHover: (nodeId: string | null) => void;
  onNodeClick: (node: GraphNodeRow) => void;
}

export function LandscapeMap({ nodes, relations, hoveredNodeId, onHover, onNodeClick }: LandscapeMapProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const zoomLayerRef = useRef<HTMLDivElement | null>(null);
  const { width } = useElementSize(container);
  const canvasWidth = Math.max(width, 720);

  const [transform, setTransform] = useState<LandscapeZoomTransform>(INITIAL_TRANSFORM);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; node: GraphNodeRow } | null>(null);
  const [previewNode, setPreviewNode] = useState<GraphNodeRow | null>(null);
  const [previewAnchor, setPreviewAnchor] = useState<{ x: number; y: number } | null>(null);

  const positioned = useLandscapeLayout(nodes, width);
  const drag = useLandscapeDrag();

  const handleTransformChange = useCallback((t: LandscapeZoomTransform) => {
    setTransform(t);
    if (zoomLayerRef.current) {
      zoomLayerRef.current.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.k})`;
    }
  }, []);

  const zoom = useLandscapeZoom({
    containerRef,
    onTransformChange: handleTransformChange,
  });

  const setContainerRef = useCallback((node: HTMLDivElement | null) => {
    setContainer(node);
    containerRef.current = node;
  }, []);

  // Hover handlers
  const handleHover = useCallback(
    (nodeId: string | null, clientX: number, clientY: number) => {
      onHover(nodeId);
      if (nodeId) {
        const node = positioned.find((n) => n.node_id === nodeId);
        if (node) {
          setTooltipPos({ x: clientX + 10, y: clientY + 10, node });
        }
      }
    },
    [onHover, positioned],
  );

  const handleHoverEnd = useCallback(() => {
    onHover(null);
    setTooltipPos(null);
  }, [onHover]);

  // Click handler: shift-click → preview, else navigate
  const handleNodeClick = useCallback(
    (node: PositionedNode, event: ReactMouseEvent<HTMLButtonElement>) => {
      if (event.shiftKey) {
        setPreviewNode(node);
        setPreviewAnchor({ x: event.clientX, y: event.clientY });
      } else {
        onNodeClick(node);
      }
    },
    [onNodeClick],
  );

  // Drag handlers wired to button pointer events
  const handlePointerDown = useCallback(
    (node: PositionedNode, event: ReactPointerEvent<HTMLButtonElement>) => {
      if (event.shiftKey || event.button !== 0) return;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      drag.beginDrag(node.node_id, {
        clientX: event.clientX,
        clientY: event.clientY,
        button: event.button,
        shiftKey: event.shiftKey,
      });
    },
    [drag],
  );

  // Global pointermove / pointerup listeners while dragging
  useEffect(() => {
    if (drag.state.phase !== "dragging") return;
    const handleMove = (event: PointerEvent) => {
      drag.updateDrag({ clientX: event.clientX, clientY: event.clientY });
    };
    const handleUp = () => {
      drag.endDrag();
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [drag]);

  // Keyboard shortcuts on the outer container
  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      switch (event.key) {
        case "+":
        case "=":
          event.preventDefault();
          zoom.zoomIn();
          return;
        case "-":
        case "_":
          event.preventDefault();
          zoom.zoomOut();
          return;
        case "0":
          event.preventDefault();
          zoom.reset();
          return;
        case "ArrowLeft":
          event.preventDefault();
          zoom.panBy(48, 0);
          return;
        case "ArrowRight":
          event.preventDefault();
          zoom.panBy(-48, 0);
          return;
        case "ArrowUp":
          event.preventDefault();
          zoom.panBy(0, 48);
          return;
        case "ArrowDown":
          event.preventDefault();
          zoom.panBy(0, -48);
          return;
        case "Escape":
          setPreviewNode(null);
          setPreviewAnchor(null);
          return;
      }
    },
    [zoom],
  );

  // Shift+Enter on a focused button opens the preview
  const handleButtonKeyDown = useCallback(
    (node: PositionedNode, event: ReactKeyboardEvent<HTMLButtonElement>) => {
      if (event.key === "Enter" && event.shiftKey) {
        event.preventDefault();
        const rect = event.currentTarget.getBoundingClientRect();
        setPreviewNode(node);
        setPreviewAnchor({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
      }
    },
    [],
  );

  // Auto-pan when a focused bubble is off-screen
  const handleFocus = useCallback(
    (node: PositionedNode, event: ReactFocusEvent<HTMLButtonElement>) => {
      const container = containerRef.current;
      if (!container) return;
      const buttonRect = event.currentTarget.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const outOfBounds =
        buttonRect.left < containerRect.left ||
        buttonRect.right > containerRect.right ||
        buttonRect.top < containerRect.top ||
        buttonRect.bottom > containerRect.bottom;
      if (outOfBounds) {
        zoom.panTo(node.x, node.y);
      }
    },
    [zoom],
  );

  return (
    <div className="p-4 bg-ink/[0.02]">
      <div className="flex items-baseline justify-between mb-2">
        <p className="uppercase tracking-[0.16em] text-[0.6rem] font-semibold text-muted">Heat map</p>
        <p className="font-mono text-[0.66rem] text-muted">ring = kind · fill = phase (themes) · size = score</p>
      </div>
      <div
        ref={setContainerRef}
        tabIndex={0}
        role="img"
        aria-label="Heat map of nodes"
        onKeyDown={handleKeyDown}
        className="relative border border-ink/15 bg-card rounded-sm overflow-hidden min-h-[420px] focus-visible:outline-2 focus-visible:outline-ink"
        style={{ height: CANVAS_HEIGHT }}
      >
        <LandscapeCanvas
          nodes={positioned}
          relations={relations}
          hoveredNodeId={hoveredNodeId}
          dragState={drag.state}
          transform={transform}
          width={canvasWidth}
          height={CANVAS_HEIGHT}
        />
        <div
          ref={zoomLayerRef}
          className="zoom-layer absolute inset-0 origin-top-left"
          style={{ transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.k})` }}
        >
          <LandscapeHitLayer
            nodes={positioned}
            hoveredNodeId={hoveredNodeId}
            dragState={drag.state}
            onHover={handleHover}
            onHoverEnd={handleHoverEnd}
            onNodeClick={handleNodeClick}
            onPointerDown={handlePointerDown}
            onKeyDown={handleButtonKeyDown}
            onFocus={handleFocus}
          />
        </div>
        <LandscapeControls
          scale={zoom.scale}
          onZoomIn={zoom.zoomIn}
          onZoomOut={zoom.zoomOut}
          onReset={zoom.reset}
        />
      </div>
      {tooltipPos ? <NodeTooltip x={tooltipPos.x} y={tooltipPos.y} node={tooltipPos.node} /> : null}
      {previewNode && previewAnchor ? (
        <LandscapePreviewPopover
          node={previewNode}
          x={previewAnchor.x}
          y={previewAnchor.y}
          onClose={() => {
            setPreviewNode(null);
            setPreviewAnchor(null);
          }}
          onNavigate={(node) => {
            setPreviewNode(null);
            setPreviewAnchor(null);
            onNodeClick(node);
          }}
        />
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Replace `LandscapeMap.test.tsx` contents**

Replace `viz-web/src/components/LandscapeMap/LandscapeMap.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapeMap } from "./LandscapeMap";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";

const nodes: GraphNodeRow[] = [
  {
    node_id: "1",
    kind: "theme",
    slug: "election",
    display_name: "US election narratives",
    summary: "Election coverage",
    article_count: 140,
    score: 84,
    phase: "emerging",
  },
  {
    node_id: "2",
    kind: "event",
    slug: "april-8",
    display_name: "April 8 Hormuz",
    article_count: 89,
    score: 72,
  },
];
const relations: SnapshotRelation[] = [];

function setup(overrides: Partial<Parameters<typeof LandscapeMap>[0]> = {}) {
  const onHover = vi.fn();
  const onNodeClick = vi.fn();
  return {
    onHover,
    onNodeClick,
    ...render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={onHover}
        onNodeClick={onNodeClick}
        {...overrides}
      />,
    ),
  };
}

describe("LandscapeMap", () => {
  it("renders one button per node", () => {
    setup();
    const buttons = screen.getAllByRole("button").filter((b) => b.getAttribute("data-node-id"));
    expect(buttons).toHaveLength(2);
  });

  it("each bubble button has an aria-label including display name and kind", () => {
    setup();
    expect(screen.getByRole("button", { name: /US election narratives.*theme.*84\.00/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /April 8 Hormuz.*event.*72\.00/ })).toBeInTheDocument();
  });

  it("plain click calls onNodeClick", async () => {
    const user = userEvent.setup();
    const { onNodeClick } = setup();
    await user.click(screen.getByRole("button", { name: /US election narratives/ }));
    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ node_id: "1" }));
  });

  it("shift-click opens the preview popover instead of navigating", async () => {
    const user = userEvent.setup();
    const { onNodeClick } = setup();
    await user.keyboard("{Shift>}");
    await user.click(screen.getByRole("button", { name: /US election narratives/ }));
    await user.keyboard("{/Shift}");
    expect(onNodeClick).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: /node preview/i })).toBeInTheDocument();
    expect(screen.getAllByText(/US election narratives/).length).toBeGreaterThanOrEqual(2); // button label + popover title
  });

  it("renders caption legend", () => {
    setup();
    expect(screen.getByText("Heat map")).toBeInTheDocument();
    expect(screen.getByText(/ring = kind/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npm run test 2>&1 | tail -25
```

Expected: 75/75 tests pass. Breakdown:
- 58 pre-existing tests (unchanged)
- 4 from `useLandscapeZoom.test.ts`
- 4 from `useLandscapeDrag.test.ts`
- 4 from `LandscapeControls.test.tsx`
- 3 from `LandscapePreviewPopover.test.tsx`
- 5 from the new `LandscapeMap.test.tsx` (replacing the previous 3)
- Net: 58 + 4 + 4 + 4 + 3 + 5 − 3 = **75**

If any test fails:
- If the `shift-click` test can't find the dialog: check that the popover's `role="dialog"` and `aria-label="Node preview"` attributes are present in `LandscapePreviewPopover.tsx`.
- If the button-count test returns 0 buttons: verify `LandscapeHitLayer.tsx` renders `<button>` elements with `data-node-id` attributes.
- If tests fail with "Cannot find module": check import paths after the subdirectory move (should be `../../lib/types` not `../lib/types`).

- [ ] **Step 4: Run typecheck**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx tsc -b 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper
git add viz-web/src/components/LandscapeMap/LandscapeMap.tsx viz-web/src/components/LandscapeMap/LandscapeMap.test.tsx
git commit -m "feat(viz-web): wire zoom, drag, controls, and preview into LandscapeMap"
```

---

## Task 10: Final verification

- [ ] **Step 1: Full build**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npm run build 2>&1 | tail -20
```

Expected: successful build, `dist/` produced. Chunk-size warning is expected (pre-existing from D3 + Recharts).

- [ ] **Step 2: Full typecheck**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npx tsc -b 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Full test suite**

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper/viz-web && npm run test 2>&1 | tail -20
```

Expected: 75/75 passing.

- [ ] **Step 4: Forbidden-pattern scan**

Run these from the repo root:

```bash
cd /Users/lfpmb/Documents/telegram-twitter-scraper

# No legacy topic-centric names in LandscapeMap/
grep -rn "TopicDetailView\|TopicTooltip\|TopicHeaderBand" viz-web/src/components/LandscapeMap/ || echo "✓ no topic terms"

# No backdrop-filter / backdrop-blur
grep -rn "backdrop-filter\|backdrop-blur" viz-web/src/components/LandscapeMap/ || echo "✓ no glassmorphism"

# No Google Fonts runtime import
grep -rn "fonts.googleapis.com" viz-web/src/components/LandscapeMap/ || echo "✓ no google fonts"

# rounded-full allowed only on circular bubble buttons in LandscapeHitLayer (comment documents the exemption)
grep -n "rounded-full" viz-web/src/components/LandscapeMap/ -r
```

Expected: each of the first three greps prints a "✓" line. The fourth grep should show exactly one match in `LandscapeHitLayer.tsx` — the circular hit buttons — which is the documented exemption.

- [ ] **Step 5: Report status**

Report the final state:
- Test count
- Typecheck result
- Build result
- Branch name
- Commits landed in this plan (use `git log --oneline feature/heatmap-zoom ^main | wc -l` and `git log --oneline feature/heatmap-zoom ^main`)

No commit for this task unless a regression was found and fixed. If a regression was found, the fix should be committed as part of the task that introduced it (bisectable history).

---

## Self-review

### Spec coverage

| Spec section | Implemented in |
|---|---|
| Architecture (canvas + button overlay + zoom-layer) | Task 9 (LandscapeMap.tsx), Task 5 (Canvas), Task 6 (HitLayer) |
| `useLandscapeLayout` | Task 2 |
| `useLandscapeZoom` | Task 3 |
| `useLandscapeDrag` | Task 4 |
| `LandscapeCanvas` | Task 5 |
| `LandscapeHitLayer` | Task 6 |
| `LandscapeControls` | Task 7 |
| `LandscapePreviewPopover` | Task 8 |
| d3-zoom filter (ignore events on bubble buttons) | Task 3 |
| Click = navigate, shift-click = preview | Task 9 (handleNodeClick) |
| Keyboard shortcuts (+/- 0 arrows Escape) | Task 9 (handleKeyDown) |
| Auto-pan on focus off-screen | Task 9 (handleFocus) |
| Snap-back animation 180ms | Task 4 (SNAP_BACK_MS) |
| Preview closes on Escape | Task 8 (useEffect keydown listener) + Task 9 (handleKeyDown Escape) |
| Semantic label culling based on effective zoom size | Task 5 (`node.r * transform.k > 24` check) |
| 75 tests total | Tasks 3, 4, 7, 8, 9 |
| Integration tests replace old DOM-based tests | Task 9 |
| Migration order (10 commits) | Tasks 1–10 |

### Placeholder scan

Scanned for "TBD", "TODO", "implement later", "add appropriate error handling" — none found. Every step has concrete code or concrete commands.

### Type consistency

- `PositionedNode` defined in Task 2, used consistently in Tasks 5, 6, 9.
- `DragState` defined in Task 4, used in Tasks 5, 6, 9.
- `LandscapeZoomTransform` defined in Task 3, used in Tasks 5, 9.
- Hook return signatures match between definition and consumption:
  - `useLandscapeZoom` returns `{ scale, zoomIn, zoomOut, reset, panBy, panTo }` — consumed in Task 9
  - `useLandscapeDrag` returns `{ state, beginDrag, updateDrag, endDrag }` — consumed in Task 9
- Callback signatures on `LandscapeHitLayer` match those defined in Task 6 and consumed in Task 9:
  - `onHover(nodeId, clientX, clientY)` ✓
  - `onNodeClick(node, event)` ✓
  - `onPointerDown(node, event)` ✓
  - `onKeyDown(node, event)` ✓
  - `onFocus(node, event)` ✓

Plan is internally consistent and ready for execution.
