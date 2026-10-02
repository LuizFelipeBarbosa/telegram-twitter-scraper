#!/usr/bin/env bash
# Execute the story notebooks in order, in place, keeping their outputs.
# Usage: bash scripts/run_notebooks.sh            (all of 00-06)
#        bash scripts/run_notebooks.sh 03 05      (only the listed notebook numbers)
# Prerequisites: `uv sync --group dev` and the spaCy model (see README). Never calls Telegram.
set -euo pipefail
cd "$(dirname "$0")/.."

ALL=(00_collect 01_corpus 02_tempo 03_agenda 04_actors 05_tone 06_media)
if [ "$#" -gt 0 ]; then
  SELECTED=()
  for prefix in "$@"; do
    for name in "${ALL[@]}"; do
      [[ "$name" == "$prefix"* ]] && SELECTED+=("$name")
    done
  done
else
  SELECTED=("${ALL[@]}")
fi

for name in "${SELECTED[@]}"; do
  echo "=== executing notebooks/${name}.ipynb ==="
  uv run --group dev jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=1800 "notebooks/${name}.ipynb"
done
echo "done: ${#SELECTED[@]} notebook(s) executed"
