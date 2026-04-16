# Behold Israel Pipeline Notebook — Design

**Date:** 2026-04-16
**Status:** Approved

## Goal

Create a second pipeline notebook pinned to the "Behold Israel" Telegram channel
(`t.me/beholdisrael`, Amir Tsarfati), parallel to the existing
[pipeline.ipynb](../../../notebooks/pipeline.ipynb) PressTV workflow, so the two
channels can be analyzed side-by-side without editing a shared notebook
between runs.

## Non-goals

- No changes to the existing [pipeline.ipynb](../../../notebooks/pipeline.ipynb).
- No changes to any module under
  [src/telegram_scraper/analysis/](../../../src/telegram_scraper/analysis/).
- No new dependencies.
- No Hebrew-specific NLP adjustments (channel is English-language).
- No automatic file saves — figures stay in memory, same as the PressTV run.
- No parameterization of the output folder; it is fixed per-notebook.

## Deliverables

| Path | Purpose |
|---|---|
| `notebooks/pipeline_behold_israel.ipynb` | Duplicate of `pipeline.ipynb` with channel pinned and intro markdown updated. |
| `docs/behold-israel-channel-analysis.md` | Empty placeholder doc parallel to [docs/presstv-channel-analysis.md](../../presstv-channel-analysis.md); filled in manually after notebook runs. |
| `docs/assets/behold-israel/.gitkeep` | Empty `.gitkeep` so the asset folder exists in git; parallel use to `docs/assets/presstv-analysis/` but populated manually on demand. |

## Design

### Channel selection change

In [pipeline.ipynb](../../../notebooks/pipeline.ipynb) Section 2, the existing
cell selects a channel by positional index into the discovered channels list:

```python
CHANNEL_INDEX = 0
MESSAGE_LIMIT = 1200
...
selected_chat = channels[CHANNEL_INDEX]
```

In the new notebook, replace that cell with a slug-based lookup that leverages
the existing `ChatRecord.selectors()` helper in
[src/telegram_scraper/models.py](../../../src/telegram_scraper/models.py):

```python
SELECTED_SLUG = "beholdisrael"
MESSAGE_LIMIT = 1200

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
```

`MESSAGE_LIMIT = 1200` is unchanged. Everything downstream reads `selected_chat`
exactly as the existing notebook does.

### Narrative changes

- **Top intro cell:** Update the H1 and opening paragraph to reference Behold
  Israel / Amir Tsarfati instead of the generic channel description. Keep the
  "Sections 1-14" scope description identical in meaning.
- **Section 2 methodology markdown:** Add one sentence noting that this
  notebook pins the channel by slug (`beholdisrael`) rather than selecting by
  positional index, and fails loudly if the channel isn't discoverable.
- **All other markdown in Sections 3-14:** Unchanged. Existing text refers to
  "the selected channel" generically and remains correct.

### What does not change

- No code changes outside the Section 2 selection cell and the two markdown
  cells listed above.
- No changes to any analysis module.
- No changes to existing tests. [test_pipeline_notebook.py](../../../tests/test_pipeline_notebook.py)
  and [test_notebook_pipeline.py](../../../tests/test_notebook_pipeline.py)
  currently target shared helpers and the existing notebook; extending them to
  cover the new notebook is out of scope unless they fail CI.

### Output isolation

- Figures remain in memory when the notebook runs. No `savefig` / `write_html`
  calls are added.
- Manual exports from the new notebook go to `docs/assets/behold-israel/`.
  Manual exports from [pipeline.ipynb](../../../notebooks/pipeline.ipynb)
  continue going to `docs/assets/presstv-analysis/`. The two sets never collide
  because each notebook is pinned to its own channel and each analyst-written
  export step specifies its own folder.
- `docs/behold-israel-channel-analysis.md` starts empty (with just a title and
  channel metadata line) and is populated manually after running the notebook,
  mirroring how
  [docs/presstv-channel-analysis.md](../../presstv-channel-analysis.md) was
  produced.

## Success criteria

1. Opening `notebooks/pipeline_behold_israel.ipynb` and running Section 1 →
   Section 2 selects the Behold Israel channel without prompting for an index.
2. If Behold Israel is not in the account's visible channels (filtered out,
   not joined, or wrong slug), Section 2 raises `RuntimeError` with a clear
   message rather than silently selecting the wrong channel.
3. Running Sections 3-14 end-to-end produces the same kinds of in-memory
   outputs as the existing PressTV run, but about Behold Israel.
4. The existing [pipeline.ipynb](../../../notebooks/pipeline.ipynb) is
   byte-identical before and after this change.

## Risks and mitigations

- **Slug drift / channel rename:** Telegram channels can change username. If
  `beholdisrael` stops resolving, Section 2 fails loudly (criterion 2), and
  the fix is a one-line edit to `SELECTED_SLUG`.
- **Include/exclude filters hiding the channel:** Error message explicitly
  points at `.env` filters as a likely cause.
- **Two near-identical notebooks drifting:** Accepted trade-off. If the
  analysis pipeline evolves significantly, we re-copy the updated
  `pipeline.ipynb` and re-apply the three small changes documented above.
