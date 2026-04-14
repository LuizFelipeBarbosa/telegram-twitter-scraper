from __future__ import annotations

import json
from pathlib import Path


NOTEBOOK_PATH = Path("notebooks/pipeline.ipynb")


def test_pipeline_notebook_has_cleared_outputs() -> None:
    with NOTEBOOK_PATH.open() as handle:
        notebook = json.load(handle)

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        assert cell.get("outputs", []) == []
        assert cell.get("execution_count") is None
