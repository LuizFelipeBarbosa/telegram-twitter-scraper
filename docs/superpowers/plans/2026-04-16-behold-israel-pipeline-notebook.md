# Behold Israel Pipeline Notebook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a second pipeline notebook pinned to Amir Tsarfati's "Behold Israel" Telegram channel (`t.me/beholdisrael`), parallel to the existing PressTV pipeline notebook, so the two channels can be analyzed side-by-side.

**Architecture:** Duplicate [notebooks/pipeline.ipynb](../../../notebooks/pipeline.ipynb) verbatim, then apply three targeted cell edits: replace the Section 2 positional-index selection with a slug-based lookup using the existing `ChatRecord.selectors()` helper, and update two markdown cells (top intro + Section 2 methodology) so the context reads correctly. No module changes, no new dependencies, no tests. Supporting files (`.gitkeep` for the asset folder, empty analysis doc) are added alongside.

**Tech Stack:** Python 3, Jupyter notebook (`.ipynb` JSON), `nbformat` for robust cell edits, existing [src/telegram_scraper](../../../src/telegram_scraper/) modules.

**Spec:** [docs/superpowers/specs/2026-04-16-behold-israel-pipeline-notebook-design.md](../specs/2026-04-16-behold-israel-pipeline-notebook-design.md)

---

## File Structure

| Path | Purpose | Action |
|---|---|---|
| `docs/assets/behold-israel/.gitkeep` | Empty placeholder so the asset folder tracks in git. | Create |
| `docs/behold-israel-channel-analysis.md` | Empty analysis doc mirroring [docs/presstv-channel-analysis.md](../../presstv-channel-analysis.md), to be filled in manually after running the notebook. | Create |
| `notebooks/pipeline_behold_israel.ipynb` | Duplicate of [notebooks/pipeline.ipynb](../../../notebooks/pipeline.ipynb) with three cells edited: the Section 2 code cell (`id="6e688c92"`), the top intro markdown (`id="4bf60fbd"`), and the Section 2 methodology markdown (`id="00886544"`). | Create by copy + programmatic edit |

The existing [notebooks/pipeline.ipynb](../../../notebooks/pipeline.ipynb) is untouched. No files under [src/telegram_scraper/](../../../src/telegram_scraper/) are modified.

---

## Task 1: Create the asset folder placeholder

**Files:**
- Create: `docs/assets/behold-israel/.gitkeep`

- [ ] **Step 1: Create the folder and `.gitkeep`**

Run:

```bash
mkdir -p docs/assets/behold-israel
touch docs/assets/behold-israel/.gitkeep
```

- [ ] **Step 2: Verify it's tracked**

Run:

```bash
git status --short docs/assets/behold-israel/
```

Expected: a line like `?? docs/assets/behold-israel/.gitkeep`.

- [ ] **Step 3: Commit**

```bash
git add docs/assets/behold-israel/.gitkeep
git commit -m "chore: create docs/assets/behold-israel placeholder folder"
```

---

## Task 2: Create the placeholder analysis doc

**Files:**
- Create: `docs/behold-israel-channel-analysis.md`

- [ ] **Step 1: Create the markdown file with exactly this content**

```markdown
# Behold Israel — Channel Analysis

**Channel:** [t.me/beholdisrael](https://t.me/beholdisrael) (Amir Tsarfati, "Behold Israel")
**Notebook:** [notebooks/pipeline_behold_israel.ipynb](../notebooks/pipeline_behold_israel.ipynb)
**Assets:** [docs/assets/behold-israel/](assets/behold-israel/)

> This document is populated manually after running the pipeline notebook.
> See [docs/presstv-channel-analysis.md](presstv-channel-analysis.md) for the
> format used by the PressTV run.
```

Use the Write tool (or `cat` heredoc) to create it at `docs/behold-israel-channel-analysis.md`.

- [ ] **Step 2: Verify the file exists and has the expected content**

Run:

