from __future__ import annotations

import json
from pathlib import Path

import pytest

NOTEBOOK_DIR = Path(__file__).resolve().parents[1] / "notebooks"
NOTEBOOK_NAMES = [
    "00_collect",
    "01_corpus",
    "02_tempo",
    "03_agenda",
    "04_actors",
    "05_tone",
    "06_media",
]
MAX_BYTES = 3 * 1024 * 1024


@pytest.mark.parametrize("name", NOTEBOOK_NAMES)
def test_story_notebook_exists_executed_and_small(name: str) -> None:
    path = NOTEBOOK_DIR / f"{name}.ipynb"
    assert path.exists(), f"{path} is missing"
    assert path.stat().st_size < MAX_BYTES, f"{name} is {path.stat().st_size / 1e6:.1f} MB (limit 3 MB)"

    notebook = json.loads(path.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert code_cells, f"{name} has no code cells"
    for index, cell in enumerate(code_cells):
        assert cell.get("execution_count") is not None, f"{name}: code cell {index} was never executed"
        for output in cell.get("outputs", []):
            assert output.get("output_type") != "error", f"{name}: code cell {index} has an error output"


@pytest.mark.parametrize("name", NOTEBOOK_NAMES)
def test_story_notebook_opens_with_question_answer_box(name: str) -> None:
    notebook = json.loads((NOTEBOOK_DIR / f"{name}.ipynb").read_text(encoding="utf-8"))
    first_markdown = next(cell for cell in notebook["cells"] if cell["cell_type"] == "markdown")
    text = "".join(first_markdown["source"])
    assert "Question" in text and "Answer" in text
    assert "prose pending" not in "".join("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "markdown")
