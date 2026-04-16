#!/usr/bin/env bash
# Insert schema validation as a pipeline checkpoint. `tee` forks the
# graph JSON to `visiter validate` (which writes its verdict to stderr
# / a side file) while the main pipe continues into `to-dot`. If the
# graph ever drifted from the documented shape — say, after a future
# breaking change to iterate — this would catch it before rendering.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

EXPR="$(cat "$HERE/data/descent.expr")"

VALIDATE_LOG="$OUT/validate.log"
visiter iterate "$EXPR" \
  | tee >(visiter validate > "$VALIDATE_LOG" 2>&1) \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/descent_validated.svg"

# Surface the validator's verdict.
echo "validator said: $(cat "$VALIDATE_LOG")"
echo "wrote $OUT/descent_validated.svg"