```bash
head -n 5 docs/behold-israel-channel-analysis.md
```

Expected output:

```
# Behold Israel — Channel Analysis

**Channel:** [t.me/beholdisrael](https://t.me/beholdisrael) (Amir Tsarfati, "Behold Israel")
**Notebook:** [notebooks/pipeline_behold_israel.ipynb](../notebooks/pipeline_behold_israel.ipynb)
**Assets:** [docs/assets/behold-israel/](assets/behold-israel/)
```

- [ ] **Step 3: Commit**

```bash
git add docs/behold-israel-channel-analysis.md
git commit -m "docs: add placeholder for Behold Israel channel analysis"
```

---

## Task 3: Duplicate the pipeline notebook

**Files:**
- Create: `notebooks/pipeline_behold_israel.ipynb` (byte-for-byte copy of [notebooks/pipeline.ipynb](../../../notebooks/pipeline.ipynb))

- [ ] **Step 1: Copy the notebook**

Run:

```bash
cp notebooks/pipeline.ipynb notebooks/pipeline_behold_israel.ipynb
```

- [ ] **Step 2: Verify the copy parses as valid nbformat JSON**

Run:

```bash
uv run python -c "import nbformat; nb = nbformat.read('notebooks/pipeline_behold_israel.ipynb', as_version=4); print('ok', len(nb.cells), 'cells')"
```

Expected: `ok <N> cells` where `<N>` matches the original (around 70+ cells). Any parse error means the copy is corrupted.

- [ ] **Step 3: Verify the existing notebook is untouched (byte-identical)**

Run:

```bash
git diff --stat notebooks/pipeline.ipynb
```

Expected: empty output (no changes to the existing notebook).

- [ ] **Step 4: Commit**

```bash
git add notebooks/pipeline_behold_israel.ipynb
git commit -m "feat: copy pipeline notebook as starting point for Behold Israel"
```

---

## Task 4: Apply the three cell edits via nbformat

**Files:**
- Modify: `notebooks/pipeline_behold_israel.ipynb` — three cells identified by their stable IDs:
  - `id="4bf60fbd"` — top intro markdown cell
  - `id="00886544"` — Section 2 methodology markdown cell
  - `id="6e688c92"` — Section 2 code cell that currently does `CHANNEL_INDEX = 0` selection

Do the edit with a one-shot Python script that uses `nbformat`. This is more robust than patching JSON by string, because cell sources are stored as arrays of lines and whitespace must round-trip cleanly.

- [ ] **Step 1: Run the edit script**

Run this command exactly. It modifies `notebooks/pipeline_behold_israel.ipynb` in place:

