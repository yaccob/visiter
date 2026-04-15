#!/usr/bin/env bash
# Insert schema validation as a pipeline checkpoint. `tee` forks the
# graph JSON to `visiter validate` (which writes its verdict to stderr
# / a side file) while the main pipe continues into `to-dot`. If the
# graph ever drifted from the documented shape — say, after a future
# breaking change to iterate — this would catch it before rendering.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out

EXPR="$(cat data/descent.expr)"

VALIDATE_LOG="out/validate.log"
visiter iterate "$EXPR" \
  | tee >(visiter validate > "$VALIDATE_LOG" 2>&1) \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o out/descent_validated.svg

# Surface the validator's verdict.
echo "validator said: $(cat "$VALIDATE_LOG")"
echo "wrote out/descent_validated.svg"
