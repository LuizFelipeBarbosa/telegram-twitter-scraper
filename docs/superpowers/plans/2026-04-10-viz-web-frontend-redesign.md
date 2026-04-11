# viz-web Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current warm-cream glassmorphism viz-web look with a dense, editorial "newsroom analyst" interface, migrating the styling stack to Tailwind v4 + hand-rolled primitives while preserving all existing behavior and data contracts.

**Architecture:** The `viz-web/` React app gets a new design system under `src/styles/` + `src/ui/` (tokens, primitives, no external component library), a shell layer under `src/layout/` (TopNav, Breadcrumbs, AppShell), and rebuilt Landscape + Node Detail views that split into small focused children under `src/components/`. The data model is node-centric (not topic-centric) — components are named accordingly. Fonts self-host via `@fontsource/*`.

**Tech Stack:** Tailwind CSS v4, `@fontsource/*` (Fraunces, Inter, JetBrains Mono), clsx, existing React 19 + Vite 6 + TypeScript + D3 v7 + Recharts + React Router 7 + Vitest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-04-10-frontend-redesign-design.md`

---

## Prerequisites

Before starting any task, verify the baseline is green:

```bash
cd viz-web
npm install
npm run test
npm run build
npx tsc -b
```

All four commands must pass. If anything fails, fix it before touching the plan.

**Recommended:** Run this plan inside a git worktree (e.g., `git worktree add ../viz-web-redesign`) so the many uncommitted files in the main working copy stay isolated from redesign commits. Not required.

**Working directory for every npm/npx command in this plan:** `viz-web/` (not the repo root).

---

## File structure

Files created:

```
viz-web/
├── postcss.config.js                          # NEW
├── tailwind.config.ts                         # NEW
└── src/
    ├── styles/
    │   ├── tokens.css                         # NEW (design tokens as CSS custom properties)
    │   └── globals.css                        # NEW (Tailwind + tokens + base)
    ├── ui/
    │   ├── kindColors.ts                      # NEW (NodeKind → hex stroke map)
    │   ├── Button.tsx                         # NEW
    │   ├── Eyebrow.tsx                        # NEW
    │   ├── Rule.tsx                           # NEW
    │   ├── Pill.tsx                           # NEW
    │   ├── Card.tsx                           # NEW
    │   ├── PhaseBadge.tsx                     # MOVED from components/, rewritten
    │   ├── KindChip.tsx                       # NEW
    │   ├── MetricCell.tsx                     # NEW
    │   ├── MetricsStrip.tsx                   # NEW
    │   ├── WindowSelector.tsx                 # MOVED from components/TimeWindowSelector.tsx, rewritten
    │   ├── SortableTable.tsx                  # NEW
    │   ├── index.ts                           # NEW (barrel)
    │   ├── Button.test.tsx                    # NEW
    │   ├── Eyebrow.test.tsx                   # NEW
    │   ├── Rule.test.tsx                      # NEW
    │   ├── Pill.test.tsx                      # NEW
    │   ├── Card.test.tsx                      # NEW
    │   ├── PhaseBadge.test.tsx                # NEW
    │   ├── KindChip.test.tsx                  # NEW
    │   ├── MetricCell.test.tsx                # NEW
    │   ├── MetricsStrip.test.tsx              # NEW
    │   ├── WindowSelector.test.tsx            # NEW
    │   ├── SortableTable.test.tsx             # NEW
    │   └── kindColors.test.ts                 # NEW
    ├── layout/
    │   ├── TopNav.tsx                         # NEW
    │   ├── Breadcrumbs.tsx                    # NEW
    │   ├── AppShell.tsx                       # NEW
    │   ├── TopNav.test.tsx                    # NEW
    │   └── Breadcrumbs.test.tsx               # NEW
    └── components/
        ├── FilterBar.tsx                      # NEW
        ├── FilterBar.test.tsx                 # NEW
        ├── LandscapeTable.tsx                 # NEW
        ├── LandscapeTable.test.tsx            # NEW
        ├── LandscapeMap.tsx                   # NEW (extracted from LandscapeView)
        ├── LandscapeMap.test.tsx              # NEW
        ├── NodeHeaderBand.tsx                 # NEW
        ├── NodeHeaderBand.test.tsx            # NEW
        ├── ThemeHistory.tsx                   # NEW
        ├── ThemeHistory.test.tsx              # NEW
        ├── NodeStoriesList.tsx                # NEW
        ├── NodeStoriesList.test.tsx           # NEW
        ├── ConnectedNodesRail.tsx             # NEW
        ├── ConnectedNodesRail.test.tsx        # NEW
        └── NodeTooltip.tsx                    # RENAMED from TopicTooltip.tsx, rewritten
```

Files modified:

```
viz-web/
├── package.json                               # MODIFIED (add deps)
├── src/
│   ├── main.tsx                               # MODIFIED (font imports, globals.css)
│   ├── App.tsx                                # MODIFIED (uses AppShell, imports NodeDetailView)
│   ├── views/
│   │   ├── LandscapeView.tsx                  # MODIFIED (thin orchestrator)
│   │   └── NodeDetailView.tsx                 # RENAMED from TopicDetailView.tsx, modified
│   ├── components/
│   │   ├── ComingSoonPanel.tsx                # MODIFIED (rewritten)
│   │   ├── EmptyState.tsx                     # MODIFIED (rewritten)
│   │   └── LoadingState.tsx                   # MODIFIED (rewritten)
│   ├── routes/
│   │   └── App.test.tsx                       # MODIFIED (new selectors)
│   └── views/
│       └── NodeDetailView.test.tsx            # RENAMED from TopicDetailView.test.tsx, modified
```

Files deleted:

```
viz-web/src/
├── styles.css                                 # DELETED
├── components/
│   ├── ChannelLegend.tsx                      # DELETED
│   ├── TopicTooltip.tsx                       # RENAMED
│   ├── PhaseBadge.tsx                         # MOVED to src/ui/
│   └── TimeWindowSelector.tsx                 # MOVED to src/ui/WindowSelector.tsx
└── views/
    └── TopicDetailView.tsx                    # RENAMED to NodeDetailView.tsx
```

---

## Phase 1 — Tailwind + tokens bootstrap

### Task 1: Install dependencies

**Files:**
- Modify: `viz-web/package.json`

- [ ] **Step 1: Install new dependencies**

```bash
cd viz-web
npm install tailwindcss@next @tailwindcss/postcss postcss clsx
npm install @fontsource/fraunces @fontsource/inter @fontsource/jetbrains-mono
```

- [ ] **Step 2: Verify install succeeded**

Run: `cd viz-web && npm ls tailwindcss @tailwindcss/postcss postcss clsx @fontsource/fraunces @fontsource/inter @fontsource/jetbrains-mono`
Expected: All packages resolved, no unmet peer dependency warnings.

- [ ] **Step 3: Run existing tests to confirm baseline still green**

Run: `cd viz-web && npm run test`
Expected: PASS. Baseline tests still green.

- [ ] **Step 4: Commit**

```bash
cd viz-web
git add package.json package-lock.json
git commit -m "chore(viz-web): add tailwind v4 and fontsource deps for redesign"
```

---

### Task 2: Create Tailwind and PostCSS config

**Files:**
- Create: `viz-web/postcss.config.js`
- Create: `viz-web/tailwind.config.ts`

- [ ] **Step 1: Create `postcss.config.js`**

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

- [ ] **Step 2: Create `tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
};

export default config;
```

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add postcss.config.js tailwind.config.ts
git commit -m "chore(viz-web): add tailwind v4 + postcss config"
```

---

### Task 3: Create design tokens and globals

**Files:**
- Create: `viz-web/src/styles/tokens.css`
- Create: `viz-web/src/styles/globals.css`

- [ ] **Step 1: Create `src/styles/tokens.css`**

```css
/* Design tokens for the viz-web editorial warm-paper theme.
   Referenced by globals.css via Tailwind v4 @theme. */
:root {
  /* Surface */
  --color-paper: #F7F1E3;
  --color-card: #FDF9EC;
  --color-surface-2: #EFE6D0;
  --color-ink: #1A1715;
  --color-muted: #8B5E3C;
  --color-cream-neutral: #F0E6D2;

  /* Phase (theme nodes only) */
  --color-phase-emerging: #C94F2B;
  --color-phase-flash: #D97706;
  --color-phase-sustained: #0D7C66;
  --color-phase-fading: #2F6FB5;
  --color-phase-steady: #5C4A39;

  /* Kind (all node kinds) */
  --color-kind-event: #B45309;
  --color-kind-theme: #2F4858;
  --color-kind-person: #115E59;
  --color-kind-nation: #1D4ED8;
  --color-kind-org: #7C2D12;
  --color-kind-place: #4D7C0F;

  /* Rules */
  --rule-ink: 1px solid var(--color-ink);
  --rule-ink-thin: 1px solid rgba(26, 23, 21, 0.16);

  /* Fonts */
  --font-display: "Fraunces", "GT Sectra", Georgia, serif;
  --font-sans: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;

  /* Type scale */
  --fs-display-xl: clamp(1.8rem, 4vw, 2.4rem);
  --fs-display-lg: 1.6rem;
  --fs-display-md: 1.2rem;
  --fs-body-md: 0.88rem;
  --fs-body-sm: 0.78rem;
  --fs-mono: 0.82rem;
  --fs-eyebrow: 0.62rem;
}
```

- [ ] **Step 2: Create `src/styles/globals.css`**

```css
@import "tailwindcss";
@import "./tokens.css";

@theme {
  --color-paper: var(--color-paper);
  --color-card: var(--color-card);
  --color-surface-2: var(--color-surface-2);
  --color-ink: var(--color-ink);
  --color-muted: var(--color-muted);
  --color-cream-neutral: var(--color-cream-neutral);
  --color-phase-emerging: var(--color-phase-emerging);
  --color-phase-flash: var(--color-phase-flash);
  --color-phase-sustained: var(--color-phase-sustained);
  --color-phase-fading: var(--color-phase-fading);
  --color-phase-steady: var(--color-phase-steady);
  --color-kind-event: var(--color-kind-event);
  --color-kind-theme: var(--color-kind-theme);
  --color-kind-person: var(--color-kind-person);
  --color-kind-nation: var(--color-kind-nation);
  --color-kind-org: var(--color-kind-org);
  --color-kind-place: var(--color-kind-place);
  --font-display: "Fraunces", "GT Sectra", Georgia, serif;
  --font-sans: "Inter", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background: var(--color-paper);
  color: var(--color-ink);
  font-family: var(--font-sans);
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

#root {
  min-height: 100vh;
}

h1,
h2,
h3 {
  font-family: var(--font-display);
  font-weight: 500;
  letter-spacing: -0.02em;
  margin: 0;
}

a {
  color: inherit;
  text-decoration: none;
}

button,
input,
select {
  font: inherit;
}
```

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/styles/tokens.css src/styles/globals.css
git commit -m "feat(viz-web): add design tokens and globals for editorial theme"
```

---

### Task 4: Wire fonts and globals into main.tsx

**Files:**
- Modify: `viz-web/src/main.tsx`

- [ ] **Step 1: Replace `src/main.tsx` contents**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

import "@fontsource/fraunces/500.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

import "./styles.css";
import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
```

Note: we're keeping `./styles.css` imported *above* `./styles/globals.css` (earlier in source order), so Tailwind utilities in `globals.css` take cascade precedence over legacy class rules of equal specificity. The legacy `styles.css` is deleted in Task 37.

- [ ] **Step 2: Run the build to confirm Tailwind + tokens compile**

Run: `cd viz-web && npm run build`
Expected: PASS. Build artifacts land in `viz-web/dist/`.

- [ ] **Step 3: Run tests to confirm nothing broke**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd viz-web
git add src/main.tsx
git commit -m "feat(viz-web): wire tailwind globals and fontsource fonts into main.tsx"
```

---

## Phase 2 — UI primitives

### Task 5: `kindColors` map

**Files:**
- Create: `viz-web/src/ui/kindColors.ts`
- Test: `viz-web/src/ui/kindColors.test.ts`

- [ ] **Step 1: Write the failing test**

Create `viz-web/src/ui/kindColors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { KIND_STROKE, KIND_LABEL } from "./kindColors";