```bash
uv run python - <<'PY'
import nbformat

NOTEBOOK = "notebooks/pipeline_behold_israel.ipynb"

INTRO_NEW = """# Behold Israel Pipeline - Notebook Only (Sections 1-14)

This notebook is the Behold Israel counterpart to `pipeline.ipynb`. It pins the selected channel to `t.me/beholdisrael` (Amir Tsarfati, "Behold Israel") by slug and otherwise keeps the first five KG stages entirely in memory, delegating the heavier analysis stages to reusable Python modules under `src/telegram_scraper/analysis/`.
It fetches Behold Israel's Telegram messages, translates them, embeds them, and exposes notebook-friendly DataFrames and figure objects without writing to Postgres, Redis, or Pinecone.

Use this alongside the PressTV notebook when you want to compare the two channels' emotional arcs, thematic landscapes, messaging cadence, vocabulary shifts over time, co-mentioned political actors, rhetorical framing, reply-threading behavior, phrase-level collocation networks, and media-vs-text editorial differences.
"""

SECTION2_METHODOLOGY_NEW = """---
## Section 2 - Telegram Client & Channel Discovery

**Methodology.** This section authenticates through the saved Telethon session, requests the account's visible dialogs, normalizes them into internal chat records, and filters them down to channels only. Include / exclude filters from `.env` are applied here, so the table is the exact universe of channels available for selection in the rest of the notebook.

**Channel pinning.** Unlike `pipeline.ipynb`, this notebook pins the selected channel by slug (`beholdisrael`) in the next cell rather than by positional index. If the Behold Israel channel is not present in `channels_df`, the next cell raises `RuntimeError` with a clear message so you can fix `.env` filters or confirm the account has joined the channel before continuing.

**How to read the output.** `channels_df` is a selection table, not an analysis result. Confirm that Behold Israel appears and that its `slug` or `username` column reads `beholdisrael`. If it is missing, the issue is usually authentication, account visibility, or an overly restrictive include / exclude filter.
"""

SELECTION_CELL_NEW = '''SELECTED_SLUG = "beholdisrael"
MESSAGE_LIMIT = 1200

if not channels:
    raise RuntimeError("No channels matched the current include/exclude filters.")

matches = [c for c in channels if SELECTED_SLUG.lower() in c.selectors()]
if not matches:
    raise RuntimeError(
        f"No channel matching '{SELECTED_SLUG}' in the discovered list. "
        f"Check include/exclude filters in .env and confirm the account has "
        f"joined t.me/{SELECTED_SLUG}."
    )
if len(matches) > 1:
    raise RuntimeError(
        f"Multiple channels match '{SELECTED_SLUG}': "
        f"{[c.title for c in matches]}"
    )

selected_chat = matches[0]
print(f"Selected channel: [{selected_chat.chat_id}] {selected_chat.title or '(untitled)'}")
print(f"Username: @{selected_chat.username}" if selected_chat.username else "Username: ---")
print(f"Message limit: {MESSAGE_LIMIT}")'''

REPLACEMENTS = {
    "4bf60fbd": ("markdown", INTRO_NEW),
    "00886544": ("markdown", SECTION2_METHODOLOGY_NEW),
    "6e688c92": ("code", SELECTION_CELL_NEW),
}

nb = nbformat.read(NOTEBOOK, as_version=4)

seen = set()
for cell in nb.cells:
    cell_id = cell.get("id")
    if cell_id in REPLACEMENTS:
        expected_type, new_source = REPLACEMENTS[cell_id]
        if cell["cell_type"] != expected_type:
            raise SystemExit(
                f"Cell {cell_id} has type {cell['cell_type']!r}, expected {expected_type!r}"
            )
        cell["source"] = new_source
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        seen.add(cell_id)

missing = set(REPLACEMENTS) - seen
if missing:
    raise SystemExit(f"Did not find cells: {missing}")

nbformat.write(nb, NOTEBOOK)
print(f"Updated {len(seen)} cells in {NOTEBOOK}")
PY
```

Expected output: `Updated 3 cells in notebooks/pipeline_behold_israel.ipynb`.

- [ ] **Step 2: Verify the code cell now contains the slug (and no longer contains `CHANNEL_INDEX`)**

Run:

```bash
uv run python -c "
import nbformat
nb = nbformat.read('notebooks/pipeline_behold_israel.ipynb', as_version=4)
cell = next(c for c in nb.cells if c.get('id') == '6e688c92')
src = cell['source']
assert 'SELECTED_SLUG = \"beholdisrael\"' in src, 'slug not found'
assert 'CHANNEL_INDEX' not in src, 'CHANNEL_INDEX still present'
assert 'c.selectors()' in src, 'selectors() helper not used'
print('selection cell OK')
"
```

Expected: `selection cell OK`.

- [ ] **Step 3: Verify the two markdown cells now reference Behold Israel**

Run:

```bash
uv run python -c "
import nbformat
nb = nbformat.read('notebooks/pipeline_behold_israel.ipynb', as_version=4)
intro = next(c for c in nb.cells if c.get('id') == '4bf60fbd')['source']
sec2 = next(c for c in nb.cells if c.get('id') == '00886544')['source']
assert 'Behold Israel' in intro, 'intro not updated'
assert 'beholdisrael' in sec2, 'section 2 methodology not updated'
print('markdown cells OK')
"
```