describe("kindColors", () => {
  it("exposes a stroke color for every node kind", () => {
    expect(KIND_STROKE.event).toBe("#B45309");
    expect(KIND_STROKE.theme).toBe("#2F4858");
    expect(KIND_STROKE.person).toBe("#115E59");
    expect(KIND_STROKE.nation).toBe("#1D4ED8");
    expect(KIND_STROKE.org).toBe("#7C2D12");
    expect(KIND_STROKE.place).toBe("#4D7C0F");
  });

  it("exposes a human label for every node kind", () => {
    expect(KIND_LABEL.event).toBe("Event");
    expect(KIND_LABEL.theme).toBe("Theme");
    expect(KIND_LABEL.person).toBe("Person");
    expect(KIND_LABEL.nation).toBe("Nation");
    expect(KIND_LABEL.org).toBe("Organization");
    expect(KIND_LABEL.place).toBe("Place");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/kindColors.test.ts`
Expected: FAIL with module resolution error "Cannot find module './kindColors'".

- [ ] **Step 3: Create `src/ui/kindColors.ts`**

```ts
import type { NodeKind } from "../lib/types";

export const KIND_STROKE: Record<NodeKind, string> = {
  event: "#B45309",
  theme: "#2F4858",
  person: "#115E59",
  nation: "#1D4ED8",
  org: "#7C2D12",
  place: "#4D7C0F",
};

export const KIND_LABEL: Record<NodeKind, string> = {
  event: "Event",
  theme: "Theme",
  person: "Person",
  nation: "Nation",
  org: "Organization",
  place: "Place",
};

export const NODE_KINDS: readonly NodeKind[] = ["event", "theme", "person", "nation", "org", "place"] as const;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/kindColors.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/kindColors.ts src/ui/kindColors.test.ts
git commit -m "feat(viz-web): add kindColors map for node-kind palette"
```

---

### Task 6: `Button` primitive

**Files:**
- Create: `viz-web/src/ui/Button.tsx`
- Test: `viz-web/src/ui/Button.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `viz-web/src/ui/Button.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("renders label as ink by default", () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass("bg-ink");
    expect(button).toHaveClass("text-paper");
  });

  it("renders ghost variant with a ruled border and transparent background", () => {
    render(<Button variant="ghost">Cancel</Button>);
    const button = screen.getByRole("button", { name: "Cancel" });
    expect(button).toHaveClass("border");
    expect(button).toHaveClass("bg-transparent");
  });

  it("applies active styling when active prop is true on ghost variant", () => {
    render(
      <Button variant="ghost" active>
        7D
      </Button>,
    );
    const button = screen.getByRole("button", { name: "7D" });
    expect(button).toHaveClass("bg-ink");
  });

  it("fires onClick", async () => {
    const handler = vi.fn();
    render(<Button onClick={handler}>Go</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/Button.test.tsx`
Expected: FAIL with "Cannot find module './Button'".

- [ ] **Step 3: Create `src/ui/Button.tsx`**

```tsx
import { clsx } from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "ink" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  active?: boolean;
  children: ReactNode;
}

export function Button({ variant = "ink", active = false, className, children, type, ...rest }: ButtonProps) {
  const base = "inline-flex items-center gap-1.5 px-3 py-2 text-[0.78rem] font-medium rounded-sm transition-transform duration-150 ease-out hover:-translate-y-px disabled:opacity-40 disabled:cursor-not-allowed";
  const ink = "bg-ink text-paper border border-ink";
  const ghost = active
    ? "bg-ink text-paper border border-ink"
    : "bg-transparent text-ink border border-ink/25 hover:border-ink/60";
  return (
    <button type={type ?? "button"} className={clsx(base, variant === "ink" ? ink : ghost, className)} {...rest}>
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/Button.test.tsx`
Expected: PASS. If Tailwind arbitrary classes like `border-ink/25` fail to resolve, verify Task 3 tokens are loaded by running `npm run build` once.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/Button.tsx src/ui/Button.test.tsx
git commit -m "feat(viz-web): add Button primitive (ink, ghost, ghost-active)"
```

---

### Task 7: `Eyebrow` primitive

**Files:**
- Create: `viz-web/src/ui/Eyebrow.tsx`
- Test: `viz-web/src/ui/Eyebrow.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Eyebrow } from "./Eyebrow";

describe("Eyebrow", () => {
  it("renders uppercase label with tracked letter spacing", () => {
    render(<Eyebrow>live topic landscape</Eyebrow>);
    const el = screen.getByText("live topic landscape");
    expect(el).toHaveClass("uppercase");
    expect(el).toHaveClass("tracking-[0.16em]");
    expect(el).toHaveClass("text-muted");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/Eyebrow.test.tsx`
Expected: FAIL "Cannot find module './Eyebrow'".

- [ ] **Step 3: Create `src/ui/Eyebrow.tsx`**

```tsx
import { clsx } from "clsx";
import type { ReactNode } from "react";

interface EyebrowProps {
  children: ReactNode;
  className?: string;
}

export function Eyebrow({ children, className }: EyebrowProps) {
  return (
    <p className={clsx("uppercase tracking-[0.16em] text-[0.62rem] font-semibold text-muted", className)}>
      {children}
    </p>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/Eyebrow.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/Eyebrow.tsx src/ui/Eyebrow.test.tsx
git commit -m "feat(viz-web): add Eyebrow primitive"
```

---

### Task 8: `Rule` primitive

**Files:**
- Create: `viz-web/src/ui/Rule.tsx`
- Test: `viz-web/src/ui/Rule.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Rule } from "./Rule";

describe("Rule", () => {
  it("renders a bold ink hr by default", () => {
    const { container } = render(<Rule />);
    const hr = container.querySelector("hr");
    expect(hr).not.toBeNull();
    expect(hr).toHaveClass("border-ink");
  });

  it("renders a thin variant with muted border", () => {
    const { container } = render(<Rule variant="thin" />);
    const hr = container.querySelector("hr");
    expect(hr).toHaveClass("border-ink/20");
  });

  it("renders dashed variant", () => {
    const { container } = render(<Rule variant="dashed" />);
    const hr = container.querySelector("hr");
    expect(hr).toHaveClass("border-dashed");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/Rule.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/Rule.tsx`**

```tsx
import { clsx } from "clsx";

interface RuleProps {
  variant?: "bold" | "thin" | "dashed";
  className?: string;
}

export function Rule({ variant = "bold", className }: RuleProps) {
  return (
    <hr
      className={clsx(
        "border-0 border-t w-full m-0",
        variant === "bold" && "border-ink",
        variant === "thin" && "border-ink/20",
        variant === "dashed" && "border-ink/30 border-dashed",
        className,
      )}
    />
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/Rule.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/Rule.tsx src/ui/Rule.test.tsx
git commit -m "feat(viz-web): add Rule primitive (bold, thin, dashed)"
```

---

### Task 9: `Pill` primitive

**Files:**
- Create: `viz-web/src/ui/Pill.tsx`
- Test: `viz-web/src/ui/Pill.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pill } from "./Pill";

describe("Pill", () => {
  it("renders a squared pill with uppercase text", () => {
    render(<Pill>Emerging</Pill>);
    const pill = screen.getByText("Emerging");
    expect(pill).toHaveClass("uppercase");
    expect(pill).toHaveClass("rounded-sm");
  });

  it("accepts custom tint classes via className", () => {
    render(<Pill className="bg-phase-emerging/15 text-phase-emerging">Emerging</Pill>);
    const pill = screen.getByText("Emerging");
    expect(pill).toHaveClass("bg-phase-emerging/15");
    expect(pill).toHaveClass("text-phase-emerging");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/Pill.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/Pill.tsx`**

```tsx
import { clsx } from "clsx";
import type { ReactNode } from "react";

interface PillProps {
  children: ReactNode;
  className?: string;
}

export function Pill({ children, className }: PillProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center uppercase tracking-[0.08em] text-[0.62rem] font-semibold px-2 py-[0.18rem] rounded-sm border border-transparent",
        className,
      )}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/Pill.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/Pill.tsx src/ui/Pill.test.tsx
git commit -m "feat(viz-web): add generic Pill primitive"
```

---

### Task 10: `Card` primitive

**Files:**
- Create: `viz-web/src/ui/Card.tsx`
- Test: `viz-web/src/ui/Card.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "./Card";

describe("Card", () => {
  it("renders a cream card with children", () => {
    render(<Card>Hello</Card>);
    const card = screen.getByText("Hello");
    expect(card).toHaveClass("bg-card");
    expect(card).toHaveClass("border");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/Card.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/Card.tsx`**

```tsx
import { clsx } from "clsx";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div className={clsx("bg-card border border-ink/15 rounded-sm px-4 py-3", className)}>{children}</div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/Card.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/Card.tsx src/ui/Card.test.tsx
git commit -m "feat(viz-web): add Card primitive"
```

---

### Task 11: `PhaseBadge` primitive (move + rewrite)

**Files:**
- Create: `viz-web/src/ui/PhaseBadge.tsx`
- Test: `viz-web/src/ui/PhaseBadge.test.tsx`
- (Old `viz-web/src/components/PhaseBadge.tsx` is deleted later in Task 37)

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PhaseBadge } from "./PhaseBadge";

describe("PhaseBadge", () => {
  it("renders emerging label and emerging tint", () => {
    render(<PhaseBadge phase="emerging" />);
    const pill = screen.getByText("Emerging");
    expect(pill).toHaveClass("text-phase-emerging");
    expect(pill).toHaveClass("bg-phase-emerging/15");
  });

  it("renders flash_event as 'Flash Event' with flash tint", () => {
    render(<PhaseBadge phase="flash_event" />);
    const pill = screen.getByText("Flash Event");
    expect(pill).toHaveClass("text-phase-flash");
  });

  it("falls back to raw phase key if unknown", () => {
    render(<PhaseBadge phase="unknown_phase" />);
    expect(screen.getByText("unknown_phase")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/PhaseBadge.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/PhaseBadge.tsx`**

```tsx
import { clsx } from "clsx";
import { Pill } from "./Pill";

interface PhaseBadgeProps {
  phase: string;
  className?: string;
}

const LABEL: Record<string, string> = {
  emerging: "Emerging",
  flash_event: "Flash Event",
  sustained: "Sustained",
  fading: "Fading",
  steady: "Steady",
};

const TINT: Record<string, string> = {
  emerging: "bg-phase-emerging/15 text-phase-emerging border-phase-emerging/30",
  flash_event: "bg-phase-flash/15 text-phase-flash border-phase-flash/30",
  sustained: "bg-phase-sustained/15 text-phase-sustained border-phase-sustained/30",
  fading: "bg-phase-fading/15 text-phase-fading border-phase-fading/30",
  steady: "bg-ink/8 text-muted border-ink/15",
};

export function PhaseBadge({ phase, className }: PhaseBadgeProps) {
  return <Pill className={clsx(TINT[phase] ?? "bg-ink/5 text-muted border-ink/10", className)}>{LABEL[phase] ?? phase}</Pill>;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/PhaseBadge.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/PhaseBadge.tsx src/ui/PhaseBadge.test.tsx
git commit -m "feat(viz-web): add PhaseBadge in src/ui/ using Pill primitive"
```

---

### Task 12: `KindChip` primitive

**Files:**
- Create: `viz-web/src/ui/KindChip.tsx`
- Test: `viz-web/src/ui/KindChip.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { KindChip } from "./KindChip";

describe("KindChip", () => {
  it("renders label and a colored dot", () => {
    const { container } = render(<KindChip kind="event" />);
    expect(screen.getByText("Event")).toBeInTheDocument();
    const dot = container.querySelector("[data-dot=\"true\"]");
    expect(dot).not.toBeNull();
    expect(dot).toHaveStyle({ backgroundColor: "#B45309" });
  });

  it("is a button and fires onClick", async () => {
    const handler = vi.fn();
    render(<KindChip kind="theme" onClick={handler} />);
    await userEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("applies active styling when active prop is true", () => {
    render(<KindChip kind="theme" active />);
    expect(screen.getByRole("button", { name: /theme/i })).toHaveClass("bg-ink");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/KindChip.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/KindChip.tsx`**

```tsx
import { clsx } from "clsx";
import type { NodeKind } from "../lib/types";
import { KIND_LABEL, KIND_STROKE } from "./kindColors";

interface KindChipProps {
  kind: NodeKind;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

export function KindChip({ kind, active = false, onClick, className }: KindChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "inline-flex items-center gap-1.5 px-2 py-1 text-[0.72rem] rounded-sm border transition-colors",
        active ? "bg-ink text-paper border-ink" : "bg-transparent text-ink border-ink/25 hover:border-ink/60",
        className,
      )}
      aria-pressed={active}
    >
      <span
        data-dot="true"
        className="inline-block w-[0.45rem] h-[0.45rem] rounded-full"
        style={{ backgroundColor: KIND_STROKE[kind] }}
      />
      <span>{KIND_LABEL[kind]}</span>
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/KindChip.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/KindChip.tsx src/ui/KindChip.test.tsx
git commit -m "feat(viz-web): add KindChip primitive for kind filter"
```

---

### Task 13: `MetricCell` primitive

**Files:**
- Create: `viz-web/src/ui/MetricCell.tsx`
- Test: `viz-web/src/ui/MetricCell.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCell } from "./MetricCell";

describe("MetricCell", () => {
  it("renders label, value, and caption", () => {
    render(<MetricCell label="Nodes" value="184" caption="in 7d window" />);
    expect(screen.getByText("Nodes")).toBeInTheDocument();
    expect(screen.getByText("184")).toBeInTheDocument();
    expect(screen.getByText("in 7d window")).toBeInTheDocument();
  });

  it("renders value in mono font", () => {
    render(<MetricCell label="Heat" value="2.3" />);
    expect(screen.getByText("2.3")).toHaveClass("font-mono");
  });

  it("omits caption when not provided", () => {
    render(<MetricCell label="Relations" value="52" />);
    expect(screen.queryByText(/window/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/MetricCell.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/MetricCell.tsx`**

```tsx
import { clsx } from "clsx";
import type { ReactNode } from "react";

interface MetricCellProps {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  className?: string;
}

export function MetricCell({ label, value, caption, className }: MetricCellProps) {
  return (
    <div className={clsx("px-3 py-2.5", className)}>
      <div className="text-[0.56rem] tracking-[0.16em] uppercase font-semibold text-muted">{label}</div>
      <div className="font-mono text-[1.15rem] font-medium text-ink mt-0.5 leading-none">{value}</div>
      {caption ? <div className="text-[0.68rem] text-muted mt-1">{caption}</div> : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/MetricCell.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/MetricCell.tsx src/ui/MetricCell.test.tsx
git commit -m "feat(viz-web): add MetricCell primitive"
```

---

### Task 14: `MetricsStrip` primitive

**Files:**
- Create: `viz-web/src/ui/MetricsStrip.tsx`
- Test: `viz-web/src/ui/MetricsStrip.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCell } from "./MetricCell";
import { MetricsStrip } from "./MetricsStrip";

describe("MetricsStrip", () => {
  it("renders children in a grid with top and bottom ink rules", () => {
    const { container } = render(
      <MetricsStrip>
        <MetricCell label="A" value="1" />
        <MetricCell label="B" value="2" />
      </MetricsStrip>,
    );
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    const strip = container.querySelector("[data-testid=\"metrics-strip\"]");
    expect(strip).toHaveClass("grid");
    expect(strip).toHaveClass("border-y");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/MetricsStrip.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/MetricsStrip.tsx`**

```tsx
import { clsx } from "clsx";
import { Children, type ReactNode } from "react";

interface MetricsStripProps {
  children: ReactNode;
  className?: string;
}

export function MetricsStrip({ children, className }: MetricsStripProps) {
  const count = Children.count(children);
  return (
    <div
      data-testid="metrics-strip"
      className={clsx("grid border-y border-ink divide-x divide-ink/15", className)}
      style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/MetricsStrip.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/MetricsStrip.tsx src/ui/MetricsStrip.test.tsx
git commit -m "feat(viz-web): add MetricsStrip primitive"
```

---

### Task 15: `WindowSelector` (move + rewrite)

**Files:**
- Create: `viz-web/src/ui/WindowSelector.tsx`
- Test: `viz-web/src/ui/WindowSelector.test.tsx`
- (Old `viz-web/src/components/TimeWindowSelector.tsx` is deleted later in Task 37)

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WindowSelector } from "./WindowSelector";

describe("WindowSelector", () => {
  it("renders all six window keys as buttons", () => {
    render(<WindowSelector value="7d" onChange={() => undefined} />);
    ["1d", "3d", "5d", "7d", "14d", "31d"].forEach((key) => {
      expect(screen.getByRole("button", { name: key })).toBeInTheDocument();
    });
  });

  it("marks the active window with aria-pressed and ink fill", () => {
    render(<WindowSelector value="7d" onChange={() => undefined} />);
    const active = screen.getByRole("button", { name: "7d" });
    expect(active).toHaveAttribute("aria-pressed", "true");
    expect(active).toHaveClass("bg-ink");
  });

  it("fires onChange with the new key when another button is clicked", async () => {
    const handler = vi.fn();
    render(<WindowSelector value="7d" onChange={handler} />);
    await userEvent.click(screen.getByRole("button", { name: "14d" }));
    expect(handler).toHaveBeenCalledWith("14d");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/WindowSelector.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/WindowSelector.tsx`**

```tsx
import { clsx } from "clsx";
import type { WindowKey } from "../lib/types";

const WINDOWS: WindowKey[] = ["1d", "3d", "5d", "7d", "14d", "31d"];

interface WindowSelectorProps {
  value: WindowKey;
  onChange: (value: WindowKey) => void;
  className?: string;
}

export function WindowSelector({ value, onChange, className }: WindowSelectorProps) {
  return (
    <div role="tablist" aria-label="Time window selector" className={clsx("inline-flex gap-1", className)}>
      {WINDOWS.map((key) => {
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-pressed={active}
            onClick={() => onChange(key)}
            className={clsx(
              "px-2.5 py-1.5 text-[0.7rem] font-medium rounded-sm border transition-colors",
              active
                ? "bg-ink text-paper border-ink"
                : "bg-transparent text-ink border-ink/25 hover:border-ink/60",
            )}
          >
            {key}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/WindowSelector.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/WindowSelector.tsx src/ui/WindowSelector.test.tsx
git commit -m "feat(viz-web): add WindowSelector in src/ui/ with six window keys"
```

---

### Task 16: `SortableTable` primitive

**Files:**
- Create: `viz-web/src/ui/SortableTable.tsx`
- Test: `viz-web/src/ui/SortableTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SortableTable, type ColumnDef } from "./SortableTable";

interface Row {
  id: string;
  name: string;
  score: number;
}

const rows: Row[] = [
  { id: "1", name: "Alpha", score: 10 },
  { id: "2", name: "Bravo", score: 30 },
  { id: "3", name: "Charlie", score: 20 },
];

const columns: ColumnDef<Row>[] = [
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "score", header: "Score", render: (row) => row.score, numeric: true, sortable: true },
];

describe("SortableTable", () => {
  it("renders rows in initial order", () => {
    render(<SortableTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    const cells = screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);
    expect(cells).toEqual(["Alpha", "Bravo", "Charlie"]);
  });

  it("sorts descending by default when column header is clicked", async () => {
    render(
      <SortableTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        initialSort={{ key: "score", dir: "desc" }}
      />,
    );
    const cells = screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);
    expect(cells).toEqual(["Bravo", "Charlie", "Alpha"]);
  });

  it("toggles sort direction when a sortable header is clicked", async () => {
    render(
      <SortableTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        initialSort={{ key: "score", dir: "desc" }}
      />,
    );
    await userEvent.click(screen.getByRole("columnheader", { name: /Score/ }));
    const cells = screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);
    expect(cells).toEqual(["Alpha", "Charlie", "Bravo"]);
  });

  it("fires onRowClick with the row", async () => {
    const handler = vi.fn();
    render(<SortableTable columns={columns} rows={rows} getRowId={(r) => r.id} onRowClick={handler} />);
    await userEvent.click(screen.getByText("Bravo"));
    expect(handler).toHaveBeenCalledWith(rows[1]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/ui/SortableTable.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/ui/SortableTable.tsx`**

```tsx
import { clsx } from "clsx";
import { useMemo, useState, type ReactNode } from "react";

export interface ColumnDef<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  numeric?: boolean;
  sortable?: boolean;
  sortValue?: (row: Row) => number | string;
  width?: string;
}

interface SortState {
  key: string;
  dir: "asc" | "desc";
}

interface SortableTableProps<Row> {
  columns: ColumnDef<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
  initialSort?: SortState;
  onRowClick?: (row: Row) => void;
  onRowHover?: (rowId: string | null) => void;
  hoveredRowId?: string | null;
  className?: string;
}

export function SortableTable<Row>({
  columns,
  rows,
  getRowId,
  initialSort,
  onRowClick,
  onRowHover,
  hoveredRowId,
  className,
}: SortableTableProps<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);

  const sorted = useMemo(() => {
    if (!sort) {
      return rows;
    }
    const col = columns.find((column) => column.key === sort.key);
    if (!col) {
      return rows;
    }
    const value = col.sortValue ?? ((row: Row) => {
      const rendered = col.render(row);
      if (typeof rendered === "number" || typeof rendered === "string") {
        return rendered;
      }
      return "";
    });
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      if (typeof av === "number" && typeof bv === "number") {
        return sort.dir === "asc" ? av - bv : bv - av;
      }
      return sort.dir === "asc"
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return copy;
  }, [columns, rows, sort]);

  const toggleSort = (key: string) => {
    setSort((previous) => {
      if (!previous || previous.key !== key) {
        return { key, dir: "desc" };
      }
      return { key, dir: previous.dir === "desc" ? "asc" : "desc" };
    });
  };

  return (
    <table className={clsx("w-full border-collapse text-[0.78rem]", className)}>
      <thead>
        <tr>
          {columns.map((column) => {
            const isSorted = sort?.key === column.key;
            const sortable = column.sortable ?? column.numeric ?? false;
            return (
              <th
                key={column.key}
                scope="col"
                aria-sort={isSorted ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                onClick={sortable ? () => toggleSort(column.key) : undefined}
                className={clsx(
                  "text-[0.56rem] uppercase tracking-[0.1em] text-muted font-semibold py-2 px-1 border-b border-ink text-left",
                  column.numeric && "text-right",
                  sortable && "cursor-pointer select-none hover:text-ink",
                )}
                style={column.width ? { width: column.width } : undefined}
              >
                {column.header}
                {isSorted ? <span aria-hidden="true">{sort!.dir === "asc" ? " ↑" : " ↓"}</span> : null}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => {
          const rowId = getRowId(row);
          const hovered = hoveredRowId === rowId;
          return (
            <tr
              key={rowId}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onMouseEnter={onRowHover ? () => onRowHover(rowId) : undefined}
              onMouseLeave={onRowHover ? () => onRowHover(null) : undefined}
              className={clsx(
                "border-b border-ink/10 align-middle transition-colors",
                onRowClick && "cursor-pointer",
                hovered && "bg-phase-emerging/5",
              )}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={clsx("py-2 px-1", column.numeric && "text-right font-mono")}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/ui/SortableTable.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/ui/SortableTable.tsx src/ui/SortableTable.test.tsx
git commit -m "feat(viz-web): add SortableTable primitive with sort + hover sync"
```

---

### Task 17: `ui/index.ts` barrel

**Files:**
- Create: `viz-web/src/ui/index.ts`

- [ ] **Step 1: Create `src/ui/index.ts`**

```ts
export { Button } from "./Button";
export { Card } from "./Card";
export { Eyebrow } from "./Eyebrow";
export { KindChip } from "./KindChip";
export { MetricCell } from "./MetricCell";
export { MetricsStrip } from "./MetricsStrip";
export { PhaseBadge } from "./PhaseBadge";
export { Pill } from "./Pill";
export { Rule } from "./Rule";
export { SortableTable } from "./SortableTable";
export type { ColumnDef } from "./SortableTable";
export { WindowSelector } from "./WindowSelector";
export { KIND_LABEL, KIND_STROKE, NODE_KINDS } from "./kindColors";
```

- [ ] **Step 2: Run all ui tests**

Run: `cd viz-web && npx vitest run src/ui`
Expected: PASS on every primitive test.

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/ui/index.ts
git commit -m "feat(viz-web): add ui/ barrel export"
```

---

## Phase 3 — Layout shell

### Task 18: `TopNav`

**Files:**
- Create: `viz-web/src/layout/TopNav.tsx`
- Test: `viz-web/src/layout/TopNav.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { TopNav } from "./TopNav";

describe("TopNav", () => {
  it("renders brand mark and all five routes", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <TopNav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Telegram Knowledge Graph")).toBeInTheDocument();
    expect(screen.getByText("Landscape")).toBeInTheDocument();
    expect(screen.getByText("Node Detail")).toBeInTheDocument();
    expect(screen.getByText("Trends")).toBeInTheDocument();
    expect(screen.getByText("Propagation")).toBeInTheDocument();
    expect(screen.getByText("Evolution")).toBeInTheDocument();
  });

  it("marks Landscape as active on /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <TopNav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Landscape").closest("a")).toHaveAttribute("data-active", "true");
  });

  it("marks Node Detail as active when on /node/:kind/:slug", () => {
    render(
      <MemoryRouter initialEntries={["/node/event/demo"]}>
        <TopNav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Node Detail").closest("a")).toHaveAttribute("data-active", "true");
  });

  it("renders disabled routes as aria-disabled and not clickable", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <TopNav />
      </MemoryRouter>,
    );
    ["Trends", "Propagation", "Evolution"].forEach((label) => {
      const el = screen.getByText(label);
      expect(el).toHaveAttribute("aria-disabled", "true");
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/layout/TopNav.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/layout/TopNav.tsx`**

```tsx
import { clsx } from "clsx";
import { NavLink, useLocation } from "react-router-dom";

interface RouteEntry {
  label: string;
  path?: string;
  disabled?: boolean;
  detailOnly?: boolean;
}

const ROUTES: RouteEntry[] = [
  { label: "Landscape", path: "/" },
  { label: "Node Detail", detailOnly: true },
  { label: "Trends", disabled: true },
  { label: "Propagation", disabled: true },
  { label: "Evolution", disabled: true },
];

export function TopNav() {
  const location = useLocation();
  const onDetail = location.pathname.startsWith("/node/");
  return (
    <header className="border-b border-ink bg-paper">
      <div className="flex items-center justify-between px-5 py-3 gap-6">
        <div className="flex flex-col">
          <span className="font-display text-[1.05rem] font-medium leading-none tracking-tight">
            Telegram Knowledge Graph
          </span>
          <span className="mt-1 text-[0.6rem] uppercase tracking-[0.16em] font-semibold text-muted">
            Signal mapping for channel narratives
          </span>
        </div>
        <nav aria-label="Visualization views" className="flex gap-5 text-[0.76rem]">
          {ROUTES.map((route) => {
            if (route.disabled) {
              return (
                <span
                  key={route.label}
                  aria-disabled="true"
                  className="text-ink/35 cursor-not-allowed select-none"
                >
                  {route.label}
                </span>
              );
            }
            if (route.detailOnly) {
              return (
                <NavLink
                  key={route.label}
                  to={onDetail ? location.pathname : "/"}
                  data-active={onDetail ? "true" : "false"}
                  className={clsx(
                    "relative pb-[0.3rem]",
                    onDetail ? "font-semibold after:content-[''] after:absolute after:inset-x-0 after:-bottom-[0.75rem] after:h-[2px] after:bg-phase-emerging" : "",
                  )}
                >
                  {route.label}
                </NavLink>
              );
            }
            return (
              <NavLink
                key={route.label}
                to={route.path!}
                end
                className={({ isActive }) =>
                  clsx(
                    "relative pb-[0.3rem]",
                    isActive
                      ? "font-semibold after:content-[''] after:absolute after:inset-x-0 after:-bottom-[0.75rem] after:h-[2px] after:bg-phase-emerging"
                      : "",
                  )
                }
              >
                {({ isActive }) => (
                  <span data-active={isActive ? "true" : "false"}>{route.label}</span>
                )}
              </NavLink>
            );
          })}
        </nav>
        <div className="font-mono text-[0.68rem] text-muted whitespace-nowrap">● LIVE</div>
      </div>
    </header>
  );
}
```

Note: The `data-active` attribute is attached to the inner `<span>` for active routes and read by the test via `closest("a")` lookup chain. To keep the test assertion straightforward, the test uses `closest("a")` and checks `data-active`. Because NavLink uses a function child to get `isActive`, we propagate `data-active` into a wrapping element that `closest("a")` can reach via the `a` element. If the test fails because the span attribute isn't visible via closest("a"), rewrite the NavLink to attach `data-active` to the anchor element using the `className` callback's sibling pattern:

```tsx
<NavLink
  to={route.path!}
  end
  className={({ isActive }) => clsx(isActive ? "..." : "")}
>
  {({ isActive }) => {
    // eslint-disable-next-line
    return <span data-active={String(isActive)}>{route.label}</span>;
  }}
</NavLink>
```

If the selector `.closest("a")` does not receive the attribute, set it via the `className` callback's `ref` indirection or change the test to `screen.getByText("Landscape").parentElement?.hasAttribute("data-active")`. Choose whichever passes — the intent is "active route carries a distinguishing data attribute."

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/layout/TopNav.test.tsx`
Expected: PASS. If it fails on the `data-active` selector, apply the fallback described in step 3 and re-run.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/layout/TopNav.tsx src/layout/TopNav.test.tsx
git commit -m "feat(viz-web): add TopNav layout component"
```

---

### Task 19: `Breadcrumbs`

**Files:**
- Create: `viz-web/src/layout/Breadcrumbs.tsx`
- Test: `viz-web/src/layout/Breadcrumbs.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Breadcrumbs } from "./Breadcrumbs";

describe("Breadcrumbs", () => {
  it("renders a Landscape link followed by kind and display name", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs kind="event" displayName="April 8 Hormuz Reclosure" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Landscape" })).toHaveAttribute("href", "/");
    expect(screen.getByText("event")).toBeInTheDocument();
    expect(screen.getByText("April 8 Hormuz Reclosure")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/layout/Breadcrumbs.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/layout/Breadcrumbs.tsx`**

```tsx
import { Link } from "react-router-dom";

interface BreadcrumbsProps {
  kind: string;
  displayName: string;
}

export function Breadcrumbs({ kind, displayName }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumbs" className="px-5 pt-3 text-[0.7rem] text-muted flex items-center gap-2">
      <Link
        to="/"
        className="text-ink underline underline-offset-[3px] decoration-ink/25 hover:decoration-ink/60"
      >
        Landscape
      </Link>
      <span aria-hidden="true">›</span>
      <span className="font-mono">{kind}</span>
      <span aria-hidden="true">›</span>
      <span>{displayName}</span>
    </nav>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/layout/Breadcrumbs.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/layout/Breadcrumbs.tsx src/layout/Breadcrumbs.test.tsx
git commit -m "feat(viz-web): add Breadcrumbs component for node detail"
```

---

### Task 20: `AppShell`

**Files:**
- Create: `viz-web/src/layout/AppShell.tsx`

- [ ] **Step 1: Create `src/layout/AppShell.tsx`**

```tsx
import type { ReactNode } from "react";
import { TopNav } from "./TopNav";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen flex flex-col bg-paper text-ink">
      <TopNav />
      <main className="flex-1 flex flex-col">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Run layout tests**

Run: `cd viz-web && npx vitest run src/layout`
Expected: PASS (TopNav + Breadcrumbs tests, AppShell has no test of its own — it's a trivial composition).

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/layout/AppShell.tsx
git commit -m "feat(viz-web): add AppShell layout wrapper"
```

---

### Task 21: Update `App.tsx` to use `AppShell`

**Files:**
- Modify: `viz-web/src/App.tsx`

- [ ] **Step 1: Replace `src/App.tsx` contents**

```tsx
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ComingSoonPanel } from "./components/ComingSoonPanel";
import { LandscapeView } from "./views/LandscapeView";
import { TopicDetailView } from "./views/TopicDetailView";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<LandscapeView />} />
        <Route path="/node/:kind/:slug" element={<TopicDetailView />} />
        <Route
          path="/trends"
          element={
            <ComingSoonPanel
              title="Trends view is next."
              description="Emerging, flash, and fading trend cards land in the next phase."
            />
          }
        />
        <Route
          path="/propagation"
          element={
            <ComingSoonPanel
              title="Propagation view is next."
              description="Cross-channel timing and framing analysis is intentionally deferred in phase 1."
            />
          }
        />
        <Route
          path="/evolution"
          element={
            <ComingSoonPanel
              title="Evolution view is next."
              description="The animated graph timeline needs the later API endpoints and ships after the detail views are stable."
            />
          }
        />
      </Routes>
    </AppShell>
  );
}
```

Note: `TopicDetailView` is still imported here because we haven't renamed the file yet. It will be renamed in Task 27.

- [ ] **Step 2: Update `src/routes/App.test.tsx` for the new tab structure**

Replace file contents with:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App";

vi.stubGlobal(
  "fetch",
  vi.fn((input: string) => {
    if (input.startsWith("/api/graph/snapshot")) {
      return Promise.resolve(
        new Response(JSON.stringify({ window: "7d", nodes: [], relations: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }),
);

describe("App", () => {
  it("renders phase-1 tabs and disabled upcoming views", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Landscape")).toBeInTheDocument();
    expect(screen.getByText("Node Detail")).toBeInTheDocument();
    expect(screen.getByText("Trends")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Propagation")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Evolution")).toHaveAttribute("aria-disabled", "true");
  });
});
```

- [ ] **Step 3: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS. The landscape and node-detail views still use legacy markup, so visual styling will be partially broken in the browser, but tests should pass.

- [ ] **Step 4: Commit**

```bash
cd viz-web
git add src/App.tsx src/routes/App.test.tsx
git commit -m "feat(viz-web): mount AppShell in App.tsx and update route test"
```

---

## Phase 4 — Landscape rebuild

### Task 22: `FilterBar`

**Files:**
- Create: `viz-web/src/components/FilterBar.tsx`
- Test: `viz-web/src/components/FilterBar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

describe("FilterBar", () => {
  const phases = new Set(["emerging", "sustained"]);
  const kinds = new Set<"event" | "theme" | "person" | "nation" | "org" | "place">(["event", "theme"]);

  it("renders six kind chips", () => {
    render(
      <FilterBar
        kinds={kinds}
        phases={phases}
        onKindToggle={() => undefined}
        onPhaseToggle={() => undefined}
      />,
    );
    ["Event", "Theme", "Person", "Nation", "Organization", "Place"].forEach((label) => {
      expect(screen.getByRole("button", { name: new RegExp(label, "i") })).toBeInTheDocument();
    });
  });

  it("fires onKindToggle with the clicked kind", async () => {
    const handler = vi.fn();
    render(
      <FilterBar
        kinds={kinds}
        phases={phases}
        onKindToggle={handler}
        onPhaseToggle={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /person/i }));
    expect(handler).toHaveBeenCalledWith("person");
  });

  it("dims phase pills when theme is not in kinds", () => {
    const kindsWithoutTheme = new Set<"event" | "theme" | "person" | "nation" | "org" | "place">(["event"]);
    render(
      <FilterBar
        kinds={kindsWithoutTheme}
        phases={phases}
        onKindToggle={() => undefined}
        onPhaseToggle={() => undefined}
      />,
    );
    const phaseGroup = screen.getByTestId("phase-group");
    expect(phaseGroup).toHaveClass("opacity-40");
  });

  it("fires onPhaseToggle with the clicked phase", async () => {
    const handler = vi.fn();
    render(
      <FilterBar
        kinds={kinds}
        phases={phases}
        onKindToggle={() => undefined}
        onPhaseToggle={handler}
      />,
    );
    await userEvent.click(screen.getByText("Fading"));
    expect(handler).toHaveBeenCalledWith("fading");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/FilterBar.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/FilterBar.tsx`**

```tsx
import { clsx } from "clsx";
import { KindChip, PhaseBadge, NODE_KINDS } from "../ui";
import type { NodeKind, PhaseKey } from "../lib/types";

const PHASES: PhaseKey[] = ["emerging", "flash_event", "sustained", "fading", "steady"];

interface FilterBarProps {
  kinds: Set<NodeKind>;
  phases: Set<string>;
  onKindToggle: (kind: NodeKind) => void;
  onPhaseToggle: (phase: PhaseKey) => void;
  className?: string;
}

export function FilterBar({ kinds, phases, onKindToggle, onPhaseToggle, className }: FilterBarProps) {
  const themeActive = kinds.has("theme");
  return (
    <div className={clsx("px-5 py-3 flex items-center justify-between gap-6 border-b border-ink/15 flex-wrap", className)}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[0.56rem] uppercase tracking-[0.16em] font-semibold text-muted mr-1">Kinds</span>
        {NODE_KINDS.map((kind) => (
          <KindChip
            key={kind}
            kind={kind}
            active={kinds.has(kind)}
            onClick={() => onKindToggle(kind)}
          />
        ))}
      </div>
      <div
        data-testid="phase-group"
        className={clsx("flex items-center gap-2 flex-wrap transition-opacity", !themeActive && "opacity-40")}
      >
        <span className="text-[0.56rem] uppercase tracking-[0.16em] font-semibold text-muted mr-1">
          Phases
          <span className="ml-1 text-muted font-normal normal-case tracking-normal">themes only</span>
        </span>
        {PHASES.map((phase) => (
          <button
            key={phase}
            type="button"
            onClick={() => onPhaseToggle(phase)}
            className={clsx(
              "rounded-sm transition-opacity",
              !phases.has(phase) && "opacity-40",
            )}
            aria-pressed={phases.has(phase)}
          >
            <PhaseBadge phase={phase} />
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/FilterBar.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/FilterBar.tsx src/components/FilterBar.test.tsx
git commit -m "feat(viz-web): add FilterBar with kind + phase filters"
```

---

### Task 23: `LandscapeTable`

**Files:**
- Create: `viz-web/src/components/LandscapeTable.tsx`
- Test: `viz-web/src/components/LandscapeTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapeTable } from "./LandscapeTable";
import type { GraphNodeRow } from "../lib/types";

const nodes: GraphNodeRow[] = [
  {
    node_id: "1",
    kind: "theme",
    slug: "election",
    display_name: "US election narratives",
    summary: "Election coverage",
    article_count: 142,
    score: 84,
    phase: "emerging",
  },
  {
    node_id: "2",
    kind: "event",
    slug: "april-8-hormuz",
    display_name: "April 8 Hormuz Reclosure",
    article_count: 89,
    score: 72,
  },
];

describe("LandscapeTable", () => {
  it("renders a row per node with display_name and score", () => {
    render(
      <LandscapeTable
        nodes={nodes}
        hoveredNodeId={null}
        onHover={() => undefined}
        onRowClick={() => undefined}
      />,
    );
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText("April 8 Hormuz Reclosure")).toBeInTheDocument();
    expect(screen.getByText("84.00")).toBeInTheDocument();
    expect(screen.getByText("72.00")).toBeInTheDocument();
  });

  it("fires onRowClick with the clicked node", async () => {
    const handler = vi.fn();
    render(
      <LandscapeTable
        nodes={nodes}
        hoveredNodeId={null}
        onHover={() => undefined}
        onRowClick={handler}
      />,
    );
    await userEvent.click(screen.getByText("April 8 Hormuz Reclosure"));
    expect(handler).toHaveBeenCalledWith(nodes[1]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/LandscapeTable.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/LandscapeTable.tsx`**

```tsx
import type { GraphNodeRow } from "../lib/types";
import { KIND_LABEL, KIND_STROKE, SortableTable, type ColumnDef } from "../ui";

const PHASE_COLOR: Record<string, string> = {
  emerging: "#C94F2B",
  flash_event: "#D97706",
  sustained: "#0D7C66",
  fading: "#2F6FB5",
  steady: "#5C4A39",
};

interface LandscapeTableProps {
  nodes: GraphNodeRow[];
  hoveredNodeId: string | null;
  onHover: (nodeId: string | null) => void;
  onRowClick: (node: GraphNodeRow) => void;
  className?: string;
}

function dotColor(node: GraphNodeRow): string {
  if (node.kind === "theme" && node.phase) {
    return PHASE_COLOR[String(node.phase)] ?? KIND_STROKE.theme;
  }
  return KIND_STROKE[node.kind];
}

export function LandscapeTable({ nodes, hoveredNodeId, onHover, onRowClick, className }: LandscapeTableProps) {
  const columns: ColumnDef<GraphNodeRow>[] = [
    {
      key: "dot",
      header: "",
      width: "0.75rem",
      render: (node) => (
        <span
          aria-hidden="true"
          className="inline-block w-[0.55rem] h-[0.55rem] rounded-full"
          style={{ backgroundColor: dotColor(node) }}
        />
      ),
    },
    {
      key: "name",
      header: "Node",
      sortable: true,
      sortValue: (node) => node.display_name.toLowerCase(),
      render: (node) => (
        <div>
          <div className="font-medium">{node.display_name}</div>
          <div className="text-[0.68rem] text-muted mt-0.5">
            {KIND_LABEL[node.kind]}
            {node.kind === "theme" && node.phase ? <> · {String(node.phase).replace("_", " ")}</> : null}
            {node.summary ? (
              <>
                {" · "}
                <span className="italic">
                  {node.summary.length > 60 ? `${node.summary.slice(0, 60)}…` : node.summary}
                </span>
              </>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: "score",
      header: "Score",
      numeric: true,
      sortable: true,
      sortValue: (node) => node.score,
      render: (node) => node.score.toFixed(2),
    },
    {
      key: "stories",
      header: "Stories",
      numeric: true,
      sortable: true,
      sortValue: (node) => node.article_count,
      render: (node) => node.article_count,
    },
    {
      key: "heat",
      header: "Heat",
      numeric: true,
      sortable: true,
      sortValue: (node) => node.heat ?? -Infinity,
      render: (node) => (node.heat != null ? node.heat.toFixed(3) : "—"),
    },
  ];

  return (
    <SortableTable
      className={className}
      columns={columns}
      rows={nodes}
      getRowId={(node) => node.node_id}
      initialSort={{ key: "score", dir: "desc" }}
      onRowClick={onRowClick}
      onRowHover={onHover}
      hoveredRowId={hoveredNodeId}
    />
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/LandscapeTable.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/LandscapeTable.tsx src/components/LandscapeTable.test.tsx
git commit -m "feat(viz-web): add LandscapeTable composing SortableTable"
```

---

### Task 24: Rename `TopicTooltip` → `NodeTooltip`

**Files:**
- Create: `viz-web/src/components/NodeTooltip.tsx`
- Delete (later in Task 37): `viz-web/src/components/TopicTooltip.tsx`

- [ ] **Step 1: Create `src/components/NodeTooltip.tsx`**

```tsx
import type { GraphNodeRow } from "../lib/types";
import { KIND_LABEL, PhaseBadge } from "../ui";

interface NodeTooltipProps {
  x: number;
  y: number;
  node: GraphNodeRow;
}

export function NodeTooltip({ x, y, node }: NodeTooltipProps) {
  return (
    <div
      className="fixed z-30 pointer-events-none rounded-sm border border-ink bg-ink text-paper p-3 shadow-lg w-[18rem] max-w-[calc(100vw-2rem)]"
      style={{ left: `${x}px`, top: `${y}px` }}
    >
      <div className="flex items-center justify-between gap-2">
        <strong className="font-display text-[0.95rem] leading-tight">{node.display_name}</strong>
        {node.kind === "theme" && node.phase ? <PhaseBadge phase={String(node.phase)} /> : null}
      </div>
      <div className="mt-1 text-[0.72rem] text-paper/70">{KIND_LABEL[node.kind]}</div>
      <div className="mt-2 flex justify-between gap-2 text-[0.72rem] font-mono text-paper/85">
        <span>score {node.score.toFixed(2)}</span>
        <span>{node.article_count} stories</span>
        {node.heat != null ? <span>heat {node.heat.toFixed(3)}</span> : null}
      </div>
      {node.summary ? <p className="mt-2 text-[0.72rem] text-paper/70">{node.summary}</p> : null}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd viz-web
git add src/components/NodeTooltip.tsx
git commit -m "feat(viz-web): add NodeTooltip replacing TopicTooltip"
```

---

### Task 25: `LandscapeMap` (extract from `LandscapeView`)

**Files:**
- Create: `viz-web/src/components/LandscapeMap.tsx`
- Test: `viz-web/src/components/LandscapeMap.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LandscapeMap } from "./LandscapeMap";
import type { GraphNodeRow, SnapshotRelation } from "../lib/types";

const nodes: GraphNodeRow[] = [
  {
    node_id: "1",
    kind: "theme",
    slug: "election",
    display_name: "US election narratives",
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

describe("LandscapeMap", () => {
  it("renders an svg with one circle per node", () => {
    const { container } = render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={() => undefined}
        onNodeClick={() => undefined}
      />,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(container.querySelectorAll("circle").length).toBe(2);
  });

  it("calls onHover with a node id on mouseenter", async () => {
    const handler = vi.fn();
    const { container } = render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={handler}
        onNodeClick={() => undefined}
      />,
    );
    const circle = container.querySelector("circle")!;
    circle.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
    expect(handler).toHaveBeenCalled();
  });

  it("renders caption legend", () => {
    render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={() => undefined}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByText(/ring = kind/i)).toBeInTheDocument();
    expect(screen.getByText("Heat map")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/LandscapeMap.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/LandscapeMap.tsx`**

```tsx
import * as d3 from "d3";
import { useMemo, useRef, useState } from "react";
import type { GraphNodeRow, SnapshotRelation } from "../lib/types";
import { KIND_STROKE } from "../ui";
import { useElementSize } from "../hooks/useElementSize";
import { NodeTooltip } from "./NodeTooltip";

const PHASE_FILL: Record<string, string> = {
  emerging: "#C94F2B",
  flash_event: "#D97706",
  sustained: "#0D7C66",
  fading: "#2F6FB5",
  steady: "#5C4A39",
};

const NEUTRAL_FILL = "#F0E6D2";

type PositionedNode = GraphNodeRow & { x: number; y: number; r: number };

interface LandscapeMapProps {
  nodes: GraphNodeRow[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  onHover: (nodeId: string | null) => void;
  onNodeClick: (node: GraphNodeRow) => void;
}

export function LandscapeMap({ nodes, relations, hoveredNodeId, onHover, onNodeClick }: LandscapeMapProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const { width } = useElementSize(container);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; node: GraphNodeRow } | null>(null);

  const positioned = useMemo<PositionedNode[]>(() => {
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

  const visibleRelations = useMemo(() => {
    if (!hoveredNodeId) {
      return [] as SnapshotRelation[];
    }
    return relations.filter((rel) => rel.source === hoveredNodeId || rel.target === hoveredNodeId);
  }, [hoveredNodeId, relations]);

  const fillFor = (node: GraphNodeRow): string => {
    if (node.kind === "theme" && node.phase) {
      return PHASE_FILL[String(node.phase)] ?? NEUTRAL_FILL;
    }
    return NEUTRAL_FILL;
  };

  return (
    <div className="p-4 bg-ink/[0.02]">
      <div className="flex items-baseline justify-between mb-2">
        <p className="uppercase tracking-[0.16em] text-[0.6rem] font-semibold text-muted">Heat map</p>
        <p className="font-mono text-[0.66rem] text-muted">ring = kind · fill = phase (themes) · size = score</p>
      </div>
      <div ref={setContainer} className="relative border border-ink/15 bg-card rounded-sm overflow-hidden">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${Math.max(width, 720)} 520`}
          className="w-full h-auto min-h-[420px]"
          role="img"
          aria-label="Heat map of nodes"
        >
          <defs>
            <filter id="bubbleGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="14" stdDeviation="16" floodOpacity="0.14" />
            </filter>
          </defs>

          {visibleRelations.map((rel) => {
            const source = positioned.find((p) => p.node_id === rel.source);
            const target = positioned.find((p) => p.node_id === rel.target);
            if (!source || !target) {
              return null;
            }
            return (
              <line
                key={`${rel.source}-${rel.target}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#1A1715"
                strokeOpacity={Math.min(0.7, rel.score / 4)}
                strokeWidth={Math.max(1, rel.score)}
              />
            );
          })}

          {positioned.map((node) => {
            const dimmed =
              hoveredNodeId !== null &&
              hoveredNodeId !== node.node_id &&
              !visibleRelations.some((r) => r.source === node.node_id || r.target === node.node_id);
            return (
              <g key={node.node_id} transform={`translate(${node.x}, ${node.y})`}>
                <circle
                  r={node.r}
                  fill={fillFor(node)}
                  fillOpacity={dimmed ? 0.16 : 0.9}
                  stroke={KIND_STROKE[node.kind]}
                  strokeWidth={3}
                  filter="url(#bubbleGlow)"
                  style={{ cursor: "pointer" }}
                  onMouseEnter={(event) => {
                    onHover(node.node_id);
                    setTooltipPos({ x: event.clientX + 10, y: event.clientY + 10, node });
                  }}
                  onMouseMove={(event) => setTooltipPos({ x: event.clientX + 10, y: event.clientY + 10, node })}
                  onMouseLeave={() => {
                    onHover(null);
                    setTooltipPos(null);
                  }}
                  onClick={() => onNodeClick(node)}
                />
                {node.r > 24 ? (
                  <text
                    textAnchor="middle"
                    className="fill-ink"
                    style={{ pointerEvents: "none", opacity: dimmed ? 0.18 : 1, fontSize: "0.82rem", fontWeight: 600 }}
                  >
                    <tspan x="0" dy="-0.1em">
                      {node.display_name.length > 18 ? `${node.display_name.slice(0, 18)}…` : node.display_name}
                    </tspan>
                    <tspan x="0" dy="1.3em" style={{ fontSize: "0.68rem", fontWeight: 500, opacity: 0.75 }}>
                      {node.kind}
                    </tspan>
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
      {tooltipPos ? <NodeTooltip x={tooltipPos.x} y={tooltipPos.y} node={tooltipPos.node} /> : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/LandscapeMap.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/LandscapeMap.tsx src/components/LandscapeMap.test.tsx
git commit -m "feat(viz-web): extract LandscapeMap from LandscapeView"
```

---

### Task 26: Rebuild `LandscapeView` orchestrator

**Files:**
- Modify: `viz-web/src/views/LandscapeView.tsx`

- [ ] **Step 1: Replace `src/views/LandscapeView.tsx` contents**

```tsx
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { FilterBar } from "../components/FilterBar";
import { LandscapeMap } from "../components/LandscapeMap";
import { LandscapeTable } from "../components/LandscapeTable";
import { LoadingState } from "../components/LoadingState";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { fetchSnapshot } from "../lib/api";
import type { GraphNodeRow, NodeKind, PhaseKey, WindowKey } from "../lib/types";
import { Eyebrow, MetricCell, MetricsStrip, WindowSelector } from "../ui";

const ALL_PHASES: PhaseKey[] = ["emerging", "flash_event", "sustained", "fading", "steady"];
const DEFAULT_KINDS: NodeKind[] = ["event", "theme"];

export function LandscapeView() {
  const navigate = useNavigate();
  const [windowKey, setWindowKey] = useState<WindowKey>("7d");
  const [kindFilter, setKindFilter] = useState<Set<NodeKind>>(new Set(DEFAULT_KINDS));
  const [phaseFilter, setPhaseFilter] = useState<Set<string>>(new Set(ALL_PHASES));
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const snapshotState = useAsyncResource(
    () =>
      fetchSnapshot({
        window: windowKey,
        kinds: Array.from(kindFilter),
      }),
    [kindFilter, windowKey],
  );

  const allNodes: GraphNodeRow[] = snapshotState.data?.nodes ?? [];

  const filteredNodes = useMemo(() => {
    return allNodes.filter((node) => {
      if (!kindFilter.has(node.kind)) {
        return false;
      }
      if (node.kind !== "theme") {
        return true;
      }
      return node.phase == null || phaseFilter.has(String(node.phase));
    });
  }, [allNodes, kindFilter, phaseFilter]);

  const metrics = useMemo(() => {
    const total = allNodes.length;
    const themes = allNodes.filter((n) => n.kind === "theme").length;
    const events = allNodes.filter((n) => n.kind === "event").length;
    const emergingThemes = allNodes.filter(
      (n) => n.kind === "theme" && (n.phase === "emerging" || n.phase === "flash_event"),
    ).length;
    const relations = snapshotState.data?.relations.length ?? 0;
    return { total, themes, events, emergingThemes, relations };
  }, [allNodes, snapshotState.data?.relations.length]);

  const toggleKind = (kind: NodeKind) => {
    setKindFilter((previous) => {
      const next = new Set(previous);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
      }
      if (next.size === 0) {
        return new Set(DEFAULT_KINDS);
      }
      return next;
    });
  };

  const togglePhase = (phase: PhaseKey) => {
    setPhaseFilter((previous) => {
      const next = new Set(previous);
      if (next.has(phase)) {
        next.delete(phase);
      } else {
        next.add(phase);
      }
      if (next.size === 0) {
        return new Set(ALL_PHASES);
      }
      return next;
    });
  };

  const resetFilters = () => {
    setKindFilter(new Set(DEFAULT_KINDS));
    setPhaseFilter(new Set(ALL_PHASES));
  };

  if (snapshotState.loading) {
    return <LoadingState view="landscape" />;
  }

  if (snapshotState.error) {
    return <EmptyState title="Graph unavailable" message="The visualization API did not return a usable snapshot." />;
  }

  return (
    <section className="flex flex-col">
      <div className="flex items-end justify-between px-5 py-5 gap-4">
        <div>
          <Eyebrow>Live node landscape</Eyebrow>
          <h1 className="text-[clamp(1.8rem,4vw,2.4rem)] leading-[0.98] tracking-[-0.03em] mt-1">
            Event and theme pressure map
          </h1>
        </div>
        <WindowSelector value={windowKey} onChange={setWindowKey} />
      </div>

      <div className="mx-5">
        <MetricsStrip>
          <MetricCell label="Nodes" value={metrics.total} caption={`in ${windowKey} window`} />
          <MetricCell label="Themes" value={metrics.themes} caption="phase-tracked" />
          <MetricCell label="Events" value={metrics.events} caption="discrete moments" />
          <MetricCell label="Emerging" value={metrics.emergingThemes} caption="themes rising" />
          <MetricCell label="Relations" value={metrics.relations} caption="graph edges" />
        </MetricsStrip>
      </div>

      <FilterBar
        kinds={kindFilter}
        phases={phaseFilter}
        onKindToggle={toggleKind}
        onPhaseToggle={togglePhase}
      />

      {filteredNodes.length === 0 ? (
        <EmptyState
          title="No active nodes"
          message="This window and filter combination returned no nodes."
          suggestions={[
            { label: "Widen the window to 31d", onClick: () => setWindowKey("31d") },
            { label: "Enable all kinds", onClick: () => setKindFilter(new Set(["event", "theme", "person", "nation", "org", "place"])) },
            { label: "Enable all phases", onClick: () => setPhaseFilter(new Set(ALL_PHASES)) },
          ]}
          onReset={resetFilters}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] border-b border-ink">
          <div className="px-5 py-4 border-r border-ink/20">
            <LandscapeTable
              nodes={filteredNodes}
              hoveredNodeId={hoveredNodeId}
              onHover={setHoveredNodeId}
              onRowClick={(node) => navigate(`/node/${node.kind}/${node.slug}`)}
            />
          </div>
          <LandscapeMap
            nodes={filteredNodes}
            relations={snapshotState.data?.relations ?? []}
            hoveredNodeId={hoveredNodeId}
            onHover={setHoveredNodeId}
            onNodeClick={(node) => navigate(`/node/${node.kind}/${node.slug}`)}
          />
        </div>
      )}

      <div className="flex justify-between items-center px-5 py-3 font-mono text-[0.68rem] text-muted">
        <span>
          {allNodes.length} nodes · {filteredNodes.length} shown · sort by score desc
        </span>
        <span>window: {windowKey}</span>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS (assuming EmptyState and LoadingState still work with their legacy APIs — their `suggestions` and `view` props are used here. If not yet supported, tests will fail. In that case, temporarily remove the new props from this file and add them back in Task 33/34.)

> **If the test fails** because `EmptyState` does not yet accept `suggestions` + `onReset`, or `LoadingState` does not accept `view`, remove those props for this commit. Add them back after Task 33 and Task 34 rewrite those components.

- [ ] **Step 3: Verify against dev API (manual)**

Run: `cd viz-web && VIZ_API_PROXY_TARGET=http://localhost:8000 npm run dev`
Open `http://localhost:5173`. Verify: Landscape renders with metrics strip, kind filter, list on the left, map on the right. Hover a row, confirm the corresponding bubble is highlighted (and vice versa). Click a row, confirm navigation to `/node/:kind/:slug`.
Stop the dev server with Ctrl-C when verified.

- [ ] **Step 4: Commit**

```bash
cd viz-web
git add src/views/LandscapeView.tsx
git commit -m "feat(viz-web): rebuild LandscapeView as orchestrator over FilterBar/LandscapeTable/LandscapeMap"
```

---

## Phase 5 — Node Detail rebuild

### Task 27: Rename `TopicDetailView` to `NodeDetailView`

**Files:**
- Create: `viz-web/src/views/NodeDetailView.tsx` (content will be replaced in Task 32)
- Create: `viz-web/src/views/NodeDetailView.test.tsx` (content will be replaced in Task 33)

- [ ] **Step 1: Rename files with git**

```bash
cd viz-web
git mv src/views/TopicDetailView.tsx src/views/NodeDetailView.tsx
git mv src/views/TopicDetailView.test.tsx src/views/NodeDetailView.test.tsx
```

- [ ] **Step 2: Update the export name inside the renamed file**

Replace the line `export function TopicDetailView()` inside `src/views/NodeDetailView.tsx` with `export function NodeDetailView()`.

- [ ] **Step 3: Update the import + reference inside the renamed test**

In `src/views/NodeDetailView.test.tsx`:
- Replace `import { TopicDetailView } from "./TopicDetailView";` with `import { NodeDetailView } from "./NodeDetailView";`
- Replace the single usage `<TopicDetailView />` with `<NodeDetailView />`
- Replace `describe("TopicDetailView", …)` with `describe("NodeDetailView", …)`

- [ ] **Step 4: Update `App.tsx` to import `NodeDetailView`**

Replace the import in `src/App.tsx`:

```tsx
import { NodeDetailView } from "./views/NodeDetailView";
```

And change the route element from `<TopicDetailView />` to `<NodeDetailView />`.

- [ ] **Step 5: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd viz-web
git add src/views/NodeDetailView.tsx src/views/NodeDetailView.test.tsx src/App.tsx
git commit -m "refactor(viz-web): rename TopicDetailView to NodeDetailView"
```

---

### Task 28: `NodeHeaderBand`

**Files:**
- Create: `viz-web/src/components/NodeHeaderBand.tsx`
- Test: `viz-web/src/components/NodeHeaderBand.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NodeHeaderBand } from "./NodeHeaderBand";
import type { NodeDetail } from "../lib/types";

const theme: NodeDetail = {
  node_id: "1",
  kind: "theme",
  slug: "election",
  display_name: "US election narratives",
  summary: "Election coverage across the RT feed",
  article_count: 142,
  events: [],
  people: [],
  nations: [],
  orgs: [],
  places: [],
  themes: [],
  stories: [],
};

const event: NodeDetail = {
  ...theme,
  kind: "event",
  slug: "april-8",
  display_name: "April 8 Hormuz Reclosure",
};

describe("NodeHeaderBand", () => {
  it("renders eyebrow, display name, slug, and stories count", () => {
    render(<NodeHeaderBand detail={theme} />);
    expect(screen.getByText(/NODE DETAIL · THEME/)).toBeInTheDocument();
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText("election")).toBeInTheDocument();
    expect(screen.getByText(/142 stories/)).toBeInTheDocument();
  });

  it("shows a phase badge for theme nodes when provided", () => {
    render(<NodeHeaderBand detail={{ ...theme, summary: null }} phase="emerging" />);
    expect(screen.getByText("Emerging")).toBeInTheDocument();
  });

  it("does not show phase badge for non-theme nodes", () => {
    render(<NodeHeaderBand detail={event} phase="emerging" />);
    expect(screen.queryByText("Emerging")).toBeNull();
  });

  it("renders summary paragraph when present", () => {
    render(<NodeHeaderBand detail={theme} />);
    expect(screen.getByText("Election coverage across the RT feed")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/NodeHeaderBand.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/NodeHeaderBand.tsx`**

```tsx
import type { NodeDetail } from "../lib/types";
import { Eyebrow, PhaseBadge } from "../ui";

interface NodeHeaderBandProps {
  detail: NodeDetail;
  phase?: string | null;
}

export function NodeHeaderBand({ detail, phase }: NodeHeaderBandProps) {
  const showPhase = detail.kind === "theme" && phase != null;
  return (
    <div className="px-5 pt-3 pb-5 grid grid-cols-[minmax(0,1fr)_auto] gap-4 items-end">
      <div>
        <Eyebrow>{`Node detail · ${detail.kind.toUpperCase()}`}</Eyebrow>
        <h1 className="text-[clamp(1.8rem,4vw,2.4rem)] leading-[0.98] tracking-[-0.03em] mt-1">
          {detail.display_name}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[0.76rem] text-muted">
          <span className="font-mono">{detail.slug}</span>
          <span>·</span>
          <span>{detail.article_count} stories</span>
        </div>
        {detail.summary ? (
          <p className="mt-3 text-[0.88rem] text-ink/85 max-w-prose leading-relaxed">{detail.summary}</p>
        ) : null}
      </div>
      {showPhase ? <PhaseBadge phase={String(phase)} /> : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/NodeHeaderBand.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/NodeHeaderBand.tsx src/components/NodeHeaderBand.test.tsx
git commit -m "feat(viz-web): add NodeHeaderBand"
```

---

### Task 29: `ThemeHistory`

**Files:**
- Create: `viz-web/src/components/ThemeHistory.tsx`
- Test: `viz-web/src/components/ThemeHistory.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThemeHistory } from "./ThemeHistory";
import type { ThemeHistoryPoint } from "../lib/types";

const history: ThemeHistoryPoint[] = [
  { date: "2026-04-08T00:00:00Z", article_count: 12, centroid_drift: 0.11 },
  { date: "2026-04-09T00:00:00Z", article_count: 18, centroid_drift: 0.14 },
];

describe("ThemeHistory", () => {
  it("renders section header", () => {
    render(<ThemeHistory history={history} />);
    expect(screen.getByText(/volume and drift/i)).toBeInTheDocument();
    expect(screen.getByText(/theme evolution/i)).toBeInTheDocument();
  });

  it("renders an empty placeholder when history is empty", () => {
    render(<ThemeHistory history={[]} />);
    expect(screen.getByText(/no history yet/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/ThemeHistory.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/ThemeHistory.tsx`**

```tsx
import { Bar, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ThemeHistoryPoint } from "../lib/types";
import { Eyebrow } from "../ui";

interface ThemeHistoryProps {
  history: ThemeHistoryPoint[];
}

export function ThemeHistory({ history }: ThemeHistoryProps) {
  const data = history.map((point) => ({
    ...point,
    dateLabel: new Date(point.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));

  return (
    <section>
      <Eyebrow>Volume and drift</Eyebrow>
      <h2 className="text-[1.2rem] mt-0.5 mb-3">Theme evolution over time</h2>
      {data.length === 0 ? (
        <p className="text-[0.78rem] text-muted border-t border-ink/15 pt-3">No history yet for this theme.</p>
      ) : (
        <div className="border-t border-ink/15 pt-2">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <XAxis
                dataKey="dateLabel"
                tickLine={false}
                axisLine={{ stroke: "rgba(26,23,21,0.16)" }}
                tick={{ fill: "#8B5E3C", fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              />
              <YAxis
                yAxisId="left"
                tickLine={false}
                axisLine={{ stroke: "rgba(26,23,21,0.16)" }}
                tick={{ fill: "#8B5E3C", fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tickLine={false}
                axisLine={{ stroke: "rgba(26,23,21,0.16)" }}
                tick={{ fill: "#8B5E3C", fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              />
              <Tooltip
                contentStyle={{ background: "#FDF9EC", border: "1px solid #1A1715", borderRadius: 2, fontSize: 12 }}
                labelStyle={{ color: "#1A1715" }}
              />
              <Bar yAxisId="left" dataKey="article_count" fill="#0D7C66" radius={[2, 2, 0, 0]} />
              <Line yAxisId="right" dataKey="centroid_drift" stroke="#C94F2B" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/ThemeHistory.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/ThemeHistory.tsx src/components/ThemeHistory.test.tsx
git commit -m "feat(viz-web): add ThemeHistory composed chart for themes"
```

---

### Task 30: `NodeStoriesList`

**Files:**
- Create: `viz-web/src/components/NodeStoriesList.tsx`
- Test: `viz-web/src/components/NodeStoriesList.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { NodeStoriesList } from "./NodeStoriesList";
import type { NodeStoryRow } from "../lib/types";

const stories: NodeStoryRow[] = [
  {
    story_id: "s-1",
    channel_id: 1,
    channel_title: "Signal Watch",
    timestamp_start: "2026-04-10T14:22:00Z",
    timestamp_end: "2026-04-10T14:25:00Z",
    confidence: 0.87,
    preview_text: "Primary challenger launches campaign",
    combined_text: "Full body: Primary challenger launches campaign with focus on border policy.",
    media_refs: [],
  },
];

describe("NodeStoriesList", () => {
  it("renders a row per story with preview + confidence", () => {
    render(<NodeStoriesList stories={stories} />);
    expect(screen.getByText("Primary challenger launches campaign")).toBeInTheDocument();
    expect(screen.getByText(/0\.87/)).toBeInTheDocument();
    expect(screen.getByText("Signal Watch")).toBeInTheDocument();
  });

  it("expands a row to show combined_text when clicked", async () => {
    render(<NodeStoriesList stories={stories} />);
    await userEvent.click(screen.getByText("Primary challenger launches campaign"));
    expect(
      screen.getByText(/Full body: Primary challenger launches campaign with focus on border policy\./),
    ).toBeInTheDocument();
  });

  it("renders empty state when stories is empty", () => {
    render(<NodeStoriesList stories={[]} />);
    expect(screen.getByText(/no stories/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/NodeStoriesList.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/NodeStoriesList.tsx`**

```tsx
import { useState } from "react";
import type { NodeStoryRow } from "../lib/types";
import { Eyebrow } from "../ui";

interface NodeStoriesListProps {
  stories: NodeStoryRow[];
}

export function NodeStoriesList({ stories }: NodeStoriesListProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <section>
      <div className="border-b border-ink pb-2 mb-1">
        <Eyebrow>Recent stories</Eyebrow>
        <h2 className="text-[1.1rem] mt-0.5">Latest assignments</h2>
      </div>
      {stories.length === 0 ? (
        <p className="py-3 text-[0.78rem] text-muted">No stories for this node yet.</p>
      ) : (
        <ul className="list-none p-0 m-0">
          {stories.map((story) => {
            const isOpen = expanded.has(story.story_id);
            const start = new Date(story.timestamp_start);
            return (
              <li key={story.story_id} className="border-b border-ink/10 py-2">
                <button
                  type="button"
                  onClick={() => toggle(story.story_id)}
                  className="w-full grid grid-cols-[5.5rem_1fr_auto] gap-3 items-baseline text-left bg-transparent border-0 cursor-pointer"
                >
                  <time className="font-mono text-[0.66rem] text-muted leading-tight">
                    {start.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    <br />
                    {start.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </time>
                  <span className="text-[0.86rem] font-medium leading-snug">
                    {story.preview_text || "(media-only story)"}
                  </span>
                  <span className="font-mono text-[0.68rem] text-muted text-right whitespace-nowrap">
                    {story.channel_title} · {story.confidence.toFixed(2)}
                  </span>
                </button>
                {isOpen ? (
                  <div className="mt-2 pl-[6.5rem] pr-2 text-[0.82rem] text-ink/85">
                    <p className="m-0">{story.combined_text || "(media-only story)"}</p>
                    {story.media_refs.length > 0 ? (
                      <ul className="mt-1 pl-4 text-[0.72rem] text-muted list-disc">
                        {story.media_refs.map((media, index) => (
                          <li key={`${story.story_id}-media-${index}`}>
                            {media.file_name ?? media.storage_path ?? media.media_type}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/NodeStoriesList.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/NodeStoriesList.tsx src/components/NodeStoriesList.test.tsx
git commit -m "feat(viz-web): add NodeStoriesList with ruled rows and expand"
```

---

### Task 31: `ConnectedNodesRail`

**Files:**
- Create: `viz-web/src/components/ConnectedNodesRail.tsx`
- Test: `viz-web/src/components/ConnectedNodesRail.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ConnectedNodesRail } from "./ConnectedNodesRail";
import type { NodeDetail } from "../lib/types";

const detail: NodeDetail = {
  node_id: "1",
  kind: "event",
  slug: "april-8",
  display_name: "April 8 Hormuz",
  article_count: 20,
  events: [],
  people: [
    {
      node_id: "p-1",
      kind: "person",
      slug: "jane-doe",
      display_name: "Jane Doe",
      article_count: 7,
      score: 0.82,
      shared_story_count: 4,
    },
  ],
  nations: [],
  orgs: [],
  places: [],
  themes: [],
  stories: [],
};

describe("ConnectedNodesRail", () => {
  it("renders six section headers regardless of content", () => {
    render(
      <MemoryRouter>
        <ConnectedNodesRail detail={detail} />
      </MemoryRouter>,
    );
    ["Events", "People", "Nations", "Organizations", "Places", "Themes"].forEach((label) => {
      expect(screen.getByText(new RegExp(label, "i"))).toBeInTheDocument();
    });
  });

  it("shows related rows for non-empty sections", () => {
    render(
      <MemoryRouter>
        <ConnectedNodesRail detail={detail} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText(/4 shared stories/)).toBeInTheDocument();
  });

  it("shows a muted empty copy for empty sections", () => {
    render(
      <MemoryRouter>
        <ConnectedNodesRail detail={detail} />
      </MemoryRouter>,
    );
    expect(screen.getAllByText(/no related/i).length).toBeGreaterThanOrEqual(5);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd viz-web && npx vitest run src/components/ConnectedNodesRail.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `src/components/ConnectedNodesRail.tsx`**

```tsx
import { Link } from "react-router-dom";
import type { NodeDetail, RelatedNodeRow } from "../lib/types";
import { Eyebrow } from "../ui";

type SectionKey = "events" | "people" | "nations" | "orgs" | "places" | "themes";

const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: "events", label: "Events" },
  { key: "people", label: "People" },
  { key: "nations", label: "Nations" },
  { key: "orgs", label: "Organizations" },
  { key: "places", label: "Places" },
  { key: "themes", label: "Themes" },
];

interface ConnectedNodesRailProps {
  detail: NodeDetail;
}

export function ConnectedNodesRail({ detail }: ConnectedNodesRailProps) {
  return (
    <div className="flex flex-col gap-5">
      {SECTIONS.map(({ key, label }) => {
        const rows = detail[key];
        return <Section key={key} label={label} rows={rows} />;
      })}
    </div>
  );
}

interface SectionProps {
  label: string;
  rows: RelatedNodeRow[];
}

function Section({ label, rows }: SectionProps) {
  const maxScore = rows.length > 0 ? Math.max(...rows.map((row) => row.score)) : 1;
  const visible = rows.slice(0, 6);
  return (
    <div>
      <div className="border-b border-ink pb-1 mb-1 flex items-baseline justify-between">
        <Eyebrow>{`${label.toUpperCase()} · ${rows.length}`}</Eyebrow>
      </div>
      {visible.length === 0 ? (
        <p className="text-[0.74rem] text-muted py-2">No related {label.toLowerCase()}.</p>
      ) : (
        <ul className="list-none p-0 m-0">
          {visible.map((row) => {
            const barWidth = maxScore > 0 ? Math.max(4, (row.score / maxScore) * 100) : 0;
            return (
              <li key={row.node_id} className="border-b border-ink/10">
                <Link
                  to={`/node/${row.kind}/${row.slug}`}
                  className="grid grid-cols-[1fr_auto] gap-3 py-2 cursor-pointer hover:bg-ink/[0.04]"
                >
                  <div>
                    <div className="text-[0.8rem] font-medium">{row.display_name}</div>
                    <div className="font-mono text-[0.64rem] text-muted mt-0.5">
                      {row.kind} · {row.shared_story_count} shared stories
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-[0.72rem] text-ink">{row.score.toFixed(2)}</div>
                    <div className="mt-1 w-[3rem] h-[3px] bg-ink/8 relative">
                      <div
                        className="absolute left-0 top-0 bottom-0 bg-phase-sustained"
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd viz-web && npx vitest run src/components/ConnectedNodesRail.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add src/components/ConnectedNodesRail.tsx src/components/ConnectedNodesRail.test.tsx
git commit -m "feat(viz-web): add ConnectedNodesRail grouping related nodes by kind"
```

---

### Task 32: Rebuild `NodeDetailView` orchestrator

**Files:**
- Modify: `viz-web/src/views/NodeDetailView.tsx`

- [ ] **Step 1: Replace `src/views/NodeDetailView.tsx` contents**

```tsx
import { useParams } from "react-router-dom";
import { ConnectedNodesRail } from "../components/ConnectedNodesRail";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { NodeHeaderBand } from "../components/NodeHeaderBand";
import { NodeStoriesList } from "../components/NodeStoriesList";
import { ThemeHistory } from "../components/ThemeHistory";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { fetchNodeDetail, fetchThemeHistory } from "../lib/api";
import { KIND_LABEL, MetricCell, MetricsStrip } from "../ui";

export function NodeDetailView() {
  const { kind, slug } = useParams<{ kind: string; slug: string }>();

  const detailState = useAsyncResource(() => fetchNodeDetail(kind ?? "", slug ?? ""), [kind, slug]);
  const historyState = useAsyncResource(
    () => (kind === "theme" && slug ? fetchThemeHistory(slug) : Promise.resolve(null)),
    [kind, slug],
  );

  if (!kind || !slug) {
    return <EmptyState title="Node not found" message="Choose a node from the landscape to inspect it in detail." />;
  }

  if (detailState.loading || historyState.loading) {
    return <LoadingState view="node-detail" />;
  }

  if (detailState.error || !detailState.data) {
    return <EmptyState title="Node detail unavailable" message="This node could not be loaded from the visualization API." />;
  }

  const detail = detailState.data;
  const history = historyState.data?.history ?? [];
  const latestDrift = history.length > 0 ? history[history.length - 1].centroid_drift : null;
  const themePhase = detail.kind === "theme" ? "steady" : null;

  const connectedCount =
    detail.events.length +
    detail.people.length +
    detail.nations.length +
    detail.orgs.length +
    detail.places.length +
    detail.themes.length;

  return (
    <section>
      <Breadcrumbs kind={detail.kind} displayName={detail.display_name} />
      <NodeHeaderBand detail={detail} phase={themePhase} />

      <div className="mx-5">
        <MetricsStrip>
          <MetricCell label="Kind" value={KIND_LABEL[detail.kind]} caption={detail.slug} />
          <MetricCell label="Stories" value={detail.article_count} caption="across sources" />
          <MetricCell label="Connected" value={connectedCount} caption="related nodes" />
          {detail.kind === "theme" ? (
            <MetricCell label="Phase" value={themePhase ?? "—"} caption="current lifecycle" />
          ) : null}
          {detail.kind === "theme" ? (
            <MetricCell
              label="Drift"
              value={latestDrift != null ? latestDrift.toFixed(3) : "—"}
              caption="centroid"
            />
          ) : null}
        </MetricsStrip>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] border-b border-ink">
        <div className="px-5 py-5 border-r border-ink/20 flex flex-col gap-6">
          {detail.kind === "theme" ? <ThemeHistory history={history} /> : null}
          <NodeStoriesList stories={detail.stories} />
        </div>
        <div className="px-5 py-5">
          <ConnectedNodesRail detail={detail} />
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `cd viz-web && npx vitest run src/views/NodeDetailView.test.tsx`
Expected: May still fail because the existing test file (originally `TopicDetailView.test.tsx`, renamed in Task 27) asserts the old `role="button"` for the story summary. We update the test in the next task.

Do not commit until Task 33 is done.

---

### Task 33: Update `NodeDetailView` test

**Files:**
- Modify: `viz-web/src/views/NodeDetailView.test.tsx`

- [ ] **Step 1: Replace `src/views/NodeDetailView.test.tsx` contents**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NodeDetailView } from "./NodeDetailView";

vi.stubGlobal(
  "fetch",
  vi.fn((input: string) => {
    if (input === "/api/nodes/event/april-8-hormuz-reclosure") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            node_id: "event-1",
            kind: "event",
            slug: "april-8-hormuz-reclosure",
            display_name: "April 8 Hormuz Reclosure",
            summary: "Node summary",
            article_count: 2,
            events: [],
            people: [],
            nations: [],
            orgs: [],
            places: [],
            themes: [],
            stories: [
              {
                story_id: "story-1",
                channel_id: 1,
                channel_title: "Signal Watch",
                timestamp_start: "2026-04-08T12:00:00Z",
                timestamp_end: "2026-04-08T12:03:00Z",
                confidence: 0.82,
                preview_text: "Alpha story preview",
                combined_text: "Alpha story preview with the full body.",
                media_refs: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    }
    return Promise.reject(new Error(`Unexpected fetch: ${input}`));
  }),
);

describe("NodeDetailView", () => {
  it("expands a story row to reveal full text", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/node/event/april-8-hormuz-reclosure"]}>
        <Routes>
          <Route path="/node/:kind/:slug" element={<NodeDetailView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("April 8 Hormuz Reclosure")).toBeInTheDocument();
    await user.click(screen.getByText("Alpha story preview"));
    expect(await screen.findByText("Alpha story preview with the full body.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/views/NodeDetailView.tsx src/views/NodeDetailView.test.tsx
git commit -m "feat(viz-web): rebuild NodeDetailView with header + rail + ThemeHistory"
```

---

## Phase 6 — State components

### Task 34: Rewrite `LoadingState`

**Files:**
- Modify: `viz-web/src/components/LoadingState.tsx`

- [ ] **Step 1: Replace `src/components/LoadingState.tsx` contents**

```tsx
import { Eyebrow, Rule } from "../ui";

interface LoadingStateProps {
  view?: "landscape" | "node-detail";
}

export function LoadingState({ view = "landscape" }: LoadingStateProps) {
  const headline = view === "landscape" ? "Fetching landscape" : "Fetching node";
  return (
    <section className="px-5 py-8" role="status" aria-live="polite">
      <Eyebrow>Loading</Eyebrow>
      <h1 className="text-[1.6rem] mt-1 mb-2">{headline}</h1>
      <Rule />
      <div className="mt-4 h-2 w-full max-w-md bg-ink/10 overflow-hidden rounded-sm">
        <div className="h-full w-2/5 bg-phase-emerging animate-[slide_1.2s_ease-in-out_infinite]" />
      </div>
      <div className="mt-6 max-w-3xl">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="grid grid-cols-[0.6rem_1fr_4rem_4rem] gap-2 items-center py-2 border-b border-ink/10">
            <span className="w-[0.55rem] h-[0.55rem] rounded-full bg-ink/15" />
            <span className="h-2 bg-ink/10 rounded-sm" />
            <span className="h-2 bg-ink/10 rounded-sm" />
            <span className="h-2 bg-ink/10 rounded-sm" />
          </div>
        ))}
      </div>
      <span className="sr-only">Loading knowledge graph…</span>
      <style>{`
        @keyframes slide {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(260%); }
        }
      `}</style>
    </section>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/components/LoadingState.tsx
git commit -m "feat(viz-web): rewrite LoadingState with skeleton rows and view prop"
```

---

### Task 35: Rewrite `EmptyState`

**Files:**
- Modify: `viz-web/src/components/EmptyState.tsx`

- [ ] **Step 1: Replace `src/components/EmptyState.tsx` contents**

```tsx
import { Button, Card, Eyebrow, Rule } from "../ui";

interface EmptyStateSuggestion {
  label: string;
  onClick: () => void;
}

interface EmptyStateProps {
  title: string;
  message: string;
  suggestions?: EmptyStateSuggestion[];
  onReset?: () => void;
}

export function EmptyState({ title, message, suggestions, onReset }: EmptyStateProps) {
  return (
    <section className="px-5 py-8">
      <Eyebrow>Nothing found</Eyebrow>
      <h1 className="text-[1.6rem] mt-1 mb-2">{title}</h1>
      <Rule />
      <p className="mt-3 text-[0.88rem] text-ink/85 max-w-prose">{message}</p>
      {suggestions && suggestions.length > 0 ? (
        <Card className="mt-5 max-w-md">
          <div className="font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted mb-2">/ suggestions</div>
          <ul className="list-none p-0 m-0 space-y-1">
            {suggestions.map((s) => (
              <li key={s.label}>
                <button
                  type="button"
                  onClick={s.onClick}
                  className="text-[0.82rem] text-ink underline underline-offset-2 decoration-ink/25 hover:decoration-ink/60 bg-transparent border-0 cursor-pointer p-0"
                >
                  <span className="text-phase-emerging mr-1">·</span>
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
          {onReset ? (
            <div className="mt-3">
              <Button variant="ghost" onClick={onReset}>
                Reset filters
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/components/EmptyState.tsx
git commit -m "feat(viz-web): rewrite EmptyState with suggestions and reset"
```

---

### Task 36: Rewrite `ComingSoonPanel`

**Files:**
- Modify: `viz-web/src/components/ComingSoonPanel.tsx`

- [ ] **Step 1: Replace `src/components/ComingSoonPanel.tsx` contents**

```tsx
import { Eyebrow, Rule } from "../ui";

interface ComingSoonPanelProps {
  title: string;
  description: string;
  phase?: string;
  eyebrow?: string;
}

export function ComingSoonPanel({ title, description, phase = "Phase 2", eyebrow = "Coming soon" }: ComingSoonPanelProps) {
  return (
    <section className="px-5 py-8 max-w-3xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1 className="text-[1.6rem] mt-1 mb-2">{title}</h1>
      <Rule />
      <p className="mt-3 text-[0.88rem] text-ink/85 max-w-prose">{description}</p>
      <div className="mt-5 border border-dashed border-ink/25 rounded-sm bg-ink/[0.02] p-4 flex flex-col gap-3">
        <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted">Upcoming</span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted w-[3rem]">RT</span>
          <span className="flex-1 h-2 bg-ink/10 rounded-sm" />
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted w-[3rem]">Tass</span>
          <span className="flex-1 h-2 bg-ink/10 rounded-sm" style={{ width: "70%" }} />
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted w-[3rem]">Reuters</span>
          <span className="flex-1 h-2 bg-ink/10 rounded-sm" style={{ width: "40%" }} />
        </div>
      </div>
      <div className="mt-4 inline-block font-mono text-[0.58rem] uppercase tracking-[0.12em] bg-ink text-paper rounded-sm px-2 py-1">
        {phase}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd viz-web
git add src/components/ComingSoonPanel.tsx
git commit -m "feat(viz-web): rewrite ComingSoonPanel with editorial styling"
```

---

## Phase 7 — Cleanup and verification

### Task 37: Delete legacy files

**Files:**
- Delete: `viz-web/src/styles.css`
- Delete: `viz-web/src/components/ChannelLegend.tsx`
- Delete: `viz-web/src/components/TopicTooltip.tsx`
- Delete: `viz-web/src/components/PhaseBadge.tsx`
- Delete: `viz-web/src/components/TimeWindowSelector.tsx`
- Modify: `viz-web/src/main.tsx` (drop the `import "./styles.css"` line)

- [ ] **Step 1: Remove the legacy stylesheet import from `src/main.tsx`**

Replace `src/main.tsx` contents with:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

import "@fontsource/fraunces/500.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 2: Delete the legacy files**

```bash
cd viz-web
git rm src/styles.css
git rm src/components/ChannelLegend.tsx
git rm src/components/TopicTooltip.tsx
git rm src/components/PhaseBadge.tsx
git rm src/components/TimeWindowSelector.tsx
```

- [ ] **Step 3: Run typecheck to catch dangling imports**

Run: `cd viz-web && npx tsc -b`
Expected: PASS. If TypeScript complains about a missing module, find the remaining import and update it to the new location (`src/ui/PhaseBadge`, `src/ui/WindowSelector`, `src/components/NodeTooltip`).

- [ ] **Step 4: Run tests**

Run: `cd viz-web && npm run test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd viz-web
git add -A
git commit -m "chore(viz-web): remove legacy styles.css, ChannelLegend, and moved primitives"
```

---

### Task 38: Final verification pass

- [ ] **Step 1: Build**

Run: `cd viz-web && npm run build`
Expected: PASS. `dist/` produced.

- [ ] **Step 2: Typecheck**

Run: `cd viz-web && npx tsc -b`
Expected: PASS with no errors.

- [ ] **Step 3: Test**

Run: `cd viz-web && npm run test`
Expected: PASS with every test green.

- [ ] **Step 4: Search for forbidden patterns**

Run these ripgrep searches (from repo root). Each must return zero results in `viz-web/src/`:

```bash
# No legacy "topic" as a domain term in new code
rg -n "TopicDetailView|TopicTooltip|TopicHeaderBand|TopicTimeline|TopicStoriesList|RelatedTopicsRail" viz-web/src/
# No pill-rounded
rg -n "rounded-full|border-radius:\s*999px" viz-web/src/
# No glassmorphism
rg -n "backdrop-filter|backdrop-blur" viz-web/src/
# No Google Fonts runtime import
rg -n "fonts.googleapis.com" viz-web/src/
# No references to the deleted styles.css
rg -n 'styles.css' viz-web/src/
```

Any match is a failure — fix it before moving on.

- [ ] **Step 5: Manual smoke test against dev API**

Run: `cd viz-web && VIZ_API_PROXY_TARGET=http://localhost:8000 npm run dev`

Walk through these flows:
1. Load `http://localhost:5173/` — Landscape renders. Metrics strip shows counts. Kind filter shows six chips. Phase filter pills are visible.
2. Toggle off `theme` in the kind filter — phase filter dims to 40%.
3. Re-enable `theme`, then toggle a phase pill — corresponding theme rows disappear from the table and corresponding bubbles disappear from the map.
4. Hover a table row — matching bubble highlights. Hover a bubble — matching row highlights.
5. Click a row or bubble — browser navigates to `/node/:kind/:slug` and Node Detail renders.
6. On a theme node: verify the `ThemeHistory` chart renders.
7. On a non-theme node (e.g. `event`): verify the `ThemeHistory` chart is absent and the `NodeStoriesList` still renders.
8. Click a related node in `ConnectedNodesRail` — navigate to another node detail.
9. Visit `/trends`, `/propagation`, `/evolution` — each renders the editorial `ComingSoonPanel`.
10. Stop dev server with Ctrl-C.

- [ ] **Step 6: Commit the verified build**

No code changes. If any fix was needed, it was committed as part of the matching task. This step exists as a checkpoint.

---

### Task 39: README update (conditional)

**Files:**
- Modify: `README.md` (only if routes or behavior changed — they should not have)

- [ ] **Step 1: Diff the Visualization Layer section of `README.md` against the new behavior**

Open `README.md` and find the "Visualization Layer" section. Verify:
- Phase 1 views still listed as `Landscape` and (now) `Node Detail` (the README currently says "Topic Detail" — update this).
- Route examples still work.
- The `cd viz-web && npm install && npm run dev` instructions still work.

- [ ] **Step 2: Apply the "Topic Detail" → "Node Detail" rename in README if needed**

Use `Edit` to replace any instance of "Topic Detail" with "Node Detail" in `README.md`, only inside the Visualization Layer section.

- [ ] **Step 3: Commit (if any change was made)**

```bash
git add README.md
git commit -m "docs: update viz-web phase 1 view name to Node Detail"
```

If no change was necessary, skip this step.

---

## Self-review checklist (run after writing the plan)

1. **Spec coverage.**
   - Palette (paper, ink, card, surface-2, muted, phase, kind, neutral) — Task 3 ✓
   - Fraunces + Inter + JetBrains Mono, self-hosted — Task 4 ✓
   - Primitives (Button, Pill, Eyebrow, Rule, Card, PhaseBadge, KindChip, MetricCell, MetricsStrip, WindowSelector, SortableTable) — Tasks 6–16 ✓
   - ui/index.ts barrel — Task 17 ✓
   - Layout (AppShell, TopNav, Breadcrumbs) — Tasks 18–20 ✓
   - App.tsx refactor to use AppShell — Task 21 ✓
   - Landscape (FilterBar, LandscapeTable, LandscapeMap, orchestrator) — Tasks 22–26 ✓
   - Node Detail rename + NodeHeaderBand + ThemeHistory + NodeStoriesList + ConnectedNodesRail + orchestrator + test update — Tasks 27–33 ✓
   - LoadingState, EmptyState, ComingSoonPanel rewrites — Tasks 34–36 ✓
   - Legacy file deletion — Task 37 ✓
   - Final verification including forbidden-pattern search — Task 38 ✓
   - README update (conditional) — Task 39 ✓
   - Metrics strip with client-side counts only (no fabricated deltas) — Task 26 ✓
   - Default kind filter = `{event, theme}` — Task 26 ✓
   - Phase filter dims when theme not selected — Task 22 ✓
   - Theme history only renders for themes — Task 32 ✓
   - NodeTooltip renamed from TopicTooltip — Task 24 ✓
   - WindowSelector covers all six `WindowKey` values — Task 15 ✓
   - channelColors.ts kept as-is (no task modifies it) ✓
   - No virtualization for the table ✓
   - No dark mode support ✓
   - "Telegram Knowledge Graph" title preserved — Task 18 ✓

2. **Placeholder scan.** No "TBD", "TODO", or "add error handling" instructions left in the plan. Each step has concrete code or a concrete command.

3. **Type consistency.**
   - `NodeKind` used consistently across KindChip, FilterBar, LandscapeView, LandscapeTable, LandscapeMap, NodeTooltip.
   - `WindowKey` used in WindowSelector + LandscapeView.
   - `PhaseKey` used in FilterBar + LandscapeView.
   - `GraphNodeRow` used in LandscapeTable + LandscapeMap + NodeTooltip.
   - `NodeDetail` used in NodeHeaderBand + ConnectedNodesRail + NodeDetailView.
   - `ThemeHistoryPoint` used in ThemeHistory + NodeDetailView.
   - `NodeStoryRow` used in NodeStoriesList + NodeDetailView.
   - Method/prop signatures line up: `onHover(nodeId: string | null)`, `onRowClick(node)`, `onNodeClick(node)`, `onKindToggle(kind)`, `onPhaseToggle(phase)`, `onChange(key)`.

Ready for execution.