Expected: `markdown cells OK`.

- [ ] **Step 4: Verify all code cells still have cleared outputs (matches the convention enforced by [tests/test_pipeline_notebook.py](../../../tests/test_pipeline_notebook.py) for the original)**

Run:

```bash
uv run python -c "
import nbformat
nb = nbformat.read('notebooks/pipeline_behold_israel.ipynb', as_version=4)
for c in nb.cells:
    if c['cell_type'] == 'code':
        assert c.get('outputs', []) == [], f'cell {c.get(\"id\")} has outputs'
        assert c.get('execution_count') is None, f'cell {c.get(\"id\")} has execution_count'
print('all code cells cleared')
"
```

Expected: `all code cells cleared`.

- [ ] **Step 5: Verify the existing notebook is still untouched**

Run:

```bash
git diff --stat notebooks/pipeline.ipynb
```

Expected: empty output.

- [ ] **Step 6: Commit**

```bash
git add notebooks/pipeline_behold_israel.ipynb
git commit -m "feat: pin Behold Israel notebook to beholdisrael via slug lookup"
```

---

## Task 5: Final integration check

**Files:** none modified; verification only.

- [ ] **Step 1: Run the existing test suite to confirm nothing we touched breaks it**

Run:

```bash
uv run pytest -q
```

Expected: all existing tests pass. [tests/test_pipeline_notebook.py](../../../tests/test_pipeline_notebook.py) checks `notebooks/pipeline.ipynb` only, so the new notebook is not exercised here — that's expected and matches the spec's "no new tests" decision.

- [ ] **Step 2: Verify the final state of the working tree**

Run:

```bash
git log --oneline -n 5
git status --short
```

Expected: four new commits on top of `main` (one each from Tasks 1–4) and a clean working tree.

- [ ] **Step 3: Smoke-check that the new notebook opens in nbformat and imports nothing it didn't already**

Run:

```bash
uv run python -c "
import nbformat
nb = nbformat.read('notebooks/pipeline_behold_israel.ipynb', as_version=4)
code = '\n'.join(c['source'] for c in nb.cells if c['cell_type'] == 'code')
# The slug lookup uses ChatRecord.selectors(), which is already imported
# transitively via the Section 2 channel-discovery cell. Confirm no new names:
for forbidden in ['from x', 'fnmatch', 'unidecode']:
    assert forbidden not in code, f'unexpected new import: {forbidden}'
print('new notebook uses no new imports')
"
```

Expected: `new notebook uses no new imports`.

No commit for Task 5 — it is verification only.

---

## Self-Review Notes

**Spec coverage check (performed while writing):**

- Deliverable: `notebooks/pipeline_behold_israel.ipynb` → Tasks 3 + 4.
- Deliverable: `docs/behold-israel-channel-analysis.md` placeholder → Task 2.
- Deliverable: `docs/assets/behold-israel/` folder → Task 1.
- Design: channel selection swap (`CHANNEL_INDEX` → `SELECTED_SLUG` with `c.selectors()`) → Task 4, Step 1 + Step 2.
- Design: narrative changes (top intro + Section 2 methodology) → Task 4, Step 1 + Step 3.
- Design: no module changes, no new dependencies → enforced by Task 5, Step 3.
- Design: existing `pipeline.ipynb` byte-identical after change → verified in Task 3 Step 3 and Task 4 Step 5.
- Design: cleared outputs preserved → verified in Task 4 Step 4.
- Success criterion: slug-based selection without index prompt → implemented in Task 4 Step 1.
- Success criterion: loud failure when channel missing → implemented in Task 4 Step 1 (`RuntimeError`).
- Success criterion: same kinds of in-memory outputs as PressTV run → inherited automatically because Tasks 3 + 4 only touch the selection cell and two markdown cells.

All spec items map to tasks. No placeholders, no "TBD", no under-specified steps.
